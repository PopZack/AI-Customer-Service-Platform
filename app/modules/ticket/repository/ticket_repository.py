"""工单模块 Repository。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.repository.base import BaseRepository
from app.models.ticket import Ticket, TicketMessage


class TicketRepository(BaseRepository[Ticket]):
    """工单数据访问层。"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Ticket)

    async def list_by_assignee(self, assigned_user: int) -> list[Ticket]:
        """按指派客服查询工单列表。"""
        stmt = select(Ticket).where(Ticket.assigned_user == assigned_user)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_tickets(
        self,
        status: int | None = None,
        assigned_user: int | None = None,
        limit: int = 200,
    ) -> list[Ticket]:
        """带筛选的工单列表(按下单时间倒序)。

        status=None 表示不筛状态;assigned_user 传 0 表示"只看未指派的",
        因为列本身可空,用 `is_(None)` 表达更准确。
        """
        stmt = select(Ticket)
        if status is not None:
            stmt = stmt.where(Ticket.status == status)
        if assigned_user == 0:
            stmt = stmt.where(Ticket.assigned_user.is_(None))
        elif assigned_user is not None:
            stmt = stmt.where(Ticket.assigned_user == assigned_user)
        stmt = stmt.order_by(Ticket.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_conversation(self, conversation_id: int) -> Ticket | None:
        """按会话查关联工单(取最新一条)。"""
        stmt = (
            select(Ticket)
            .where(Ticket.conversation_id == conversation_id)
            .order_by(Ticket.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()


class TicketMessageRepository(BaseRepository[TicketMessage]):
    """工单消息数据访问层。"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, TicketMessage)

    async def list_by_ticket(self, ticket_id: int, limit: int = 200) -> list[TicketMessage]:
        """按工单查询消息(时间升序)。"""
        stmt = (
            select(TicketMessage)
            .where(TicketMessage.ticket_id == ticket_id)
            .order_by(TicketMessage.created_at.asc(), TicketMessage.id.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def first_contents(self, ticket_ids: list[int]) -> dict[int, str]:
        """批量取每个工单的首条消息内容,用作列表页的"问题摘要"。

        一次查询取回后在内存里按 ticket_id 取首条 —— 工单量在演示/中小规模下
        完全够用,不值得为此写窗口函数子查询。
        """
        if not ticket_ids:
            return {}
        stmt = (
            select(TicketMessage)
            .where(TicketMessage.ticket_id.in_(ticket_ids))
            .order_by(TicketMessage.ticket_id.asc(), TicketMessage.id.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        result: dict[int, str] = {}
        for row in rows:
            result.setdefault(row.ticket_id, row.content)
        return result
