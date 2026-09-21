"""混合检索:向量 + 关键词两路召回,RRF 融合(第 14 阶段 M1)。

为什么混合:纯向量检索对"精确术语/型号/编号"类查询不稳(语义近邻≠字面命中),
纯关键词对"换个说法"的查询不稳。两路互补,RRF(Reciprocal Rank Fusion)
只依赖排名而非分数,天然规避两路分数量纲不可比的问题。

关键词路:中文没有默认分词器(需 zhparser),这里用**字符二元组(bigram)匹配**:
把查询切成 bigram,统计块内容命中的 bigram 数作为得分。对客服场景的
短查询(3~15 字)足够鲁棒,且能被 pg_trgm GIN 索引加速。
"""
import logging
import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag.cache import get_cached, set_cached
from app.ai.rag.config import RETRIEVAL_CANDIDATES, RETRIEVAL_TOP_K, RRF_K
from app.ai.rag.vector_store import vector_store
from app.infrastructure.embedding import embed_query

logger = logging.getLogger(__name__)

# 仅保留中日韩文字、字母、数字;bigram 在这些字符内滑动
_TERM_CHARS = re.compile(r"[\u4e00-\u9fff\uf900-\ufaffa-zA-Z0-9]+")
_ASCII_WORD = re.compile(r"[a-zA-Z0-9]+")

# 关键词路最多用的 bigram 数(防止长查询生成几十个 ILIKE 拖垮查询)
_MAX_KEYWORD_TERMS = 8


@dataclass
class RetrievedChunk:
    """检索命中的一个块。"""

    chunk_id: int
    document_id: int
    kb_id: int | None
    file_name: str
    content: str
    rrf_score: float
    vector_distance: float | None = None  # 向量路命中时才有


def _build_keyword_terms(query: str) -> list[str]:
    """从查询中提取检索词:ASCII 单词整体保留,中文按 bigram 切。"""
    terms: list[str] = []
    for seg in _TERM_CHARS.findall(query):
        if _ASCII_WORD.fullmatch(seg):
            if seg.lower() not in [t.lower() for t in terms]:
                terms.append(seg)
            continue
        for i in range(len(seg) - 1):
            bg = seg[i : i + 2]
            if bg not in terms:
                terms.append(bg)
    # 查询太短切不出 bigram(如单字"退"),退化为整串
    if not terms and query.strip():
        terms = [query.strip()]
    return terms[:_MAX_KEYWORD_TERMS]


async def _keyword_search(
    session: AsyncSession, query: str, kb_ids: list[int] | None, limit: int
) -> list[dict]:
    """关键词路:bigram ILIKE 命中计数排序。"""
    terms = _build_keyword_terms(query)
    if not terms:
        return []

    params: dict = {"top_k": limit}
    conditions = []
    score_expr = []
    for i, t in enumerate(terms):
        key = f"g{i}"
        params[key] = f"%{t}%"
        conditions.append(f"dc.content ILIKE :{key}")
        score_expr.append(f"(CASE WHEN dc.content ILIKE :{key} THEN 1 ELSE 0 END)")

    kb_filter = ""
    if kb_ids:
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
               ({' + '.join(score_expr)}) AS matched
        FROM document_chunk dc
        JOIN document d ON d.id = dc.document_id
        WHERE d.status = 4
          AND ({' OR '.join(conditions)})
          {kb_filter}
        ORDER BY matched DESC, dc.id ASC
        LIMIT :top_k
    """
    result = await session.execute(text(sql), params)
    return [dict(row._mapping) for row in result.fetchall()]


def _rrf_fuse(rankings: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    """Reciprocal Rank Fusion:score = Σ 1/(k + rank)。rank 从 1 计。"""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


async def retrieve(
    session: AsyncSession,
    query: str,
    kb_ids: list[int] | None = None,
    top_k: int = RETRIEVAL_TOP_K,
) -> list[RetrievedChunk]:
    """混合检索主入口:向量 + 关键词 → RRF → top_k。

    外层套了 Redis 结果缓存(Phase 20):相同查询直接回上次结果,
    跳过 embedding 推理与双路 SQL。只缓存非空结果,Redis 不可用时
    退化为直查 —— 缓存是提速,不是正确性前提。

    任何一路失败(如 embedding 模型未加载)不致命:降级为另一路的结果。
    两路都空则返回空列表(调用方据此走"无知识"分支)。
    """
    cached = await get_cached(query, kb_ids, top_k)
    if cached is not None:
        logger.debug("检索缓存命中: %s", query[:40])
        return cached

    results = await _retrieve_uncached(session, query, kb_ids, top_k)
    await set_cached(query, kb_ids, top_k, results)
    return results


async def _retrieve_uncached(
    session: AsyncSession,
    query: str,
    kb_ids: list[int] | None,
    top_k: int,
) -> list[RetrievedChunk]:
    """真正的混合检索(无缓存版)。"""
    details: dict[int, dict] = {}
    rankings: list[list[int]] = []

    # ── 向量路 ──
    try:
        qvec = await embed_query(query)
        vec_rows = await vector_store.search(session, qvec, RETRIEVAL_CANDIDATES, kb_ids)
        if vec_rows:
            rankings.append([r["chunk_id"] for r in vec_rows])
            for r in vec_rows:
                details[r["chunk_id"]] = r
    except Exception:
        # 向量路属于增强能力,失败要让关键词路继续跑,不能把整个聊天打断。
        # 常见原因:embedding 模型未加载、向量列不存在。
        # 这里刻意降级而非抛出:检索降级 ≠ 聊天不可用。
        logger.warning("向量检索失败,本轮降级为纯关键词检索", exc_info=True)

    # ── 关键词路 ──
    kw_rows = await _keyword_search(session, query, kb_ids, RETRIEVAL_CANDIDATES)
    if kw_rows:
        rankings.append([r["chunk_id"] for r in kw_rows])
        for r in kw_rows:
            details.setdefault(r["chunk_id"], r)

    if not rankings:
        return []

    fused = _rrf_fuse(rankings)
    top_ids = sorted(fused, key=lambda cid: fused[cid], reverse=True)[:top_k]

    results: list[RetrievedChunk] = []
    for cid in top_ids:
        d = details[cid]
        results.append(
            RetrievedChunk(
                chunk_id=cid,
                document_id=d["document_id"],
                kb_id=d["kb_id"],
                file_name=d["file_name"],
                content=d["content"],
                rrf_score=fused[cid],
                vector_distance=d.get("distance"),
            )
        )
    return results


def build_context_block(chunks: list[RetrievedChunk], max_chars: int) -> str:
    """把检索结果编排成喂给 LLM 的参考资料块(带编号,便于引用标注)。"""
    parts: list[str] = []
    used = 0
    for i, c in enumerate(chunks, start=1):
        snippet = c.content
        remain = max_chars - used
        if remain <= 100:  # 剩余空间放不下有意义的内容就停
            break
        if len(snippet) > remain:
            snippet = snippet[:remain] + "…"
        parts.append(f"[{i}] (来源: {c.file_name})\n{snippet}")
        used += len(snippet) + len(c.file_name) + 16
    return "\n\n".join(parts)
