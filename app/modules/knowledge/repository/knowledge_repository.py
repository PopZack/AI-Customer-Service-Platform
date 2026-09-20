"""知识库模块 Repository。"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.repository.base import BaseRepository
from app.models.knowledge import Document, DocumentChunk, KnowledgeBase


class KnowledgeBaseRepository(BaseRepository[KnowledgeBase]):
    """知识库数据访问层。"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, KnowledgeBase)

    async def list_by_tenant(self, tenant_id: int) -> list[KnowledgeBase]:
        """按租户查询知识库列表。"""
        stmt = select(KnowledgeBase).where(KnowledgeBase.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent(self, limit: int = 100) -> list[KnowledgeBase]:
        """按创建时间倒序查询(本项目暂未启用多租户,先全量返回)。"""
        stmt = select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class DocumentRepository(BaseRepository[Document]):
    """文档数据访问层。"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Document)

    async def list_by_kb(self, kb_id: int, limit: int = 200) -> list[Document]:
        """按知识库查询文档列表。"""
        stmt = (
            select(Document)
            .where(Document.kb_id == kb_id)
            .order_by(Document.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_indexed_ids(self) -> list[int]:
        """已索引完成(status=4)的文档 ID。检索只应命中这些文档。"""
        stmt = select(Document.id).where(Document.status == 4)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class DocumentChunkRepository(BaseRepository[DocumentChunk]):
    """文档切块数据访问层。"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, DocumentChunk)

    async def list_by_document(self, document_id: int, limit: int = 500) -> list[DocumentChunk]:
        """按文档查询切块(按块序号升序)。"""
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_no.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_document(self, document_id: int) -> int:
        """统计文档的切块数。"""
        stmt = select(func.count()).select_from(DocumentChunk).where(
            DocumentChunk.document_id == document_id
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def delete_by_document(self, document_id: int) -> int:
        """删除某文档的全部切块。返回删除条数。"""
        chunks = await self.list_by_document(document_id, limit=10_000)
        for chunk in chunks:
            await self.session.delete(chunk)
        await self.session.flush()
        return len(chunks)
