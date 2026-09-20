"""向量存储抽象与 pgvector 实现(第 14 阶段 M1)。

抽象接口 VectorStore 只约束 upsert / search / delete 三个动作,
pgvector 实现直接落在 document_chunk.embedding 列上(向量与业务数据同库)。
日后要切 Milvus 时,新写一个实现类即可,业务层不动。

检索距离:余弦(<=>)。bge 系列模型官方推荐余弦相似度。
"""
from abc import ABC, abstractmethod

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class VectorStore(ABC):
    """向量存储抽象接口。"""

    @abstractmethod
    async def upsert(self, session: AsyncSession, chunk_ids: list[int],
                     embeddings: list[list[float]]) -> int:
        """把向量写入一批 chunk。返回成功条数。"""

    @abstractmethod
    async def search(self, session: AsyncSession, query_embedding: list[float],
                     top_k: int, kb_ids: list[int] | None = None) -> list[dict]:
        """向量近邻检索。返回 [{chunk_id, distance, content, file_name, kb_id}] 按距离升序。"""

    @abstractmethod
    async def delete_by_document(self, session: AsyncSession, document_id: int) -> None:
        """删除某文档全部向量(pgvector 实现 = 清空 embedding 列)。"""


def _to_pgvector_literal(vec: list[float]) -> str:
    """把 Python float 列表序列化为 pgvector 字面量 '[0.1,0.2,...]'。

    asyncpg 以文本参数传入,SQL 侧显式 CAST 成 vector —— 避开各驱动
    对自定义类型的适配差异。
    """
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


class PgVectorStore(VectorStore):
    """pgvector 实现:向量直接存 document_chunk.embedding。"""

    async def upsert(self, session: AsyncSession, chunk_ids: list[int],
                     embeddings: list[list[float]]) -> int:
        if len(chunk_ids) != len(embeddings):
            raise ValueError(f"chunk_ids({len(chunk_ids)}) 与 embeddings({len(embeddings)}) 数量不一致")
        updated = 0
        for chunk_id, vec in zip(chunk_ids, embeddings, strict=True):
            result = await session.execute(
                text(
                    "UPDATE document_chunk "
                    "SET embedding = CAST(:vec AS vector), embedding_status = 1 "
                    "WHERE id = :chunk_id"
                ),
                {"vec": _to_pgvector_literal(vec), "chunk_id": chunk_id},
            )
            updated += result.rowcount or 0
        return updated

    async def search(self, session: AsyncSession, query_embedding: list[float],
                     top_k: int, kb_ids: list[int] | None = None) -> list[dict]:
        kb_filter = ""
        params: dict = {
            "qv": _to_pgvector_literal(query_embedding),
            "top_k": top_k,
        }
        if kb_ids:
            # = ANY(:kb_ids) 需要数组类型;用 IN + 动态占位符最稳
            placeholders = ",".join(f":kb{i}" for i in range(len(kb_ids)))
            kb_filter = f"AND d.kb_id IN ({placeholders})"
            for i, kb_id in enumerate(kb_ids):
                params[f"kb{i}"] = kb_id

        sql = f"""
            SELECT dc.id AS chunk_id,
                   dc.content AS content,
                   dc.document_id AS document_id,
                   d.file_name AS file_name,
                   d.kb_id AS kb_id,
                   dc.embedding <=> CAST(:qv AS vector) AS distance
            FROM document_chunk dc
            JOIN document d ON d.id = dc.document_id
            WHERE dc.embedding IS NOT NULL
              AND d.status = 4
              {kb_filter}
            ORDER BY distance ASC
            LIMIT :top_k
        """
        result = await session.execute(text(sql), params)
        return [dict(row._mapping) for row in result.fetchall()]

    async def delete_by_document(self, session: AsyncSession, document_id: int) -> None:
        await session.execute(
            text(
                "UPDATE document_chunk "
                "SET embedding = NULL, embedding_status = 0 "
                "WHERE document_id = :document_id"
            ),
            {"document_id": document_id},
        )


# 全局默认实例(pgvector 无连接状态,可安全复用)
vector_store: VectorStore = PgVectorStore()


__all__ = ["PgVectorStore", "VectorStore", "vector_store"]
