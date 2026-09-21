"""Ticket 路由:工单列表/详情、指派认领、人工回复、关单。

挂载前缀 /api/v1/tickets(见 app/api/router.py)。
工单由「转人工」自动创建(AI 工具或用户点按钮),客服侧在这里处理。

依赖注入用 Annotated 形式,避免 ruff 的 B008。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session
from app.common.response.base import ResponseBase, success
from app.models.user_system import User
from app.modules.ticket.schemas import (
    TicketAssignRequest,
    TicketCloseRequest,
    TicketDetailResponse,
    TicketListResponse,
    TicketMessageResponse,
    TicketReplyRequest,
    TicketResponse,
)
from app.modules.ticket.service import TicketService

router = APIRouter()

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=ResponseBase[TicketListResponse])
async def list_tickets(
    db: DbSession,
    current_user: CurrentUser,
    status: Annotated[int | None, Query(description="工单状态:0待处理 1处理中 2已完成 3已关闭")] = None,
    assigned_user: Annotated[
        int | None, Query(description="指派客服 ID;传 0 表示只看未指派")
    ] = None,
):
    """工单列表(可按状态 / 指派筛选)。

    客服工作台用 `status=0` 看待处理队列,或 `assigned_user=0` 看未被认领的单。
    """
    service = TicketService(db)
    items = await service.list_tickets(status, assigned_user)
    return success(TicketListResponse(items=items, total=len(items)))


@router.get("/{ticket_id}", response_model=ResponseBase[TicketDetailResponse])
async def get_ticket(ticket_id: int, db: DbSession, current_user: CurrentUser):
    """工单详情(含往来记录)。"""
    service = TicketService(db)
    return success(await service.get_ticket(ticket_id))


@router.post("/{ticket_id}/assign", response_model=ResponseBase[TicketResponse])
async def assign_ticket(
    ticket_id: int,
    req: TicketAssignRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """指派工单;不传 agent_id 表示认领给自己。

    指派后会话状态变为「人工接管」,AI 不再对该会话作答。
    """
    service = TicketService(db)
    return success(await service.assign(ticket_id, req.agent_id, current_user.id))


@router.post("/{ticket_id}/reply", response_model=ResponseBase[TicketMessageResponse])
async def reply_ticket(
    ticket_id: int,
    req: TicketReplyRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """客服人工回复。

    回复会**双写**:工单留痕 + 写入会话消息流(用户在聊天窗口能看到)。
    未指派的工单,回复即视为认领。
    """
    service = TicketService(db)
    return success(await service.reply(ticket_id, current_user.id, req.content))


@router.post("/{ticket_id}/close", response_model=ResponseBase[TicketResponse])
async def close_ticket(
    ticket_id: int,
    req: TicketCloseRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """关闭工单,同时结束对应会话。"""
    service = TicketService(db)
    return success(await service.close(ticket_id, req.resolution))
