"""Ticket 业务用例:工单列表/详情、指派认领、人工回复、关单。

关键设计:**人工回复要双写**
    - `ticket_message`(sender_type='human') —— 工单的审计留痕,客服侧可见
    - `message`(sender_type='human')       —— 写入会话消息流,用户侧可见

只写工单表的话,客服回了话、用户在自己的聊天窗口却看不到,工单与会话会脱节。
这是"AI + 人工协同"最容易被忽略、又最影响体感的一处。

权限:第 16 阶段采用**基于数据归属的最小门槛**(指派/认领),不依赖角色表 ——
设计文档定义了 ticket:view / ticket:edit 权限码,但角色与权限数据尚未播种,
此时强校验会让所有人 403。留待权限体系落地后收紧(见 README 的已知取舍)。
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions.handler import AppException
from app.models.conversation import Conversation, ConversationStatus, Message
from app.models.ticket import Ticket, TicketMessage, TicketPriority, TicketStatus
from app.modules.ticket.repository.ticket_repository import (
    TicketMessageRepository,
    TicketRepository,
)
from app.modules.ticket.schemas import (
    TicketDetailResponse,
    TicketMessageResponse,
    TicketResponse,
)

logger = logging.getLogger(__name__)


class TicketService:
    """工单业务服务。"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.ticket_repo = TicketRepository(session)
        self.msg_repo = TicketMessageRepository(session)

    # ── 查询 ──────────────────────────────────────────────

    async def list_tickets(
        self, status: int | None = None, assigned_user: int | None = None
    ) -> list[TicketResponse]:
        tickets = await self.ticket_repo.list_tickets(status, assigned_user)
        summaries = await self.msg_repo.first_contents([t.id for t in tickets])
        return [self._to_response(t, summaries.get(t.id)) for t in tickets]

    async def get_ticket(self, ticket_id: int) -> TicketDetailResponse:
        ticket = await self._require(ticket_id)
        msgs = await self.msg_repo.list_by_ticket(ticket_id)
        base = self._to_response(ticket, msgs[0].content if msgs else None)
        return TicketDetailResponse(
            **base.model_dump(),
            messages=[TicketMessageResponse.model_validate(m) for m in msgs],
        )

    # ── 操作 ──────────────────────────────────────────────

    async def assign(self, ticket_id: int, agent_id: int | None, caller_id: int) -> TicketResponse:
        """指派工单。agent_id 为空表示「认领给自己」。"""
        ticket = await self._require(ticket_id)
        target = agent_id if agent_id is not None else caller_id

        if ticket.status in (TicketStatus.DONE, TicketStatus.CLOSED):
            raise AppException(400, "工单已结束,不能再指派")

        ticket.assigned_user = target
        ticket.status = TicketStatus.PROCESSING
        # 客服接手 → 会话进入「人工接管」,AI 不再作答
        await self._set_conversation_status(ticket, ConversationStatus.HUMAN)
        self.session.add(
            TicketMessage(
                ticket_id=ticket.id,
                sender_type="system",
                sender_id=caller_id,
                content=f"工单已指派给用户 {target},会话进入人工接管。",
            )
        )
        await self.session.commit()
        await self.session.refresh(ticket)
        return self._to_response(ticket)

    async def reply(self, ticket_id: int, agent_id: int, content: str) -> TicketMessageResponse:
        """客服人工回复(双写:工单留痕 + 会话可见)。"""
        ticket = await self._require(ticket_id)

        if ticket.status in (TicketStatus.DONE, TicketStatus.CLOSED):
            raise AppException(400, "工单已结束,无法回复")
        if ticket.assigned_user is None:
            # 未指派的工单,回复即认领,省掉一步操作
            ticket.assigned_user = agent_id
        elif ticket.assigned_user != agent_id:
            raise AppException(403, f"该工单已指派给用户 {ticket.assigned_user},无权回复")
        ticket.status = TicketStatus.PROCESSING

        # ① 工单留痕
        ticket_msg = TicketMessage(
            ticket_id=ticket.id, sender_type="human", sender_id=agent_id, content=content
        )
        self.session.add(ticket_msg)

        # ② 写入会话消息流,用户在聊天窗口能看到
        if ticket.conversation_id is not None:
            self.session.add(
                Message(
                    conversation_id=ticket.conversation_id,
                    sender_type="human",
                    sender_id=agent_id,
                    content=content,
                    message_type="text",
                )
            )
            await self._set_conversation_status(ticket, ConversationStatus.HUMAN, commit=False)

        await self.session.commit()
        await self.session.refresh(ticket_msg)
        return TicketMessageResponse.model_validate(ticket_msg)

    async def close(self, ticket_id: int, resolution: str | None = None) -> TicketResponse:
        """关闭工单,同时结束会话。"""
        ticket = await self._require(ticket_id)
        if ticket.status == TicketStatus.CLOSED:
            raise AppException(400, "工单已经关闭")

        ticket.status = TicketStatus.DONE
        self.session.add(
            TicketMessage(
                ticket_id=ticket.id,
                sender_type="system",
                content=f"工单已完成。{resolution or ''}".strip(),
            )
        )
        await self._set_conversation_status(ticket, ConversationStatus.CLOSED)
        await self.session.commit()
        await self.session.refresh(ticket)
        return self._to_response(ticket)

    # ── 内部 ──────────────────────────────────────────────

    async def _require(self, ticket_id: int) -> Ticket:
        ticket = await self.ticket_repo.get_by_id(ticket_id)
        if ticket is None:
            raise AppException(404, "工单不存在")
        return ticket

    async def _set_conversation_status(
        self, ticket: Ticket, status: int, commit: bool = False
    ) -> None:
        """同步会话状态机(工单与会话是同一件事的两个视角,状态必须一致)。"""
        if ticket.conversation_id is None:
            return
        conv = await self.session.get(Conversation, ticket.conversation_id)
        if conv is not None and conv.status != status:
            conv.status = status
            logger.info("会话 %s 状态更新为 %s", conv.id, ConversationStatus.TEXT.get(status))
        if commit:
            await self.session.commit()

    @staticmethod
    def _to_response(ticket: Ticket, summary: str | None = None) -> TicketResponse:
        resp = TicketResponse.model_validate(ticket)
        resp.status_text = TicketStatus.TEXT.get(ticket.status, "未知")
        resp.priority_text = TicketPriority.TEXT.get(ticket.priority, "未知")
        resp.summary = summary[:120] if summary else None
        return resp
