"""Agent 循环单测:用假 LLM 驱动脚本化的工具调用,确定性验证循环逻辑。

为什么不接真 LLM:
  1. 本地/CI 都不该依赖 API key;
  2. 更根本的原因 —— 真 LLM 输出不确定,而这里要验证的是**循环本身**
     (增量累积、工具结果回填、最大轮数保护、转人工短路)。
     用假 LLM 才能把每种分支稳定复现出来。

这套假 LLM 同时覆盖了最容易写错的一点:**流式 tool_calls 必须按 index 跨 chunk 累积**。
OpenAI 兼容接口把一次工具调用切成多个 chunk 下发,id 和函数名往往只在第一个 chunk 出现,
arguments 是被切碎的 JSON 字符串 —— 这里就按这个最坏情况来造数据。
"""
from typing import Any

import pytest

from app.ai.agent import agent as agent_module
from app.ai.agent.agent import Agent
from app.ai.tools.executor import ToolResult
from app.infrastructure.llm import StreamChunk, ToolCallDelta

# ── 测试替身 ────────────────────────────────────────────


class FakeLLM:
    """按轮次脚本化的假 LLM。

    每次被调用消耗一轮脚本;调用记录里会保留 messages 与 tools,
    便于断言「工具结果是否回填进对话」「收尾轮是否禁用了工具」。
    """

    def __init__(self, rounds: list[list[StreamChunk]]):
        self._rounds = list(rounds)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, messages, *, tools=None, **kwargs):
        self.calls.append({"messages": list(messages), "tools": tools})

        script = self._rounds.pop(0) if self._rounds else []

        async def gen():
            for chunk in script:
                yield chunk

        return gen()


class RecordingExecutor:
    """记录调用并按名字返回预设结果的假工具执行器。"""

    def __init__(self, results: dict[str, ToolResult] | None = None):
        self.results = results or {}
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, name: str, arguments: dict, ctx) -> ToolResult:
        self.calls.append((name, arguments))
        return self.results.get(name, ToolResult(f"[{name} 的执行结果]"))


@pytest.fixture
def patch_llm(monkeypatch):
    """注入假 LLM,返回设置函数的夹具。"""

    def _apply(fake: FakeLLM) -> FakeLLM:
        monkeypatch.setattr(agent_module, "chat_stream_with_tools", fake)
        return fake

    return _apply


@pytest.fixture
def patch_tools(monkeypatch):
    """注入假工具执行器。"""

    def _apply(executor: RecordingExecutor) -> RecordingExecutor:
        monkeypatch.setattr(agent_module, "execute_tool", executor)
        return executor

    return _apply


def _content(text: str) -> StreamChunk:
    return StreamChunk(content=text)


def _tool_call_fragments(
    index: int, call_id: str, name: str, arguments: str, pieces: int = 3
) -> list[StreamChunk]:
    """把一次工具调用切成 pieces 个 chunk —— 模拟真实流式下发的碎片化。

    第一个 chunk 带 id 与函数名,arguments 均分到各个 chunk。
    """
    size = max(1, len(arguments) // pieces)
    parts = [arguments[i : i + size] for i in range(0, len(arguments), size)]
    chunks = [StreamChunk(tool_call=ToolCallDelta(index=index, id=call_id, name=name))]
    chunks.extend(StreamChunk(tool_call=ToolCallDelta(index=index, arguments=p)) for p in parts)
    return chunks


async def _collect(agent: Agent, messages: list[dict]) -> list:
    return [ev async for ev in agent.run(messages)]


# ── 用例 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_没有工具调用时直接流式作答(patch_llm):
    """模型不需要工具 → 文本直接流出,不进入第二轮,不产生任何工具调用。"""
    fake = patch_llm(FakeLLM([[ _content("退款"), _content("一般 3 到 5 个工作日到账。") ]]))
    agent = Agent(session=None, conversation_id=1)

    events = await _collect(agent, [{"role": "user", "content": "退款多久到账"}])

    assert [e.type for e in events] == ["content", "content", "done"]
    assert "".join(e.content for e in events if e.type == "content") == "退款一般 3 到 5 个工作日到账。"
    assert agent.tool_calls_made == 0
    assert len(fake.calls) == 1
    # 第一轮应带上工具定义(否则模型无从选择)
    assert fake.calls[0]["tools"] is not None


@pytest.mark.asyncio
async def test_工具调用参数跨chunk累积(patch_llm, patch_tools):
    """核心用例:arguments 被切成多段下发时,必须拼成完整合法 JSON 才能执行。"""
    arguments = '{"query": "退款到账时间", "top_k": 3}'
    round1 = [
        _content("让我查一下。"),
        *_tool_call_fragments(0, "call_abc", "search_knowledge", arguments, pieces=4),
    ]
    fake = patch_llm(FakeLLM([round1, [_content("根据资料,退款 3 到 5 个工作日到账[1]。")]]))
    executor = patch_tools(RecordingExecutor())

    agent = Agent(session=None, conversation_id=7)
    events = await _collect(agent, [{"role": "user", "content": "退款多久到账"}])

    # 工具被正确调用,且参数完整解析出来了
    assert len(executor.calls) == 1
    name, args = executor.calls[0]
    assert name == "search_knowledge"
    assert args == {"query": "退款到账时间", "top_k": 3}, f"参数未正确累积: {args!r}"

    # 第二轮:工具结果必须作为 role=tool 回填,否则模型下一轮看不到检索内容
    second_messages = fake.calls[1]["messages"]
    tool_msgs = [m for m in second_messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "call_abc"
    assert tool_msgs[0]["content"] == "[search_knowledge 的执行结果]"

    # assistant 的 tool_calls 也要回填,否则模型不知道自己调用过
    assistant_msgs = [m for m in second_messages if m.get("role") == "assistant"]
    assert assistant_msgs[-1]["tool_calls"][0]["function"]["name"] == "search_knowledge"

    # 事件序列:先文本,再工具开始/结束,再最终回答
    types = [e.type for e in events]
    assert types == ["content", "tool_start", "tool_end", "content", "done"]
    assert agent.tool_calls_made == 1


@pytest.mark.asyncio
async def test_最大轮数保护会强制收尾(patch_llm, patch_tools):
    """模型反复调工具时,不能无限循环:达到上限必须禁用工具强制给出答案。"""
    def tool_round() -> list[StreamChunk]:
        return _tool_call_fragments(0, "call_loop", "search_knowledge", '{"query": "x"}', pieces=1)

    fake = patch_llm(FakeLLM([tool_round(), tool_round(), [_content("最终答案")]]))
    executor = patch_tools(RecordingExecutor())

    agent = Agent(session=None, conversation_id=2, max_steps=2)
    events = await _collect(agent, [{"role": "user", "content": "问题"}])

    # 只跑了 max_steps 轮工具
    assert agent.tool_calls_made == 2
    assert len(executor.calls) == 2

    # 收尾那一次调用必须 tools=None(禁用工具),否则模型又会去调工具
    assert fake.calls[-1]["tools"] is None

    # 必须有提示 + 最终答案,不能让用户看到"我还在调工具"
    notices = [e.content for e in events if e.type == "notice"]
    assert any("上限" in n for n in notices), notices
    assert "".join(e.content for e in events if e.type == "content") == "最终答案"
    assert events[-1].type == "done"


@pytest.mark.asyncio
async def test_转人工后短路并收尾(patch_llm, patch_tools):
    """工具完成转人工 → 不再继续调工具,直接让模型给出给用户的交代。"""
    round1 = _tool_call_fragments(
        0, "call_ho", "handoff_to_human", '{"reason": "用户要求人工"}', pieces=2
    )
    fake = patch_llm(FakeLLM([round1, [_content("已为您转接人工客服，请稍候。")]]))
    executor = patch_tools(
        RecordingExecutor(
            {"handoff_to_human": ToolResult("已转人工", handoff_requested=True, ticket_created=42)}
        )
    )

    agent = Agent(session=None, conversation_id=3)
    events = await _collect(agent, [{"role": "user", "content": "我要人工"}])

    # 转人工工具的 reason 参数同样要跨 chunk 累积正确
    assert executor.calls == [("handoff_to_human", {"reason": "用户要求人工"})]
    assert agent.handoff_requested is True
    assert agent.ticket_created == 42
    # 转人工后只应有收尾那一次调用(共 2 次),且收尾禁用工具
    assert len(fake.calls) == 2
    assert fake.calls[-1]["tools"] is None
    assert events[-1].type == "done"
    # tool_end 事件要带上转人工标记,供上层决定会话状态
    tool_end = [e for e in events if e.type == "tool_end"]
    assert tool_end and tool_end[0].handoff_requested is True


@pytest.mark.asyncio
async def test_空检索会打标并累计(patch_llm, patch_tools):
    """检索为空的标记必须透传,它是隐式转人工的判定信号。"""
    round1 = _tool_call_fragments(0, "call_s", "search_knowledge", '{"query": "不知道的事"}', pieces=1)
    patch_llm(FakeLLM([round1, [_content("抱歉,没找到相关资料。")]]))
    executor = patch_tools(
        RecordingExecutor({"search_knowledge": ToolResult("没有找到", retrieval_empty=True)})
    )

    agent = Agent(session=None, conversation_id=4)
    await _collect(agent, [{"role": "user", "content": "问个偏门问题"}])

    # 工具确实被调用过(否则 retrieval_empty 无从谈起)
    assert [name for name, _ in executor.calls] == ["search_knowledge"]
    assert agent.any_retrieval is True
    assert agent.any_retrieval_empty is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", {}),
        ("   ", {}),
        ("not-json", {}),
        ('{"a": 1}', {"a": 1}),
        ("[1,2,3]", {}),  # 顶层不是对象 → 视为无效
    ],
)
def test_工具参数解析对脏数据健壮(raw, expected):
    """模型可能给出截断/非法 JSON,解析失败要降级为空参而不是抛异常。"""
    assert Agent._parse_args(raw) == expected
