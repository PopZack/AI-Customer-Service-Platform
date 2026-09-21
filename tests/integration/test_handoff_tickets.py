"""转人工与工单闭环集成测试（Phase 16）。

覆盖两条转人工路径：
  - 显式：用户调 /handoff 接口（AI 工具触发的路径在 test_chat_sse.py 里覆盖）
  - 隐式：连续 N 次检索为空（用真实 Redis 计数验证）

以及工单的完整生命周期：建单 → 认领 → 回复（双写）→ 关单。
"""
import uuid

from httpx import AsyncClient

from app.ai.agent import agent as agent_module
from app.ai.agent.handoff import IMPLICIT_HANDOFF_THRESHOLD
from app.infrastructure.llm import StreamChunk
from tests.integration.helpers import create_conversation, event_types, parse_sse


def _fake_llm(rounds: list[list[StreamChunk]]):
    remaining = list(rounds)

    def fake(messages, *, tools=None, **kwargs):
        async def gen():
            for chunk in remaining.pop(0) if remaining else []:
                yield chunk

        return gen()

    return fake


async def _handoff(client: AsyncClient, headers: dict, conv_id: int, reason: str = "测试") -> dict:
    r = await client.post(
        f"/api/v1/conversations/{conv_id}/handoff", json={"reason": reason}, headers=headers
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


async def _conv(client: AsyncClient, headers: dict, conv_id: int) -> dict:
    return (await client.get(f"/api/v1/conversations/{conv_id}", headers=headers)).json()["data"]


# ── 显式转人工 ──────────────────────────────────────────


async def test_显式转人工改状态并自动建单(client: AsyncClient, auth_headers: dict):
    conv_id = await create_conversation(client, auth_headers)
    data = await _handoff(client, auth_headers, conv_id, "客户要求人工处理退款纠纷")

    assert data["status"] == 2
    assert data["status_text"] == "等待人工"
    assert data["ticket_id"], "转人工必须同时建单"

    assert (await _conv(client, auth_headers, conv_id))["status"] == 2

    ticket = (
        await client.get(f"/api/v1/tickets/{data['ticket_id']}", headers=auth_headers)
    ).json()["data"]
    assert ticket["conversation_id"] == conv_id
    assert ticket["status"] == 0, "新建工单应为「待处理」"
    # 转人工动作本身要留痕在工单往来记录里
    assert any(m["sender_type"] == "system" for m in ticket["messages"])


async def test_转人工会在对话流里留下系统消息(client: AsyncClient, auth_headers: dict):
    conv_id = await create_conversation(client, auth_headers)
    await _handoff(client, auth_headers, conv_id)

    msgs = (
        await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers)
    ).json()["data"]["items"]
    assert any(m["sender_type"] == "system" and "转人工" in m["content"] for m in msgs)


async def test_重复转人工不会重复建单(client: AsyncClient, auth_headers: dict):
    """转人工必须幂等：否则用户多点两次就会堆出一串工单。"""
    conv_id = await create_conversation(client, auth_headers)
    first = await _handoff(client, auth_headers, conv_id)
    second = await _handoff(client, auth_headers, conv_id)

    assert first["ticket_id"] == second["ticket_id"], "重复转人工又建了新单"

    tickets = (await client.get("/api/v1/tickets", headers=auth_headers)).json()["data"]["items"]
    assert len([t for t in tickets if t["conversation_id"] == conv_id]) == 1


async def test_转人工信号接口(client: AsyncClient, auth_headers: dict):
    conv_id = await create_conversation(client, auth_headers)
    r = await client.get(
        f"/api/v1/conversations/{conv_id}/handoff-signal", headers=auth_headers
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["threshold"] == IMPLICIT_HANDOFF_THRESHOLD
    assert body["empty_retrieval_count"] == 0


# ── 隐式转人工 ──────────────────────────────────────────


async def test_连续空检索会自动转人工(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """知识库里什么都没有时，连续问 N 次就应自动转人工，而不是一直硬答。

    这条走的是真实 Redis 计数，是 M2 隐式转人工的端到端验证。
    """
    conv_id = await create_conversation(client, auth_headers)
    monkeypatch.setattr(
        agent_module, "chat_stream_with_tools", _fake_llm([[StreamChunk(content="不知道")]] * 5)
    )

    last_events: list[dict] = []
    for i in range(IMPLICIT_HANDOFF_THRESHOLD):
        r = await client.post(
            "/api/v1/chat",
            json={"conversation_id": conv_id, "message": f"冷门问题{i}"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        last_events = parse_sse(r.text)

        signal = (
            await client.get(
                f"/api/v1/conversations/{conv_id}/handoff-signal", headers=auth_headers
            )
        ).json()["data"]
        if i < IMPLICIT_HANDOFF_THRESHOLD - 1:
            assert signal["empty_retrieval_count"] == i + 1, "空检索应被累计"
            assert signal["status"] == 1, "还没到阈值,不该转人工"

    # 第 N 次之后应已转人工
    assert "handoff" in event_types(last_events), f"达到阈值未转人工: {event_types(last_events)}"
    handoff = next(e for e in last_events if e["type"] == "handoff")
    assert handoff["status"] == 2
    assert handoff["ticket_id"]

    conv = await _conv(client, auth_headers, conv_id)
    assert conv["status"] == 2

    # 转人工后计数应被清空，避免后续再次触发
    signal = (
        await client.get(f"/api/v1/conversations/{conv_id}/handoff-signal", headers=auth_headers)
    ).json()["data"]
    assert signal["empty_retrieval_count"] == 0


async def test_检索命中会清零连续计数(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """打断一次就该重新计数 —— 否则用户"偶尔问到偏门问题"会累积误转人工。"""
    from tests.integration.helpers import SAMPLE_DOC, create_kb, upload_and_wait

    conv_id = await create_conversation(client, auth_headers)
    # 先问两次命中不了的（此时库是空的）
    monkeypatch.setattr(
        agent_module, "chat_stream_with_tools", _fake_llm([[StreamChunk(content="不知道")]] * 5)
    )
    for i in range(2):
        await client.post(
            "/api/v1/chat",
            json={"conversation_id": conv_id, "message": f"冷门{i}"},
            headers=auth_headers,
        )
    before = (
        await client.get(
            f"/api/v1/conversations/{conv_id}/handoff-signal", headers=auth_headers
        )
    ).json()["data"]["empty_retrieval_count"]
    assert before == 2

    # 建知识库并上传文档后，这次提问能检索到 → 计数应清零
    kb_id = await create_kb(client, auth_headers)
    await upload_and_wait(client, auth_headers, kb_id, content=SAMPLE_DOC)

    await client.post(
        "/api/v1/chat", json={"conversation_id": conv_id, "message": "退款多久到账"}, headers=auth_headers
    )
    after = (
        await client.get(
            f"/api/v1/conversations/{conv_id}/handoff-signal", headers=auth_headers
        )
    ).json()["data"]["empty_retrieval_count"]
    assert after == 0, "检索命中后连续空计数必须归零"


# ── 工单生命周期 ────────────────────────────────────────


async def test_工单列表带问题摘要(client: AsyncClient, auth_headers: dict):
    """工单表本身没有标题字段，摘要来自首条消息 —— 客服列表靠它辨认问题。"""
    conv_id = await create_conversation(client, auth_headers)
    data = await _handoff(client, auth_headers, conv_id, "客户投诉物流太慢")

    items = (await client.get("/api/v1/tickets", headers=auth_headers)).json()["data"]["items"]
    target = next(t for t in items if t["id"] == data["ticket_id"])
    assert target["summary"], "列表必须给出摘要,否则客服看不出这单是什么问题"
    assert "物流太慢" in target["summary"]
    assert target["status_text"] == "待处理"
    assert target["priority_text"]


async def test_认领会把会话推进到人工接管(client: AsyncClient, auth_headers: dict):
    conv_id = await create_conversation(client, auth_headers)
    ticket_id = (await _handoff(client, auth_headers, conv_id))["ticket_id"]

    # 不传 agent_id = 认领给自己
    r = await client.post(f"/api/v1/tickets/{ticket_id}/assign", json={}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == 1, "认领后工单应为「处理中」"
    assert r.json()["data"]["assigned_user"] is not None

    assert (await _conv(client, auth_headers, conv_id))["status"] == 3, "会话应进入「人工接管」"


async def test_人工回复是双写的(client: AsyncClient, auth_headers: dict):
    """核心断言：客服的回复既要进工单留痕，也要进会话让用户看到。"""
    conv_id = await create_conversation(client, auth_headers)
    ticket_id = (await _handoff(client, auth_headers, conv_id))["ticket_id"]
    await client.post(f"/api/v1/tickets/{ticket_id}/assign", json={}, headers=auth_headers)

    reply = "您好,已核实订单,退款将在 2 个工作日内到账。"
    r = await client.post(
        f"/api/v1/tickets/{ticket_id}/reply", json={"content": reply}, headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["data"]["sender_type"] == "human"

    # ① 工单侧留痕
    ticket = (
        await client.get(f"/api/v1/tickets/{ticket_id}", headers=auth_headers)
    ).json()["data"]
    assert any(m["sender_type"] == "human" and m["content"] == reply for m in ticket["messages"])

    # ② 会话侧可见（用户在自己的聊天窗口能看到）
    msgs = (
        await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers)
    ).json()["data"]["items"]
    assert any(
        m["sender_type"] == "human" and m["content"] == reply for m in msgs
    ), "客服回复没有写进会话消息流,用户会看不到"


async def test_未指派时回复即认领(client: AsyncClient, auth_headers: dict):
    """省掉"先认领再回复"的一步操作 —— 客服直接答就等于接管。"""
    conv_id = await create_conversation(client, auth_headers)
    ticket_id = (await _handoff(client, auth_headers, conv_id))["ticket_id"]

    r = await client.post(
        f"/api/v1/tickets/{ticket_id}/reply", json={"content": "我来处理"}, headers=auth_headers
    )
    assert r.status_code == 200

    ticket = (
        await client.get(f"/api/v1/tickets/{ticket_id}", headers=auth_headers)
    ).json()["data"]
    assert ticket["assigned_user"] is not None
    assert ticket["status"] == 1


async def test_非指派客服不能回复(client: AsyncClient, auth_headers: dict, client2=None):
    """工具与接口的权限边界：A 认领的单，B 不能替他回复。"""
    conv_id = await create_conversation(client, auth_headers)
    ticket_id = (await _handoff(client, auth_headers, conv_id))["ticket_id"]

    # 让另一个用户认领
    other = f"u{uuid.uuid4().hex[:12]}"
    await client.post("/api/v1/auth/register", json={"username": other, "password": "test123456"})
    other_token = (
        await client.post(
            "/api/v1/auth/login", json={"username": other, "password": "test123456"}
        )
    ).json()["data"]["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    await client.post(
        f"/api/v1/tickets/{ticket_id}/assign", json={}, headers=other_headers
    )

    # 原用户（非指派）回复应被拒
    r = await client.post(
        f"/api/v1/tickets/{ticket_id}/reply", json={"content": "我插一句"}, headers=auth_headers
    )
    assert r.status_code == 403


async def test_关单会结束会话且不可再操作(client: AsyncClient, auth_headers: dict):
    conv_id = await create_conversation(client, auth_headers)
    ticket_id = (await _handoff(client, auth_headers, conv_id))["ticket_id"]
    await client.post(f"/api/v1/tickets/{ticket_id}/assign", json={}, headers=auth_headers)

    r = await client.post(
        f"/api/v1/tickets/{ticket_id}/close", json={"resolution": "已退款"}, headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["data"]["status"] == 2, "关单后工单应为「已完成」"

    conv = await _conv(client, auth_headers, conv_id)
    assert conv["status"] == 0
    assert conv["status_text"] == "已结束"

    # 关单后不能再回复/指派
    assert (
        await client.post(
            f"/api/v1/tickets/{ticket_id}/reply", json={"content": "x"}, headers=auth_headers
        )
    ).status_code == 400
    assert (
        await client.post(
            f"/api/v1/tickets/{ticket_id}/assign", json={}, headers=auth_headers
        )
    ).status_code == 400
    # 重复关单也应被拒（不是静默成功）
    assert (
        await client.post(
            f"/api/v1/tickets/{ticket_id}/close", json={}, headers=auth_headers
        )
    ).status_code == 400


async def test_按状态筛选工单(client: AsyncClient, auth_headers: dict):
    pending_conv = await create_conversation(client, auth_headers)
    pending_ticket = (await _handoff(client, auth_headers, pending_conv))["ticket_id"]

    done_conv = await create_conversation(client, auth_headers)
    done_ticket = (await _handoff(client, auth_headers, done_conv))["ticket_id"]
    await client.post(f"/api/v1/tickets/{done_ticket}/close", json={}, headers=auth_headers)

    pending = (
        await client.get("/api/v1/tickets?status=0", headers=auth_headers)
    ).json()["data"]["items"]
    assert pending_ticket in [t["id"] for t in pending]
    assert done_ticket not in [t["id"] for t in pending], "已完成的单不该出现在待处理队列里"

    unassigned = (
        await client.get("/api/v1/tickets?assigned_user=0", headers=auth_headers)
    ).json()["data"]["items"]
    assert pending_ticket in [t["id"] for t in unassigned]


async def test_不存在的工单返回404(client: AsyncClient, auth_headers: dict):
    assert (await client.get("/api/v1/tickets/999999", headers=auth_headers)).status_code == 404
    assert (
        await client.post("/api/v1/tickets/999999/assign", json={}, headers=auth_headers)
    ).status_code == 404
    assert (
        await client.post(
            "/api/v1/tickets/999999/reply", json={"content": "x"}, headers=auth_headers
        )
    ).status_code == 404


async def test_工单接口也需要认证(client: AsyncClient):
    assert (await client.get("/api/v1/tickets")).status_code == 401
    assert (
        await client.post("/api/v1/tickets/1/reply", json={"content": "x"})
    ).status_code == 401
