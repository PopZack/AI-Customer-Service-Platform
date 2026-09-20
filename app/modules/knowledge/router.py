"""Knowledge 路由:知识库 CRUD、文档上传与索引状态、检索预览。

挂载前缀 /api/v1/knowledge-bases(见 app/api/router.py)。
文档上传后立即返回,解析/切块/向量化由 BackgroundTasks 异步执行;
前端轮询 GET /{kb_id}/documents/{doc_id} 看 status 变化。

依赖注入用 Annotated 形式(FastAPI 现行推荐写法),可避免 ruff 的 B008
(function-call-in-default-argument)—— 老式写法会把 Depends(...) 当作默认值。
"""
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db_session
from app.common.response.base import ResponseBase, success
from app.models.user_system import User
from app.modules.knowledge.schemas import (
    ChunkListResponse,
    DocumentListResponse,
    DocumentResponse,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    SearchRequest,
    SearchResponse,
)
from app.modules.knowledge.service import KnowledgeService
from app.tasks.document_tasks import process_document

router = APIRouter()

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# ── 知识库 ──────────────────────────────────────────────


@router.post("", response_model=ResponseBase[KnowledgeBaseResponse])
async def create_knowledge_base(
    req: KnowledgeBaseCreateRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """创建知识库。"""
    service = KnowledgeService(db)
    return success(await service.create_kb(req, current_user.id))


@router.get("", response_model=ResponseBase[KnowledgeBaseListResponse])
async def list_knowledge_bases(db: DbSession, current_user: CurrentUser):
    """知识库列表。"""
    service = KnowledgeService(db)
    items = await service.list_kbs()
    return success(KnowledgeBaseListResponse(items=items, total=len(items)))


# ── 文档 ────────────────────────────────────────────────


@router.post("/{kb_id}/documents", response_model=ResponseBase[DocumentResponse])
async def upload_document(
    kb_id: int,
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File(description="PDF / DOCX / MD / TXT")],
):
    """上传文档并触发异步索引。

    立即返回文档记录(status=0 上传中);处理进度通过文档详情接口轮询。
    """
    service = KnowledgeService(db)
    doc = await service.upload_document(kb_id, file, current_user.id)

    # 响应返回后执行;任务内部自建 session(此时请求 session 已关闭)
    background_tasks.add_task(process_document, doc.id)
    return success(doc)


@router.get("/{kb_id}/documents", response_model=ResponseBase[DocumentListResponse])
async def list_documents(kb_id: int, db: DbSession, current_user: CurrentUser):
    """知识库下的文档列表。"""
    service = KnowledgeService(db)
    items = await service.list_documents(kb_id)
    return success(DocumentListResponse(items=items, total=len(items)))


@router.get(
    "/{kb_id}/documents/{document_id}",
    response_model=ResponseBase[DocumentResponse],
)
async def get_document(
    kb_id: int, document_id: int, db: DbSession, current_user: CurrentUser
):
    """文档详情(含索引状态与失败原因)。"""
    service = KnowledgeService(db)
    return success(await service.get_document(kb_id, document_id))


@router.get(
    "/{kb_id}/documents/{document_id}/chunks",
    response_model=ResponseBase[ChunkListResponse],
)
async def list_document_chunks(
    kb_id: int, document_id: int, db: DbSession, current_user: CurrentUser
):
    """查看文档切块结果(调切块参数时很有用)。"""
    service = KnowledgeService(db)
    items = await service.list_chunks(kb_id, document_id)
    return success(ChunkListResponse(items=items, total=len(items)))


@router.delete("/{kb_id}/documents/{document_id}", response_model=ResponseBase[dict])
async def delete_document(
    kb_id: int, document_id: int, db: DbSession, current_user: CurrentUser
):
    """删除文档及其切块与向量。"""
    service = KnowledgeService(db)
    await service.delete_document(kb_id, document_id)
    return success({"deleted": document_id})


# ── 检索预览 ────────────────────────────────────────────


@router.post("/{kb_id}/search", response_model=ResponseBase[SearchResponse])
async def search_knowledge_base(
    kb_id: int, req: SearchRequest, db: DbSession, current_user: CurrentUser
):
    """直接跑混合检索看命中结果,不经过 LLM。调参与演示用。"""
    service = KnowledgeService(db)
    hits = await service.search(req.query, kb_id, req.top_k)
    return success(SearchResponse(query=req.query, hits=hits, total=len(hits)))
