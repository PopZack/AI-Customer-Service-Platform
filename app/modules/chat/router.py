"""Chat 路由:会话 CRUD + AI 聊天(SSE 流式)+ 转人工。

拆成两个 router,在 api/router.py 中分别挂载:
- conversations_router → /api/v1/conversations
- chat_router          → /api/v1/chat

SSE 端点注意事项:
- EventSourceResponse 返回后,FastAPI 依赖注入会关闭 session
- 因此 SSE 内部用 async_session_factory 创建独立 session,由 generator 自己管理生命周期
- 流式结束后用该 session 保存 AI 回复,不会被提前关闭

依赖注入统一用 Annotated 形式(与 knowledge 路由一致),避免 ruff 的 B008。
"""
import json
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.dependencies import get_current_user, get_db_session
from app.common.exceptions.handler import AppException
from app.common.response.base import ResponseBase, success
from app.infrastructure.database.session import async_session_factory
from app.infrastructure.llm import is_llm_available
from app.models.conversation import ConversationStatus
from app.models.user_system import User
from app.modules.chat.repository.chat_repository import MessageRepository
from app.modules.chat.schemas import (
    ChatRequest,
    ConversationCreateRequest,
    ConversationResponse,
    HandoffRequest,
    HandoffResponse,
    MessageListResponse,
)
from app.modules.chat.service import ChatEvent, ChatService

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

# ── 会话 CRUD router(挂 /conversations 前缀) ───────────
conversations_router = APIRouter()


@conversations_router.post("", response_model=ResponseBase[ConversationResponse])
async def create_conversation(
    req: ConversationCreateRequest, db: DbSession, current_user: CurrentUser
):
    """创建新会话。"""
    service = ChatService(db)
    return success(await service.create_conversation(current_user.id, req))


@conversations_router.get("", response_model=ResponseBase[list[ConversationResponse]])
async def list_conversations(db: DbSession, current_user: CurrentUser):
    """查询当前用户的会话列表。"""
    service = ChatService(db)
    return success(await service.list_conversations(current_user.id))


@conversations_router.get("/{conversation_id}", response_model=ResponseBase[ConversationResponse])
async def get_conversation(conversation_id: int, db: DbSession, current_user: CurrentUser):
    """查询会话详情(含状态机状态)。"""
    service = ChatService(db)
    return success(await service.get_conversation(conversation_id))


@conversations_router.get(
    "/{conversation_id}/messages", response_model=ResponseBase[MessageListResponse]
)
async def list_messages(conversation_id: int, db: DbSession, current_user: CurrentUser):
    """查询会话的消息列表。"""
    service = ChatService(db)
    items = await service.list_messages(conversation_id)
    return success(MessageListResponse(items=items))


# ── 转人工 ──────────────────────────────────────────────


@conversations_router.post(
    "/{conversation_id}/handoff", response_model=ResponseBase[HandoffResponse]
)
async def handoff_conversation(
    conversation_id: int,
    req: HandoffRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """显式转人工(用户点「转人工」按钮)。

    与 AI 自己判断的隐式转人工共用同一套落库逻辑:会话置为「等待人工」
    + 落 system 消息 + 保证有工单可追。
    """
    service = ChatService(db)
    result = await service.handoff(current_user.id, conversation_id, req.reason or "")
    return success(HandoffResponse(**result))


@conversations_router.get(
    "/{conversation_id}/handoff-signal", response_model=ResponseBase[dict]
)
async def get_handoff_signal(conversation_id: int, db: DbSession, current_user: CurrentUser):
    """查看转人工判定信号(连续空检索次数 / 阈值),用于调试与前端展示。"""
    service = ChatService(db)
    return success(await service.get_handoff_signal(conversation_id))


# ── AI 聊天 router(挂 /chat 前缀) ───────────────────────
chat_router = APIRouter()


@chat_router.post("")
async def chat(req: ChatRequest, db: DbSession, current_user: CurrentUser):
    """AI 聊天接口(SSE 流式输出)。

    注意:本接口是 **POST**,浏览器的 EventSource 只支持 GET,
    前端需用 fetch + ReadableStream 手工解析 SSE 帧(见 static/index.html)。

    事件类型(data 字段的 type):
        - start                        — 流开始
        - content      {content}       — 内容增量
        - tool_start   {tool, content} — 开始执行工具(前端可显示"正在检索知识库…")
        - tool_end     {tool}          — 工具执行结束
        - notice       {content}       — 提示信息(如已达工具轮数上限)
        - handoff      {status, ticket_id, content} — 已转人工
        - error        {message}       — 流式中途出错
        - done         {status}        — 流结束,附带会话最新状态
    """
    # 先确认会话存在且是否需要 AI 作答 —— 顺序很重要:
    # 已转人工的会话,AI 本就不该回答,此时报"LLM 未配置"是错的;
    # 而且这条分支不经过 LLM,不该被 LLM 可用性拦住。
    conv = await ChatService(db).get_conversation(req.conversation_id)
    if conv.status not in ConversationStatus.HUMAN_SIDE and not is_llm_available():
        raise AppException(503, "LLM 未配置,无法进行 AI 聊天", http_status=503)

    user_id = current_user.id

    def _sse(event: ChatEvent) -> dict:
        # reply 是给本函数落库用的完整回答,内容已经通过 content 事件流式推过,
        # 不必再重复发一遍(长回答会凭空多出一倍负载)
        payload = asdict(event)
        payload.pop("reply", None)
        return {"event": "chat", "data": json.dumps(payload, ensure_ascii=False)}

    async def event_generator():
        # 必须用独立 session!
        # EventSourceResponse 返回后,FastAPI 依赖注入会关闭请求 session,
        # 但 AI 回复与工具副作用需要在流式过程中/结束后落库。
        async with async_session_factory() as sse_session:
            service = ChatService(sse_session)

            yield {"event": "chat", "data": json.dumps({"type": "start"})}

            full_reply = ""
            has_error = False
            final_status: int | None = None
            done_sent = False

            try:
                async for event in service.chat(user_id, req):
                    if event.type == "done":
                        final_status = event.status
                        full_reply = event.reply or full_reply
                        done_sent = True
                    yield _sse(event)
            except Exception as e:  # noqa: BLE001 —— 必须转成 SSE error 事件,不能中断流
                has_error = True
                error_payload = {"type": "error", "message": str(e)}
                yield {"event": "chat", "data": json.dumps(error_payload, ensure_ascii=False)}

            # 流式结束后保存 AI 回复(出错时不保存,避免存半句话)
            if not has_error and full_reply.strip():
                msg_repo = MessageRepository(sse_session)
                await msg_repo.create(
                    conversation_id=req.conversation_id,
                    sender_type="ai",
                    sender_id=None,
                    content=full_reply.strip(),
                )
                await sse_session.commit()

            # service 正常收尾时已经发过 done,这里只在异常/未收尾时兜底,
            # 避免前端收到两个 done 事件
            if not done_sent:
                yield {
                    "event": "chat",
                    "data": json.dumps(
                        {"type": "done", "status": final_status}, ensure_ascii=False
                    ),
                }

    return EventSourceResponse(event_generator())


# 保留原 router 名称作为 conversations_router 的别名,兼容旧引用
router = conversations_router
