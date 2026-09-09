"""Chat 业务用例:会话 CRUD + AI 聊天(带上下文 + SSE 流式)。

链路:
    用户消息 → 保存 DB → 加载历史 → 拼 prompt → LLM 流式 → SSE 推前端
                                          ↓
                                    保存 AI 回复

注意:SSE 场景下,DB session 生命周期必须由调用方管理(EventSourceResponse 返回后
FastAPI 依赖注入会关闭 session,但 AI 回复需要在流式结束后保存)。
"""
from typing import AsyncGenerator

from openai.types.chat import ChatCompletionMessageParam
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompt.system import get_system_prompt
from app.common.exceptions.handler import AppException
from app.config.settings import get_settings
from app.infrastructure.llm import chat_stream, is_llm_available
from app.models.conversation import Conversation, Message
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
        return ConversationResponse.model_validate(conv)

    async def list_conversations(self, user_id: int | None) -> list[ConversationResponse]:
        """查询用户的会话列表(按创建时间倒序)。"""
        convs = await self.conv_repo.list_by_user(user_id) if user_id else []
        convs_sorted = sorted(convs, key=lambda c: c.created_at, reverse=True)
        return [ConversationResponse.model_validate(c) for c in convs_sorted]

    async def get_conversation(self, conversation_id: int) -> ConversationResponse:
        """查询会话详情。"""
        conv = await self.conv_repo.get_by_id(conversation_id)
        if conv is None:
            raise AppException(404, "会话不存在")
        return ConversationResponse.model_validate(conv)

    async def list_messages(self, conversation_id: int) -> list[MessageResponse]:
        """查询会话的消息列表(按时间升序)。"""
        conv = await self.conv_repo.get_by_id(conversation_id)
        if conv is None:
            raise AppException(404, "会话不存在")
        msgs = await self.msg_repo.list_by_conversation(conversation_id)
        return [MessageResponse.model_validate(m) for m in msgs]

    # ── AI 聊天 ──────────────────────────────────────────

    async def chat(
        self, user_id: int | None, req: ChatRequest
    ) -> AsyncGenerator[str, None]:
        """AI 聊天(SSE 流式 generator)。

        负责:校验会话 → 保存用户消息 → 加载历史 → 拼 prompt → 调 LLM 流式。
        注意:AI 回复的保存由 router 的 event_generator 负责,因为它管理着独立的 session。

        流式过程中如果 LLM 调用失败,会 yield 错误标记串让前端识别。
        """
        if not is_llm_available():
            raise AppException(503, "LLM 未配置,无法进行 AI 聊天", http_status=503)

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

        # 3+4. 加载历史 + 拼 messages
        messages = await self._build_llm_messages(conv.id, req.message)

        # 5. 流式调用 LLM
        try:
            async for chunk in chat_stream(messages):
                yield chunk
        except Exception as e:
            # 失败时 yield 特殊标记,由 router 识别后发 error SSE 事件
            yield f"[AI_ERROR]{e}[/AI_ERROR]"

    # ── 内部:构建 LLM messages ────────────────────────────

    async def _build_llm_messages(
        self, conversation_id: int, current_user_message: str
    ) -> list[ChatCompletionMessageParam]:
        """构建发送给 LLM 的 messages 列表。"""
        settings = get_settings()
        history = await self.msg_repo.list_by_conversation(conversation_id)

        # 截取最近 N 条
        history = history[-settings.LLM_MAX_CONTEXT_MESSAGES :]

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": get_system_prompt()}
        ]

        for msg in history:
            if msg.sender_type == "user":
                messages.append({"role": "user", "content": msg.content})
            elif msg.sender_type == "ai":
                messages.append({"role": "assistant", "content": msg.content})

        return messages
