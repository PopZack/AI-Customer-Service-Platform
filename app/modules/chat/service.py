"""Chat 业务用例:会话 CRUD + AI 聊天(Agent + 工具 + 转人工)。

第 15/16 阶段后的链路:
    用户消息 → 保存 DB → 检查会话状态 → RAG 预注入拼 prompt
              → Agent 循环(可按需调工具:检索/查工单/建单/转人工)
              → 隐式转人工判定 → 产出 ChatEvent 流 → SSE 推前端

注意:SSE 场景下,DB session 生命周期必须由调用方管理(EventSourceResponse 返回后
FastAPI 依赖注入会关闭 session,但 AI 回复需要在流式结束后保存)。
"""
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent import (
    IMPLICIT_HANDOFF_THRESHOLD,
    Agent,
    empty_retrieval_count,
    record_retrieval_result,
    reset,
    should_handoff_implicitly,
)
from app.ai.prompt.system import build_rag_system_prompt, get_system_prompt
from app.ai.rag.config import MAX_CONTEXT_CHARS, RETRIEVAL_TOP_K
from app.ai.rag.retriever import build_context_block, retrieve
from app.ai.tools import ToolContext, request_handoff
from app.common.exceptions.handler import AppException
from app.config.settings import get_settings
from app.infrastructure.llm import is_llm_available
from app.models.conversation import ConversationStatus
from app.models.user_system import User
from app.modules.chat.repository.chat_repository import (
    ConversationRepository,
    MessageRepository,
)
from app.modules.chat.schemas import (
    ChatRequest,
    ConversationCreateRequest,
    ConversationResponse,
    MessageResponse,
)

logger = logging.getLogger(__name__)

#: 工具名 → 给用户看的中文提示(前端在工具执行期间展示)
_TOOL_LABELS = {
    "search_knowledge": "正在检索知识库…",
    "get_ticket": "正在查询工单…",
    "create_ticket": "正在创建工单…",
    "handoff_to_human": "正在转接人工客服…",
    "get_user_profile": "正在读取您的资料…",
}


def _tool_label(tool: str) -> str:
    return _TOOL_LABELS.get(tool, f"正在执行 {tool}…")


@dataclass
class ChatEvent:
    """聊天过程中的一个事件。

    由 router 翻译成 SSE 帧。刻意不用裸字符串 + 前缀标记的老做法 ——
    工具开始/结束、转人工这些结构化事件用字符串表达不了。
    """

    type: str  # content / tool_start / tool_end / notice / handoff / done
    content: str = ""
    tool: str = ""
    status: int | None = None
    ticket_id: int | None = None
    reply: str = ""


class ChatService:
    """聊天业务服务。"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.conv_repo = ConversationRepository(session)
        self.msg_repo = MessageRepository(session)

    # ── 会话 CRUD ────────────────────────────────────────

    async def create_conversation(
        self, user_id: int | None, req: ConversationCreateRequest
    ) -> ConversationResponse:
        """创建新会话。"""
        conv = await self.conv_repo.create(
            user_id=user_id,
            title=req.title,
            channel=req.channel,
            status=1,
        )
        return ConversationResponse.from_model(conv)

    async def list_conversations(self, user_id: int | None) -> list[ConversationResponse]:
        """查询用户的会话列表(按创建时间倒序)。"""
        convs = await self.conv_repo.list_by_user(user_id) if user_id else []
        convs_sorted = sorted(convs, key=lambda c: c.created_at, reverse=True)
        return [ConversationResponse.from_model(c) for c in convs_sorted]

    async def get_conversation(self, conversation_id: int) -> ConversationResponse:
        """查询会话详情。"""
        conv = await self.conv_repo.get_by_id(conversation_id)
        if conv is None:
            raise AppException(404, "会话不存在")
        return ConversationResponse.from_model(conv)

    async def list_messages(self, conversation_id: int) -> list[MessageResponse]:
        """查询会话的消息列表(按时间升序)。"""
        conv = await self.conv_repo.get_by_id(conversation_id)
        if conv is None:
            raise AppException(404, "会话不存在")
        msgs = await self.msg_repo.list_by_conversation(conversation_id)
        return [MessageResponse.model_validate(m) for m in msgs]

    # ── AI 聊天 ──────────────────────────────────────────

    async def chat(self, user_id: int | None, req: ChatRequest) -> AsyncGenerator[ChatEvent, None]:
        """AI 聊天(SSE 流式 generator)。

        链路:校验会话 → 保存用户消息 → 检查会话状态 → 拼 prompt(含 RAG 预注入)
              → 跑 Agent(可用工具)→ 隐式转人工判定

        产出 ChatEvent 流,由 router 翻译成 SSE 帧。
        AI 回复的落库由 router 的 event_generator 负责(它管理独立 session)。

        LLM 可用性的检查**放在"确实需要 AI 作答"之后** —— 已转人工的会话
        不该因为 LLM 没配就报错,那条分支根本不经过模型。
        """
        # 1. 校验会话
        conv = await self.conv_repo.get_by_id(req.conversation_id)
        if conv is None:
            raise AppException(404, "会话不存在")

        # 2. 保存用户消息
        await self.msg_repo.create(
            conversation_id=conv.id,
            sender_type="user",
            sender_id=user_id,
            content=req.message,
        )
        await self.session.commit()

        # 3. 已转人工的会话,AI 不再作答(消息仍入库,等客服处理)
        if conv.status in ConversationStatus.HUMAN_SIDE:
            yield ChatEvent(
                type="notice",
                content="当前会话已转人工客服,您的消息已记录,请等待客服回复。",
            )
            yield ChatEvent(type="done", status=conv.status)
            return

        # 4. 需要 AI 作答,才要求 LLM 可用
        if not is_llm_available():
            raise AppException(503, "LLM 未配置,无法进行 AI 聊天", http_status=503)

        # 5. 拼 prompt(RAG 预注入:常见问答题不必多花一次工具往返)
        system_prompt, pre_retrieval_empty = await self._build_system_prompt(req.message)
        messages = await self._build_llm_messages(conv.id, system_prompt)

        # 6. 记录本轮预检索结果,驱动隐式转人工计数
        await record_retrieval_result(conv.id, empty=pre_retrieval_empty)

        # 7. 跑 Agent
        user = await self.session.get(User, user_id) if user_id else None
        agent = Agent(self.session, conv.id, user=user)
        reply_parts: list[str] = []

        async for ev in agent.run(messages):
            if ev.type == "content":
                reply_parts.append(ev.content)
                yield ChatEvent(type="content", content=ev.content)
            elif ev.type == "tool_start":
                yield ChatEvent(type="tool_start", tool=ev.tool, content=_tool_label(ev.tool))
            elif ev.type == "tool_end":
                # 工具侧发现的空检索也要计入隐式判定
                if ev.retrieval_empty:
                    await record_retrieval_result(conv.id, empty=True)
                yield ChatEvent(type="tool_end", tool=ev.tool)
            elif ev.type == "notice":
                yield ChatEvent(type="notice", content=ev.content)

        # 8. 隐式转人工:连续 N 次检索为空 → 知识库确实覆盖不了,别再让 AI 硬答
        await self.session.refresh(conv)
        ticket_id = agent.ticket_created
        if agent.handoff_requested:
            yield ChatEvent(
                type="handoff",
                status=ConversationStatus.WAITING_HUMAN,
                ticket_id=ticket_id,
                content="已为您转接人工客服,请稍候。",
            )
            await reset(conv.id)
        elif conv.status not in ConversationStatus.HUMAN_SIDE and await should_handoff_implicitly(conv.id):
            result = await request_handoff(
                ToolContext(session=self.session, conversation_id=conv.id, user=user),
                reason=f"连续 {IMPLICIT_HANDOFF_THRESHOLD} 次未在知识库检索到相关资料",
            )
            ticket_id = result.ticket_created
            notice = "很抱歉,知识库暂时无法解答您的问题,已为您转接人工客服。"
            yield ChatEvent(type="content", content=notice)
            yield ChatEvent(
                type="handoff",
                status=ConversationStatus.WAITING_HUMAN,
                ticket_id=ticket_id,
                content=notice,
            )
            await reset(conv.id)

        # 9. 把会话最新状态回传,前端据此切换 UI(显示"等待人工"/"人工接管")
        await self.session.refresh(conv)
        yield ChatEvent(type="done", status=conv.status, reply="".join(reply_parts))

    # ── 显式转人工(用户点按钮)──────────────────────────

    async def handoff(self, user_id: int | None, conversation_id: int, reason: str = "") -> dict:
        """显式转人工:用户主动点「转人工」按钮。

        与隐式判定共用 request_handoff,保证落库形态一致。
        """
        conv = await self.conv_repo.get_by_id(conversation_id)
        if conv is None:
            raise AppException(404, "会话不存在")

        user = await self.session.get(User, user_id) if user_id else None
        result = await request_handoff(
            ToolContext(session=self.session, conversation_id=conv.id, user=user),
            reason=reason.strip() or f"用户 {user.username if user else '匿名'} 主动请求人工客服",
        )
        if not result.ok:
            raise AppException(400, result.content)

        await reset(conv.id)
        await self.session.refresh(conv)
        return {
            "conversation_id": conv.id,
            "status": conv.status,
            "status_text": ConversationStatus.TEXT.get(conv.status, "未知"),
            "ticket_id": result.ticket_created,
        }

    async def get_handoff_signal(self, conversation_id: int) -> dict:
        """当前会话的转人工相关状态(前端展示/调试用)。"""
        conv = await self.conv_repo.get_by_id(conversation_id)
        if conv is None:
            raise AppException(404, "会话不存在")
        return {
            "conversation_id": conv.id,
            "status": conv.status,
            "status_text": ConversationStatus.TEXT.get(conv.status, "未知"),
            "empty_retrieval_count": await empty_retrieval_count(conv.id),
            "threshold": IMPLICIT_HANDOFF_THRESHOLD,
        }

    # ── 内部:构建 LLM messages ────────────────────────────

    async def _build_llm_messages(
        self, conversation_id: int, system_prompt: str
    ) -> list[dict[str, Any]]:
        """构建发送给 LLM 的 messages 列表。

        system_prompt 由调用方拼好传入(其中已含 RAG 预注入的参考资料),
        这样「检索」与「拼 messages」两个职责分开,便于单测。
        """
        settings = get_settings()
        history = await self.msg_repo.list_by_conversation(conversation_id)

        # 截取最近 N 条
        history = history[-settings.LLM_MAX_CONTEXT_MESSAGES :]

        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

        for msg in history:
            if msg.sender_type == "user":
                messages.append({"role": "user", "content": msg.content})
            elif msg.sender_type == "ai":
                messages.append({"role": "assistant", "content": msg.content})

        return messages

    async def _build_system_prompt(self, question: str) -> tuple[str, bool]:
        """带知识库检索的系统提示词。返回 (提示词, 本轮检索是否为空)。

        检索失败不致命:降级为不带资料的基础提示词,聊天仍可用
        (与 LLM 未配置时返回 503 的处理取舍不同 —— 检索是增强,不是前提)。
        """
        try:
            chunks = await retrieve(self.session, question, top_k=RETRIEVAL_TOP_K)
        except Exception:
            logger.exception("知识库检索失败,本轮降级为无资料回答")
            return get_system_prompt(), True

        if not chunks:
            # 这个信号会驱动隐式转人工(连续 N 次为空 → 转人工)
            logger.info("知识库无命中: %s", question[:40])
            return get_system_prompt(), True

        context = build_context_block(chunks, MAX_CONTEXT_CHARS)
        logger.info("知识库命中 %s 块,注入上下文 %s 字", len(chunks), len(context))
        return build_rag_system_prompt(context), False
