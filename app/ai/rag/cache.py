"""检索结果缓存:Redis 缓存 query → 检索结果,跳过 embedding + 双路查询。

为什么值得做:同一条用户追问(「那发票呢?」「再说一遍」)以及多轮对话里
反复出现的相似问法,每次都要跑一次 embedding 推理 + 两条 SQL。
缓存命中把这一整段降到一次 Redis GET。

失效策略:数据版本号 + TTL 兜底 + 只缓存**非空**结果。
  - **版本号**:Redis 里存一个全局数据版本 `rag:dataver`,文档索引/删除时 INCR;
    缓存键里编入版本,旧键即刻失效(不删,靠 TTL 过期)。
    这是测试抓出来的正确性问题 —— 纯 TTL 会让"删掉的文档"在一小时内仍能搜到。
  - 只缓存非空:空结果意味着"知识库回答不了",此时恰恰是用户最需要
    实时性的场景(刚上传完文档就来提问,不能让他等一小时缓存过期)。

Redis 不可用时全部静默跳过 —— 缓存是性能优化,不是正确性前提。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import TYPE_CHECKING

from app.ai.rag.config import EMBEDDING_MODEL_NAME
from app.config.settings import get_settings
from app.infrastructure.redis.client import get_redis

if TYPE_CHECKING:
    # 仅类型标注用。运行时在函数内导入:retriever 顶层 import 本模块,
    # 而本模块又需要 retriever 的 RetrievedChunk,顶层互引会构成循环导入。
    from app.ai.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

_KEY_PREFIX = "rag:qcache"
#: 全局数据版本键:文档索引/删除时 INCR,缓存键编入该版本
_DATAVER_KEY = "rag:dataver"
_WS_RE = re.compile(r"\s+")


async def current_version() -> str:
    """当前数据版本。Redis 不可用时返回固定值 —— 此时缓存读写都拿不到 Redis,
    等价于缓存关闭,版本值无所谓。"""
    try:
        r = await get_redis()
        return str(await r.get(_DATAVER_KEY) or "0")
    except Exception:  # noqa: BLE001 —— 缓存是提速手段,Redis 挂了不影响正确性
        return "0"


async def bump_version() -> None:
    """数据版本 +1,使所有已缓存检索结果即刻失效。文档索引/删除时调用。"""
    try:
        r = await get_redis()
        await r.incr(_DATAVER_KEY)
    except Exception:
        logger.debug("数据版本递增失败(Redis 不可用?)", exc_info=True)


def make_cache_key(query: str, kb_ids: list[int] | None, top_k: int, version: str) -> str:
    """缓存键:数据版本 + 归一化查询 + 知识库范围 + top_k + embedding 模型名。

    模型名进键:换模型后旧缓存必须天然失效,不能靠 TTL 慢慢过期。
    版本进键:文档增删改后旧键即刻失效(测试抓出的删除后仍可搜到的问题)。
    """
    q = _WS_RE.sub(" ", query.strip().lower())
    kbs = ",".join(str(i) for i in sorted(kb_ids)) if kb_ids else "*"
    raw = f"{EMBEDDING_MODEL_NAME}|{kbs}|{top_k}|{version}|{q}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{_KEY_PREFIX}:{digest}"


async def get_cached(query: str, kb_ids: list[int] | None, top_k: int) -> list[RetrievedChunk] | None:
    """命中返回缓存结果;未命中或 Redis 不可用返回 None。"""
    from app.common import metrics

    if get_settings().RETRIEVAL_CACHE_TTL <= 0:
        return None
    try:
        r = await get_redis()
        raw = await r.get(make_cache_key(query, kb_ids, top_k, await current_version()))
    except Exception:  # noqa: BLE001 —— Redis 挂了只影响提速,不影响正确性
        return None
    if raw is None:
        metrics.inc("retrieval_cache_misses_total")
        return None
    from app.ai.rag.retriever import RetrievedChunk

    try:
        data = json.loads(raw)
        metrics.inc("retrieval_cache_hits_total")
        return [RetrievedChunk(**item) for item in data]
    except (ValueError, TypeError):
        # 反序列化失败(如字段变更)等价于未命中,顺手删掉脏数据
        logger.warning("检索缓存反序列化失败,已删除脏键")
        metrics.inc("retrieval_cache_misses_total")
        try:
            await r.delete(make_cache_key(query, kb_ids, top_k, await current_version()))
        except Exception:
            logger.debug("脏缓存键删除失败,等待 TTL 过期", exc_info=True)
        return None


async def set_cached(query: str, kb_ids: list[int] | None, top_k: int, chunks: list[RetrievedChunk]) -> None:
    """缓存非空结果。空结果刻意不缓存(见模块 docstring)。"""
    if not chunks:
        return
    settings = get_settings()
    if settings.RETRIEVAL_CACHE_TTL <= 0:
        return
    try:
        r = await get_redis()
        payload = json.dumps([c.__dict__ for c in chunks], ensure_ascii=False)
        await r.set(
            make_cache_key(query, kb_ids, top_k, await current_version()),
            payload,
            ex=settings.RETRIEVAL_CACHE_TTL,
        )
    except Exception:
        logger.warning("检索缓存写入失败", exc_info=True)
