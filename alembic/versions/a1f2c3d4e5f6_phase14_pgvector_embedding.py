"""phase14: pgvector extension, embedding column, hybrid-search indexes

Revision ID: a1f2c3d4e5f6
Revises: 0391ca308092
Create Date: 2026-09-20

变更内容:
1. CREATE EXTENSION vector / pg_trgm
   - vector: pgvector 向量检索(embedding 列、<=> 余弦距离、HNSW 索引)
   - pg_trgm: 中文关键词检索的 GIN 索引(ILIKE 加速)
2. document_chunk 增加 embedding vector(512) 列(可空,旧数据无向量)
   + HNSW 余弦索引(vector_cosine_ops)
3. 补初始迁移欠下的业务索引:
   - message(conversation_id, created_at):会话消息列表按时间排序,最高频查询
   - document_chunk(document_id):按文档查块/级联删除
   - user(email):登录查询(该列本有唯一约束,补显式索引便于统一管理)

注意:
- 向量维度 512 与 app/ai/rag/config.py 的 EMBEDDING_DIM 绑定,换模型需重建向量。
- alembic autogenerate 不识别 pgvector 类型,故本迁移全部手写 SQL。
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1f2c3d4e5f6'
down_revision: str | Sequence[str] | None = '0391ca308092'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. 扩展 ──
    # vector 扩展需要超级用户或 CREATE 权限;docker-compose 的 ai_cs 用户
    # 是该实例的 superuser,本地开发环境无问题。生产环境需 DBA 预先创建。
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ── 2. embedding 列 + HNSW 余弦索引 ──
    op.execute(
        "ALTER TABLE document_chunk "
        "ADD COLUMN IF NOT EXISTS embedding vector(512)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_chunk_embedding "
        "ON document_chunk USING hnsw (embedding vector_cosine_ops)"
    )

    # ── 3. 中文关键词检索 GIN 索引(pg_trgm,加速 ILIKE)──
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_chunk_content_trgm "
        "ON document_chunk USING gin (content gin_trgm_ops)"
    )

    # ── 4. 补业务索引 ──
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_message_conversation_created "
        "ON message (conversation_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_chunk_document "
        "ON document_chunk (document_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_email "
        "ON \"user\" (email)"
    )

    # ── 5. document 增加失败原因列 ──
    # 扫描版 PDF 抽不出文字、文件损坏等情况下,仅有 status=5 无法定位问题,
    # 记下原因便于前端展示与排查。
    op.execute(
        "ALTER TABLE document ADD COLUMN IF NOT EXISTS error_reason text"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE document DROP COLUMN IF EXISTS error_reason")
    op.execute("DROP INDEX IF EXISTS idx_user_email")
    op.execute("DROP INDEX IF EXISTS idx_document_chunk_document")
    op.execute("DROP INDEX IF EXISTS idx_message_conversation_created")
    op.execute("DROP INDEX IF EXISTS idx_document_chunk_content_trgm")
    op.execute("DROP INDEX IF EXISTS idx_document_chunk_embedding")
    op.execute("ALTER TABLE document_chunk DROP COLUMN IF EXISTS embedding")
    # 扩展不 DROP:可能被其他对象依赖,且重建成本高
