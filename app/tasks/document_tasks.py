"""文档处理异步任务(第 14 阶段 M1)。

链路:解析 → 切块 → 向量化 → 写向量 → 置完成

用 FastAPI BackgroundTasks 触发,**不引入消息队列**(Phase 17 已按精简收尾路线砍掉)。
注意:任务在响应返回之后才执行,那时请求作用域的 DB session 已经关闭,
所以这里每一步都自己开新 session —— 与 SSE 端点同样的处理方式。
状态每步提交,前端轮询 /documents/{id} 能看到实时进度。
"""
import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import delete, select

from app.ai.rag.cache import bump_version
from app.ai.rag.chunker import split_text
from app.ai.rag.config import EMBEDDING_MODEL_NAME
from app.ai.rag.parser import UnsupportedFileTypeError, extract_text
from app.ai.rag.vector_store import vector_store
from app.config.settings import get_settings
from app.infrastructure.database.session import async_session_factory
from app.infrastructure.embedding import embed_passages
from app.models.knowledge import Document, DocumentChunk, DocumentStatus, KnowledgeBase

logger = logging.getLogger(__name__)


async def _set_status(document_id: int, status: int, error: str | None = None) -> None:
    """更新文档状态并提交(独立 session,短事务)。"""
    if async_session_factory is None:
        return
    async with async_session_factory() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            return
        doc.status = status
        if error is not None:
            doc.error_reason = error
        await session.commit()


async def _replace_chunks(document_id: int, chunks: list[str]) -> list[int]:
    """重建文档切块(先清后插),返回新块 ID 列表。

    先清后插是为了支持失败重跑 —— 否则重复索引会让同一文档的块成倍增长。
    """
    async with async_session_factory() as session:
        await session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        records = [
            DocumentChunk(
                document_id=document_id,
                chunk_no=idx,
                content=content,
                embedding_status=0,
            )
            for idx, content in enumerate(chunks)
        ]
        session.add_all(records)
        await session.commit()
        return [r.id for r in records]


async def _embed_and_store(chunk_ids: list[int], chunks: list[str], batch: int) -> None:
    """分批向量化并写入向量列。分批是为了控制 ONNX 推理的峰值内存。"""
    for start in range(0, len(chunks), batch):
        window_texts = chunks[start : start + batch]
        window_ids = chunk_ids[start : start + batch]
        vectors = await embed_passages(window_texts)
        async with async_session_factory() as session:
            await vector_store.upsert(session, window_ids, vectors)
            await session.commit()


async def _mark_indexed(document_id: int, kb_id: int) -> None:
    """置为完成,并把本次使用的 embedding 模型名记进知识库。"""
    async with async_session_factory() as session:
        kb = await session.get(KnowledgeBase, kb_id)
        if kb is not None:
            kb.embedding_model = EMBEDDING_MODEL_NAME
        doc = await session.get(Document, document_id)
        if doc is not None:
            doc.status = DocumentStatus.INDEXED
            doc.error_reason = None
        await session.commit()


async def process_document(document_id: int) -> None:
    """完整的文档索引流程。任何异常都落到 FAILED 并记录原因,不向外抛。"""
    if async_session_factory is None:
        logger.error("DATABASE_URL 未配置,无法处理文档 %s", document_id)
        return

    async with async_session_factory() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            logger.warning("文档 %s 不存在,跳过", document_id)
            return
        storage_path = doc.storage_path
        kb_id = doc.kb_id

    try:
        if not storage_path:
            raise ValueError("文档缺少 storage_path,无法解析。")

        # ── 1. 解析 ──
        await _set_status(document_id, DocumentStatus.PARSING)
        text = extract_text(Path(storage_path))
        if not text.strip():
            raise ValueError(
                "未能提取到任何文字。若为扫描版 PDF(图片型)需先做 OCR,当前不支持。"
            )

        # ── 2. 切块 ──
        await _set_status(document_id, DocumentStatus.CHUNKING)
        chunks = split_text(text)
        if not chunks:
            raise ValueError("切块结果为空,文件可能没有有效正文。")
        chunk_ids = await _replace_chunks(document_id, chunks)

        # ── 3. 向量化 + 写向量 ──
        await _set_status(document_id, DocumentStatus.EMBEDDING)
        batch = get_settings().EMBED_BATCH_SIZE
        await _embed_and_store(chunk_ids, chunks, batch)

        # ── 4. 完成 ──
        await _mark_indexed(document_id, kb_id)
        logger.info("文档 %s 索引完成,共 %s 块", document_id, len(chunks))

    except UnsupportedFileTypeError as e:
        await _set_status(document_id, DocumentStatus.FAILED, str(e))
        logger.warning("文档 %s 类型不支持: %s", document_id, e)
    except Exception as e:
        await _set_status(document_id, DocumentStatus.FAILED, f"{type(e).__name__}: {e}")
        logger.exception("文档 %s 索引失败", document_id)
    finally:
        # 无论成败,只要跑过索引,块的内容/向量就可能变过 —— 检索缓存全部作废。
        # (旧键不删,靠 TTL 过期;新版本号的键从现在起才写。)
        await bump_version()


# ── 入队 / 重试 / 启动恢复(Phase 17 精简决策的补强)───────────────
#
# 背景:BackgroundTasks 跟随进程生死 —— 进程重启会把"解析中/向量化中"的任务
# 直接丢掉,文档永远卡在中间状态。这里用三个小函数补掉这个伤,同时留好
# 二次开发接缝:将来上 procrastinate / Redis Stream 时,只改 enqueue_document
# 的函数体,调用方(knowledge router / 启动恢复)一行都不用动。

#: 视为"卡在中间状态"的文档状态集合(0=已上传未开工也算)
_RECOVERABLE_STATUSES = (
    DocumentStatus.UPLOADED,
    DocumentStatus.PARSING,
    DocumentStatus.CHUNKING,
    DocumentStatus.EMBEDDING,
)


def enqueue_document(add_task: Callable[..., None], document_id: int) -> None:
    """任务入队的**唯一入口**。

    add_task 传 BackgroundTasks.add_task。整个代码库不允许绕过这里
    直接 add_task(process_document) —— 否则将来换队列时会有漏网之鱼。
    """
    add_task(process_document_with_retry, document_id)


async def process_document_with_retry(document_id: int, max_attempts: int = 2) -> None:
    """带重试的处理。process_document 失败会把状态置为 FAILED,据此判断是否重跑。

    重试是"尽力而为":永久性失败(如扫描版 PDF 提不出文字)重试也不会成功,
    只是多花一次尝试 —— 不做错误分类,换来的是零额外状态。
    """
    for attempt in range(1, max_attempts + 1):
        await process_document(document_id)
        async with async_session_factory() as session:
            doc = await session.get(Document, document_id)
            if doc is None:  # 处理期间被删除:不重试
                return
            if doc.status != DocumentStatus.FAILED:
                return
        if attempt < max_attempts:
            logger.warning("文档 %s 第 %s 次处理失败,稍后重试", document_id, attempt)
            await asyncio.sleep(1)
    logger.error("文档 %s 重试 %s 次后仍失败,保持 FAILED 状态", document_id, max_attempts)


async def recover_stuck_document_ids() -> list[int]:
    """找出卡在中间状态的文档(进程重启打断了 BackgroundTasks)。

    只负责"找",不负责"跑" —— 入队方式(应用内 asyncio task / 将来的队列)
    由调用方决定,这样本函数保持纯查询、可在测试里直接断言返回值。
    """
    if async_session_factory is None:
        return []
    async with async_session_factory() as session:
        rows = await session.execute(
            select(Document.id).where(Document.status.in_(_RECOVERABLE_STATUSES))
        )
        return [row[0] for row in rows]
