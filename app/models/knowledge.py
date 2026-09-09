"""知识库系统模型: knowledge_base / document / document_chunk / vector_index。"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, BigIntPKMixin


def _created_at() -> Mapped[datetime]:
    """统一的 created_at 列定义(仅创建时间,无 updated_at)。"""
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )


# ── 知识库 ──────────────────────────────────────────────
class KnowledgeBase(Base, BigIntPKMixin):
    """知识库。"""

    __tablename__ = "knowledge_base"

    tenant_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tenant.id", ondelete="SET NULL"), nullable=True, comment="所属租户"
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="知识库名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="嵌入模型")
    status: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False, comment="状态")
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, comment="创建人"
    )
    created_at: Mapped[datetime] = _created_at()

    # 关联
    documents: Mapped[list["Document"]] = relationship(back_populates="knowledge_base", cascade="all, delete-orphan")


# ── 文档 ────────────────────────────────────────────────
class Document(Base, BigIntPKMixin):
    """文档。"""

    __tablename__ = "document"

    kb_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False, comment="所属知识库"
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="文件名")
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="文件大小(字节)")
    file_type: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="文件类型")
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="存储路径")
    status: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False, comment="状态:0上传中 1解析中 2切块中 3向量化 4完成 5失败")
    upload_user: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, comment="上传人"
    )
    created_at: Mapped[datetime] = _created_at()

    # 关联
    knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


# ── 文档切块 ────────────────────────────────────────────
class DocumentChunk(Base, BigIntPKMixin):
    """文档切块(RAG 核心表)。"""

    __tablename__ = "document_chunk"

    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("document.id", ondelete="CASCADE"), nullable=False, comment="所属文档"
    )
    chunk_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="块序号")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="块内容")
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="token 数")
    embedding_status: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False, comment="向量化状态:0未向量化 1已向量化 2失败")
    created_at: Mapped[datetime] = _created_at()

    # 关联
    document: Mapped["Document"] = relationship(back_populates="chunks")
    vector_index: Mapped["VectorIndex | None"] = relationship(back_populates="chunk", uselist=False, cascade="all, delete-orphan")


# ── 向量索引映射 ────────────────────────────────────────
class VectorIndex(Base, BigIntPKMixin):
    """向量索引映射(PG 记录 chunk 与向量库中 vector_id 的对应关系)。"""

    __tablename__ = "vector_index"

    chunk_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("document_chunk.id", ondelete="CASCADE"), nullable=False, unique=True, comment="所属切块"
    )
    vector_id: Mapped[str] = mapped_column(String(100), nullable=False, comment="向量库中的ID")
    platform: Mapped[str] = mapped_column(String(50), nullable=False, comment="向量平台:milvus/pgvector/es")
    created_at: Mapped[datetime] = _created_at()

    # 关联
    chunk: Mapped["DocumentChunk"] = relationship(back_populates="vector_index")
