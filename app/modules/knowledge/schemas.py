"""Knowledge API 数据结构:知识库 CRUD + 文档上传/索引状态 + 检索预览。"""
from datetime import datetime

from pydantic import BaseModel, Field

# ── 知识库 ──────────────────────────────────────────────


class KnowledgeBaseCreateRequest(BaseModel):
    """创建知识库请求。"""

    name: str = Field(..., min_length=1, max_length=100, description="知识库名称")
    description: str | None = Field(None, description="描述")


class KnowledgeBaseResponse(BaseModel):
    """知识库响应。"""

    id: int
    name: str
    description: str | None = None
    embedding_model: str | None = None
    status: int
    created_at: datetime

    class Config:
        from_attributes = True


class KnowledgeBaseListResponse(BaseModel):
    """知识库列表响应。"""

    items: list[KnowledgeBaseResponse]
    total: int


# ── 文档 ────────────────────────────────────────────────

# 状态码语义(与 Document.status 一致),前端据此展示进度
DOCUMENT_STATUS_TEXT = {
    0: "上传中",
    1: "解析中",
    2: "切块中",
    3: "向量化中",
    4: "已完成",
    5: "失败",
}


class DocumentResponse(BaseModel):
    """文档响应。"""

    id: int
    kb_id: int
    file_name: str
    file_size: int | None = None
    file_type: str | None = None
    status: int
    status_text: str | None = None
    error_reason: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """文档列表响应。"""

    items: list[DocumentResponse]
    total: int


class ChunkResponse(BaseModel):
    """文档切块响应(不含向量本身,只给元信息与命中状态)。"""

    id: int
    chunk_no: int
    content: str
    embedding_status: int
    created_at: datetime

    class Config:
        from_attributes = True


class ChunkListResponse(BaseModel):
    """切块列表响应。"""

    items: list[ChunkResponse]
    total: int


# ── 检索预览(调试/演示用)────────────────────────────


class SearchRequest(BaseModel):
    """检索预览请求:直接看知识库命中了哪些块,便于调参与演示。"""

    query: str = Field(..., min_length=1, max_length=500, description="查询串")
    top_k: int = Field(6, ge=1, le=20, description="返回条数")


class SearchHit(BaseModel):
    """单条命中。"""

    chunk_id: int
    document_id: int
    file_name: str
    content: str
    rrf_score: float


class SearchResponse(BaseModel):
    """检索预览响应。"""

    query: str
    hits: list[SearchHit]
    total: int
