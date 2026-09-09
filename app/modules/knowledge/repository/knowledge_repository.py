"""知识库模块 Repository。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.repository.base import BaseRepository
from app.models.knowledge import KnowledgeBase


class KnowledgeBaseRepository(BaseRepository[KnowledgeBase]):
    """知识库数据访问层。"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, KnowledgeBase)

    async def list_by_tenant(self, tenant_id: int) -> list[KnowledgeBase]:
        """按租户查询知识库列表。"""
        stmt = select(KnowledgeBase).where(KnowledgeBase.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
