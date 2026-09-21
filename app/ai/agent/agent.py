"""Agent:带工具调用的对话循环(第 15 阶段 V7)。

与 M1 的关系不是替代而是叠加:
  - M1 的「检索结果预先拼进 system prompt」仍是第一跳 —— 常见问答题不必多花一次工具往返;
  - 本 Agent 让模型在需要时**主动**调工具(换措辞再检索、查工单、建单、转人工)。

循环形态:**流式 + 按 index 累积工具调用增量**。
不用非流式做工具轮的原因:非流式要等整轮生成完才返回,多轮工具调用会让用户干等几十秒。
流式下模型先说的思考文字可以立刻推给用户,工具参数则累积到完整再执行。

安全边界:
  - `MAX_STEPS` 限制轮数,防止模型在两个工具之间来回打转烧 token;
  - 达到上限时**带 tools=None 强制收尾**,让模型必须给出文本答案,而不是把
    "我还在调工具"直接抛给用户;
  - 工具参数来自模型输出,归属校验放在 executor 内(见 executor 注释)。
"""
import json
import logging
from collections import defaultdict
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.definitions import TOOL_DEFINITIONS
from app.ai.tools.executor import ToolContext, execute_tool
from app.infrastructure.llm import chat_stream_with_tools
from app.models.user_system import User

logger = logging.getLogger(__name__)

#: 单轮对话最多允许几轮工具调用
MAX_STEPS = 5


@dataclass
class AgentEvent:
    """Agent 执行过程中的事件,由 ChatService 翻译成 SSE 帧。"""

    type: str  # content / tool_start / tool_end / notice / done
    content: str = ""
    tool: str = ""
    #: 本次事件是否导致会话转人工
    handoff_requested: bool = False
    #: 本次事件是否新建了工单
    ticket_created: int | None = None
    #: 本次工具检索是否为空(隐式转人工的判定信号)
    retrieval_empty: bool = False


class _ToolCallAccumulator:
    """按 index 累积一次工具调用的片段。"""

    __slots__ = ("arguments", "id", "name")

    def __init__(self) -> None:
        self.id: str | None = None
        self.name: str | None = None
        self.arguments = ""


class Agent:
    """工具调用 Agent。一次实例对应一轮用户消息的处理。"""

    def __init__(
        self,
        session: AsyncSession,
        conversation_id: int,
        user: User | None = None,
        max_steps: int = MAX_STEPS,
    ):
        self.session = session
        self.conversation_id = conversation_id
        self.ctx = ToolContext(session=session, conversation_id=conversation_id, user=user)
        self.max_steps = max_steps

        # ── 执行结果汇总(供 ChatService 决定后续动作)──
        self.handoff_requested = False
        self.ticket_created: int | None = None
        self.tool_calls_made = 0
        self.any_retrieval = False
        self.any_retrieval_empty = False

    async def run(self, messages: list[dict[str, Any]]) -> AsyncGenerator[AgentEvent, None]:
        """执行对话循环。yield 过程事件;文本增量通过 type='content' 事件给出。"""
        working: list[dict[str, Any]] = list(messages)
        finalize_reason: str | None = None

        for step in range(self.max_steps):
            accs: dict[int, _ToolCallAccumulator] = defaultdict(_ToolCallAccumulator)
            text = ""

            async for chunk in chat_stream_with_tools(working, tools=TOOL_DEFINITIONS):
                if chunk.content:
                    text += chunk.content
                    yield AgentEvent("content", content=chunk.content)
                if chunk.tool_call:
                    acc = accs[chunk.tool_call.index]
                    if chunk.tool_call.id:
                        acc.id = chunk.tool_call.id
                    if chunk.tool_call.name:
                        acc.name = chunk.tool_call.name
                    if chunk.tool_call.arguments:
                        acc.arguments += chunk.tool_call.arguments

            if not accs:
                # 本轮没有工具调用 → 刚才流出的文本就是最终回答
                yield AgentEvent("done")
                return

            # ── 把这一轮的 assistant 工具调用写回对话,否则模型下一轮不知道发生过什么 ──
            working.append(
                {
                    "role": "assistant",
                    "content": text or None,
                    "tool_calls": [
                        {
                            "id": acc.id or f"call_{idx}",
                            "type": "function",
                            "function": {"name": acc.name or "", "arguments": acc.arguments or "{}"},
                        }
                        for idx, acc in sorted(accs.items())
                    ],
                }
            )

            for idx, acc in sorted(accs.items()):
                name = acc.name or ""
                self.tool_calls_made += 1
                yield AgentEvent("tool_start", tool=name)

                result = await execute_tool(name, self._parse_args(acc.arguments), self.ctx)

                if name == "search_knowledge":
                    self.any_retrieval = True
                    if result.retrieval_empty:
                        self.any_retrieval_empty = True
                if result.handoff_requested:
                    self.handoff_requested = True
                if result.ticket_created is not None:
                    self.ticket_created = result.ticket_created

                working.append(
                    {
                        "role": "tool",
                        "tool_call_id": acc.id or f"call_{idx}",
                        "content": result.content,
                    }
                )
                yield AgentEvent(
                    "tool_end",
                    tool=name,
                    content=result.content,
                    handoff_requested=result.handoff_requested,
                    ticket_created=result.ticket_created,
                    retrieval_empty=result.retrieval_empty,
                )

            if self.handoff_requested:
                # 已转人工:让模型再出一句"已为您转接人工"给用户,然后就结束
                finalize_reason = "handoff"
                break
        else:
            finalize_reason = "max_steps"
            logger.warning(
                "会话 %s 达到工具调用轮数上限(%s),强制收尾", self.conversation_id, self.max_steps
            )

        # ── 收尾:不带工具再调一次,强制模型给出文本答案 ──
        if finalize_reason == "max_steps":
            yield AgentEvent("notice", content="（已达到工具调用轮数上限，直接作答）")
        try:
            async for chunk in chat_stream_with_tools(working, tools=None):
                if chunk.content:
                    yield AgentEvent("content", content=chunk.content)
        except Exception:
            logger.exception("会话 %s 收尾生成失败", self.conversation_id)
        yield AgentEvent("done")

    @staticmethod
    def _parse_args(raw: str) -> dict[str, Any]:
        """解析模型给出的工具参数 JSON。解析失败返回空字典,由 executor 报参数缺失。"""
        if not raw or not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("工具参数不是合法 JSON,已忽略:%s", raw[:200])
            return {}
        return parsed if isinstance(parsed, dict) else {}
