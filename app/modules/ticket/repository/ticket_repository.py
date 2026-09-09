"""工单模块 Repository。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.repository.base import BaseRepository
from app.models.ticket import Ticket


class TicketRepository(BaseRepository[Ticket]):
    """工单数据访问层。"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Ticket)

    async def list_by_assignee(self, assigned_user: int) -> list[Ticket]:
        """按指派客服查询工单列表。"""
        stmt = select(Ticket).where(Ticket.assigned_user == assigned_user)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
