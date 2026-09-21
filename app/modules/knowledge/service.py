"""Knowledge 业务用例:知识库 CRUD + 文档上传 + 索引状态查询 + 检索预览。

文档上传只负责"落盘 + 建记录",真正的解析/切块/向量化交给后台任务
(app/tasks/document_tasks.py),接口立即返回、前端轮询状态。
"""
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag.cache import bump_version
from app.ai.rag.config import SUPPORTED_EXTENSIONS
from app.ai.rag.retriever import retrieve
from app.common.exceptions.handler import AppException
from app.config.settings import get_settings
from app.models.knowledge import Document, DocumentStatus, KnowledgeBase
from app.modules.knowledge.repository.knowledge_repository import (
    DocumentChunkRepository,
    DocumentRepository,
    KnowledgeBaseRepository,
)
from app.modules.knowledge.schemas import (
    ChunkResponse,
    DocumentResponse,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseResponse,
    SearchHit,
)

logger = logging.getLogger(__name__)


class KnowledgeService:
    """知识库业务服务。"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.kb_repo = KnowledgeBaseRepository(session)
        self.doc_repo = DocumentRepository(session)
        self.chunk_repo = DocumentChunkRepository(session)

    # ── 知识库 ────────────────────────────────────────────

    async def create_kb(
        self, req: KnowledgeBaseCreateRequest, user_id: int | None
    ) -> KnowledgeBaseResponse:
        kb = await self.kb_repo.create(
            name=req.name,
            description=req.description,
            status=1,
            created_by=user_id,
        )
        await self.session.commit()
        return KnowledgeBaseResponse.model_validate(kb)

    async def list_kbs(self) -> list[KnowledgeBaseResponse]:
        kbs = await self.kb_repo.list_recent()
        return [KnowledgeBaseResponse.model_validate(k) for k in kbs]

    async def get_kb(self, kb_id: int) -> KnowledgeBase:
        kb = await self.kb_repo.get_by_id(kb_id)
        if kb is None:
            raise AppException(404, "知识库不存在")
        return kb

    # ── 文档 ──────────────────────────────────────────────

    async def upload_document(
        self, kb_id: int, file: UploadFile, user_id: int | None
    ) -> DocumentResponse:
        """保存上传文件并创建文档记录(status=上传中),不在此处做解析。"""
        await self.get_kb(kb_id)

        filename = file.filename or "unnamed"
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise AppException(
                400,
                f"不支持的文件类型 {suffix},当前支持:{', '.join(sorted(SUPPORTED_EXTENSIONS))}",
            )

        settings = get_settings()
        raw = await file.read()
        max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
        if len(raw) > max_bytes:
            raise AppException(400, f"文件超过 {settings.MAX_UPLOAD_MB}MB 上限")
        if not raw:
            raise AppException(400, "上传的文件是空的")

        # 落盘文件名加随机前缀:避免同名覆盖,也避免用户文件名里的路径分隔符
        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        stored_path = upload_dir / f"{uuid4().hex}_{Path(filename).name}"
        stored_path.write_bytes(raw)

        doc = await self.doc_repo.create(
            kb_id=kb_id,
            file_name=filename,
            file_size=len(raw),
            file_type=suffix.lstrip("."),
            storage_path=str(stored_path),
            status=DocumentStatus.UPLOADED,
            upload_user=user_id,
        )
        await self.session.commit()
        return self._to_response(doc)

    async def list_documents(self, kb_id: int) -> list[DocumentResponse]:
        await self.get_kb(kb_id)
        docs = await self.doc_repo.list_by_kb(kb_id)
        return [self._to_response(d) for d in docs]

    async def get_document(self, kb_id: int, document_id: int) -> DocumentResponse:
        doc = await self._require_document(kb_id, document_id)
        return self._to_response(doc)

    async def list_chunks(self, kb_id: int, document_id: int) -> list[ChunkResponse]:
        await self._require_document(kb_id, document_id)
        chunks = await self.chunk_repo.list_by_document(document_id)
        return [ChunkResponse.model_validate(c) for c in chunks]

    async def delete_document(self, kb_id: int, document_id: int) -> None:
        """删除文档及其切块(向量随行删除),并清理落盘文件。"""
        doc = await self._require_document(kb_id, document_id)
        storage_path = doc.storage_path

        await self.chunk_repo.delete_by_document(document_id)
        await self.doc_repo.delete(doc)
        await self.session.commit()
        # 检索缓存即刻失效,防止删掉的文档在 TTL 内仍能搜到(测试抓出的问题)
        await bump_version()

        if storage_path:
            try:
                Path(storage_path).unlink(missing_ok=True)
            except OSError as e:
                # 文件删除失败不应让接口失败(DB 已清理)
                logger.warning("删除落盘文件失败 %s: %s", storage_path, e)

    # ── 检索预览 ──────────────────────────────────────────

    async def search(self, query: str, kb_id: int | None, top_k: int) -> list[SearchHit]:
        """直接跑一遍混合检索,用于调参与演示(不经过 LLM)。"""
        if kb_id is not None:
            await self.get_kb(kb_id)
        chunks = await retrieve(
            self.session, query, kb_ids=[kb_id] if kb_id else None, top_k=top_k
        )
        return [
            SearchHit(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                file_name=c.file_name,
                content=c.content,
                rrf_score=c.rrf_score,
            )
            for c in chunks
        ]

    # ── 内部 ──────────────────────────────────────────────

    async def _require_document(self, kb_id: int, document_id: int) -> Document:
        doc = await self.doc_repo.get_by_id(document_id)
        if doc is None or doc.kb_id != kb_id:
            raise AppException(404, "文档不存在")
        return doc

    @staticmethod
    def _to_response(doc: Document) -> DocumentResponse:
        resp = DocumentResponse.model_validate(doc)
        resp.status_text = DocumentStatus.TEXT.get(doc.status, "未知")
        return resp
