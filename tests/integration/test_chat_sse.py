"""聊天 SSE 集成测试：流式事件、工具调用、转人工。

**假 LLM，真工具**：模型输出用脚本化的假客户端顶替（不然测试要联网、要花钱、
结果还不确定），但工具真正执行 —— `search_knowledge` 会真去查数据库里的向量。
这样"模型调工具 → 工具真检索 → 结果回填给模型 → 模型作答"整条链路都在覆盖内，
而不是把最该验的一环 mock 掉。
"""
import json

import pytest
from httpx import AsyncClient

from app.ai.agent import agent as agent_module
from app.infrastructure.llm import StreamChunk, ToolCallDelta
from tests.integration.helpers import (
    create_conversation,
    create_kb,
    event_types,
    joined_content,
    parse_sse,
    upload_and_wait,
)


def _tool_call_chunks(index: int, call_id: str, name: str, arguments: dict) -> list[StreamChunk]:
    """把一次工具调用切成多个 chunk —— 模拟真实的流式碎片化下发。

    参数 JSON 被拆成两段，且 id/函数名只出现在第一段。
    这样能顺带验证"按 index 跨 chunk 累积"这段最容易写错的逻辑。
    """
    raw = json.dumps(arguments, ensure_ascii=False)
    mid = len(raw) // 2
    return [
        StreamChunk(tool_call=ToolCallDelta(index=index, id=call_id, name=name)),
        StreamChunk(tool_call=ToolCallDelta(index=index, arguments=raw[:mid])),
        StreamChunk(tool_call=ToolCallDelta(index=index, arguments=raw[mid:])),
    ]


def _fake_llm(rounds: list[list[StreamChunk]]):
    """构造一个按轮次脚本化返回的假 LLM，并记录每轮收到的 messages。"""
    calls: list[dict] = []
    remaining = list(rounds)

    def fake(messages, *, tools=None, **kwargs):
        calls.append({"messages": list(messages), "tools": tools})

        async def gen():
            for chunk in remaining.pop(0) if remaining else []:
                yield chunk

        return gen()

    fake.calls = calls  # type: ignore[attr-defined]
    return fake


@pytest.fixture
def patch_llm(monkeypatch):
    """替换 Agent 内部的 LLM 调用。"""

    def _apply(rounds: list[list[StreamChunk]]):
        fake = _fake_llm(rounds)
        monkeypatch.setattr(agent_module, "chat_stream_with_tools", fake)
        return fake

    return _apply


# ── 基础流式 ────────────────────────────────────────────


async def test_普通回答以SSE流式返回并落库(client: AsyncClient, auth_headers: dict, patch_llm):
    conv_id = await create_conversation(client, auth_headers)
    patch_llm([[StreamChunk(content="退款"), StreamChunk(content="一般 3 到 5 个工作日到账[1]。")]])

    r = await client.post(
        "/api/v1/chat",
        json={"conversation_id": conv_id, "message": "退款多久到账"},
        headers=auth_headers,
    )
    assert r.status_code == 200

    events = parse_sse(r.text)
    types = event_types(events)
    assert types[0] == "start"
    assert types[-1] == "done"
    assert types.count("done") == 1, "done 不应重复发送"
    assert "3 到 5 个工作日" in joined_content(events)

    # 用户消息与 AI 回复都应落库（AI 回复在流结束后由 router 保存）
    msgs = (
        await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers)
    ).json()["data"]["items"]
    assert [m["sender_type"] for m in msgs] == ["user", "ai"]
    assert "3 到 5 个工作日" in msgs[1]["content"]


async def test_会话状态随done事件返回(client: AsyncClient, auth_headers: dict, patch_llm):
    conv_id = await create_conversation(client, auth_headers)
    patch_llm([[StreamChunk(content="你好")]])

    r = await client.post(
        "/api/v1/chat", json={"conversation_id": conv_id, "message": "在吗"}, headers=auth_headers
    )
    done = next(e for e in parse_sse(r.text) if e["type"] == "done")
    assert done["status"] == 1, "AI 服务中的会话，done 应带状态 1"
    assert "reply" not in done, "done 帧不该重复携带完整回答"


# ── 工具调用（工具是真实执行的）──────────────────────────


async def test_模型调用检索工具并基于真实检索结果作答(
    client: AsyncClient, auth_headers: dict, patch_llm
):
    """最有价值的一条：工具真的查了库，检索结果真的回填给了模型。"""
    kb_id = await create_kb(client, auth_headers)
    await upload_and_wait(client, auth_headers, kb_id)
    conv_id = await create_conversation(client, auth_headers)

    fake = patch_llm(
        [
            _tool_call_chunks(0, "call_1", "search_knowledge", {"query": "退款时效", "top_k": 3}),
            [StreamChunk(content="退款一般 3 到 5 个工作日到账。")],
        ]
    )

    r = await client.post(
        "/api/v1/chat",
        json={"conversation_id": conv_id, "message": "退款多久能到账"},
        headers=auth_headers,
    )
    assert r.status_code == 200

    types = event_types(parse_sse(r.text))
    assert "tool_start" in types, "工具开始执行时必须有事件,否则前端会长时间无反馈"
    assert "tool_end" in types
    assert types.index("tool_start") < types.index("tool_end")
    assert "退款" in joined_content(parse_sse(r.text))

    # 关键断言：第二次调用模型时，工具的执行结果必须以 role=tool 回填
    assert len(fake.calls) == 2, "工具调用后应再调一次模型来生成最终回答"
    tool_msgs = [m for m in fake.calls[1]["messages"] if m.get("role") == "tool"]
    assert tool_msgs, "工具结果没有回填给模型,模型无从基于资料作答"
    assert "退款" in tool_msgs[0]["content"], "回填的内容不是真实检索结果"

    # 第一轮请求必须带上工具定义与 tool_choice，否则模型根本不会调工具
    assert fake.calls[0]["tools"] is not None


async def test_工具轮数达到上限时强制收尾(client: AsyncClient, auth_headers: dict, patch_llm):
    """模型反复调工具时不能无限循环：收尾那次必须禁用工具。"""
    conv_id = await create_conversation(client, auth_headers)

    def loop_round() -> list[StreamChunk]:
        return _tool_call_chunks(0, "call_x", "get_user_profile", {})

    fake = patch_llm(
        [loop_round() for _ in range(5)] + [[StreamChunk(content="（直接作答）")]]
    )

    r = await client.post(
        "/api/v1/chat",
        json={"conversation_id": conv_id, "message": "问题"},
        headers=auth_headers,
    )
    assert r.status_code == 200

    events = parse_sse(r.text)
    assert any(e["type"] == "notice" for e in events), "达到上限应给出提示"
    assert fake.calls[-1]["tools"] is None, "收尾轮必须禁用工具,否则模型会继续调"


# ── 转人工 ──────────────────────────────────────────────


async def test_模型转人工会改会话状态并自动建单(
    client: AsyncClient, auth_headers: dict, patch_llm
):
    conv_id = await create_conversation(client, auth_headers)
    patch_llm(
        [
            _tool_call_chunks(0, "call_ho", "handoff_to_human", {"reason": "用户要求人工"}),
            [StreamChunk(content="已为您转接人工客服,请稍候。")],
        ]
    )

    r = await client.post(
        "/api/v1/chat",
        json={"conversation_id": conv_id, "message": "我要人工客服"},
        headers=auth_headers,
    )
    events = parse_sse(r.text)
    types = event_types(events)
    assert "handoff" in types

    handoff = next(e for e in events if e["type"] == "handoff")
    assert handoff["status"] == 2, "转人工后会话应处于「等待人工」"
    ticket_id = handoff["ticket_id"]
    assert ticket_id, "转人工必须自动建单,否则没有责任凭证可追"

    # 会话状态真的落库了
    conv = (
        await client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers)
    ).json()["data"]
    assert conv["status"] == 2
    assert conv["status_text"] == "等待人工"

    # 工单也真的建了
    ticket = (await client.get(f"/api/v1/tickets/{ticket_id}", headers=auth_headers)).json()["data"]
    assert ticket["conversation_id"] == conv_id
    assert ticket["status"] == 0


async def test_已转人工的会话不再由AI作答(client: AsyncClient, auth_headers: dict, patch_llm):
    """这条分支不经过模型，因此不该被"LLM 不可用"拦住，也不该再消耗 token。"""
    conv_id = await create_conversation(client, auth_headers)
    await client.post(
        f"/api/v1/conversations/{conv_id}/handoff", json={"reason": "测试"}, headers=auth_headers
    )

    fake = patch_llm([[StreamChunk(content="这句不该出现")]])
    r = await client.post(
        "/api/v1/chat", json={"conversation_id": conv_id, "message": "在吗"}, headers=auth_headers
    )
    assert r.status_code == 200

    events = parse_sse(r.text)
    assert "notice" in event_types(events)
    assert "这句不该出现" not in joined_content(events)
    assert fake.calls == [], "已转人工的会话不该再调用模型"

    # 用户消息仍要入库（等客服接手时能看到）
    msgs = (
        await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers)
    ).json()["data"]["items"]
    assert any(m["sender_type"] == "user" and m["content"] == "在吗" for m in msgs)


# ── 错误分支 ────────────────────────────────────────────


async def test_会话不存在返回404(client: AsyncClient, auth_headers: dict):
    r = await client.post(
        "/api/v1/chat", json={"conversation_id": 999999, "message": "你好"}, headers=auth_headers
    )
    assert r.status_code == 404


async def test_LLM未配置时返回503(client: AsyncClient, auth_headers: dict, monkeypatch):
    """LLM 不可用要返回明确的 503，而不是让 SSE 里冒出一个半截错误。"""
    from app.modules.chat import router as chat_router
    from app.modules.chat import service as chat_service

    monkeypatch.setattr(chat_router, "is_llm_available", lambda: False)
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: False)

    conv_id = await create_conversation(client, auth_headers)
    r = await client.post(
        "/api/v1/chat", json={"conversation_id": conv_id, "message": "你好"}, headers=auth_headers
    )
    assert r.status_code == 503
