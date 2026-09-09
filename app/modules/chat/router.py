"""Chat 路由:会话 CRUD + AI 聊天(SSE 流式)。

拆成两个 router,在 api/router.py 中分别挂载:
- conversations_router → /api/v1/conversations
- chat_router          → /api/v1/chat

SSE 端点注意事项:
- EventSourceResponse 返回后,FastAPI 依赖注入会关闭 session
- 因此 SSE 内部用 async_session_factory 创建独立 session,由 generator 自己管理生命周期
- 流式结束后用该 session 保存 AI 回复,不会被提前关闭
"""
import json

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session
from app.common.exceptions.handler import AppException
from app.common.response.base import ResponseBase, success
from app.infrastructure.database.session import async_session_factory
from app.infrastructure.llm import is_llm_available
from app.modules.chat.repository.chat_repository import MessageRepository
from app.modules.chat.schemas import (
    ChatRequest,
    ConversationCreateRequest,
    ConversationResponse,
    MessageListResponse,
)
from app.modules.chat.service import ChatService

# ── 会话 CRUD router(挂 /conversations 前缀) ───────────
conversations_router = APIRouter()


@conversations_router.post("", response_model=ResponseBase[ConversationResponse])
async def create_conversation(
    req: ConversationCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """创建新会话。"""
    service = ChatService(db)
    user_id = current_user.id if current_user else None
    result = await service.create_conversation(user_id, req)
    return success(result)


@conversations_router.get("", response_model=ResponseBase[list[ConversationResponse]])
async def list_conversations(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """查询当前用户的会话列表。"""
    service = ChatService(db)
    user_id = current_user.id if current_user else None
    result = await service.list_conversations(user_id)
    return success(result)


@conversations_router.get(
    "/{conversation_id}", response_model=ResponseBase[ConversationResponse]
)
async def get_conversation(
    conversation_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """查询会话详情。"""
    service = ChatService(db)
    result = await service.get_conversation(conversation_id)
    return success(result)


@conversations_router.get(
    "/{conversation_id}/messages",
    response_model=ResponseBase[MessageListResponse],
)
async def list_messages(
    conversation_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """查询会话的消息列表。"""
    service = ChatService(db)
    items = await service.list_messages(conversation_id)
    return success(MessageListResponse(items=items))


# ── AI 聊天 router(挂 /chat 前缀) ───────────────────────
chat_router = APIRouter()


# 错误标记(与 service.chat 配合)
_ERROR_PREFIX = "[AI_ERROR]"
_ERROR_SUFFIX = "[/AI_ERROR]"


@chat_router.post("")
async def chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """AI 聊天接口(SSE 流式输出)。

    前端通过 EventSource 接收事件流,事件类型:
        - {"type":"start"}             — 流开始
        - {"type":"content","content": "..."} — 内容增量
        - {"type":"error","message": "..."}   — 流式中途出错
        - {"type":"done"}              — 流结束
    """
    # 提前校验:LLM 不可用直接抛 503(避免 SSE 吞异常)
    if not is_llm_available():
        raise AppException(503, "LLM 未配置,无法进行 AI 聊天", http_status=503)

    user_id = current_user.id if current_user else None

    async def event_generator():
        # 必须用独立 session!
        # EventSourceResponse 返回后,FastAPI 依赖注入会关闭 db session,
        # 但 AI 回复需要在流式结束后保存,所以这里自己创建 session。
        async with async_session_factory() as sse_session:
            service = ChatService(sse_session)

            # 先推送 start 事件
            yield {"event": "chat", "data": json.dumps({"type": "start"})}

            # 流式推送内容增量 + 收集完整回复
            full_reply_parts: list[str] = []
            has_error = False

            try:
                async for chunk in service.chat(user_id, req):
                    # 检测错误标记
                    if chunk.startswith(_ERROR_PREFIX) and chunk.endswith(_ERROR_SUFFIX):
                        has_error = True
                        error_msg = chunk[len(_ERROR_PREFIX) : -len(_ERROR_SUFFIX)]
                        yield {
                            "event": "chat",
                            "data": json.dumps(
                                {"type": "error", "message": error_msg},
                                ensure_ascii=False,
                            ),
                        }
                        break

                    full_reply_parts.append(chunk)
                    yield {
                        "event": "chat",
                        "data": json.dumps(
                            {"type": "content", "content": chunk}, ensure_ascii=False
                        ),
                    }
            except Exception as e:
                has_error = True
                yield {
                    "event": "chat",
                    "data": json.dumps(
                        {"type": "error", "message": str(e)}, ensure_ascii=False
                    ),
                }

            # 流式结束后保存 AI 回复(仅当没有出错且有内容时)
            if not has_error:
                full_reply = "".join(full_reply_parts).strip()
                if full_reply:
                    msg_repo = MessageRepository(sse_session)
                    await msg_repo.create(
                        conversation_id=req.conversation_id,
                        sender_type="ai",
                        sender_id=None,
                        content=full_reply,
                    )
                    await sse_session.commit()

            # 结束事件
            yield {"event": "chat", "data": json.dumps({"type": "done"})}

    return EventSourceResponse(event_generator())


# 保留原 router 名称作为 conversations_router 的别名,兼容旧引用
router = conversations_router
