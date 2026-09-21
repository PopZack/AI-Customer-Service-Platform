"""转人工判定(第 16 阶段 V8)。

两条触发路径:

**显式** —— 用户点「转人工」按钮,或模型调用 `handoff_to_human` 工具。
**隐式** —— 连续 N 次检索为空。语义是"知识库确实覆盖不了这类问题",
此时继续让 AI 硬答只会产出幻觉,不如交给人。

隐式计数为什么放 Redis 而不是数据库:
  - 它是短期会话状态,不是审计数据,不值得落库;
  - 天然需要 TTL(会话闲置即自动重置),Redis 直接满足;
  - 项目已有 Redis,不新增依赖。

key: `chat:empty_retrieval:{conversation_id}`,命中非空检索时**立即清零**
(连续计数一旦被打断就该从头算)。
"""
import logging

from app.infrastructure.redis import get_redis

logger = logging.getLogger(__name__)

#: 连续多少次检索为空就转人工
IMPLICIT_HANDOFF_THRESHOLD = 3
#: 计数有效期(秒):超过这段时间没有活动就重置,避免旧会话的计数被反复累加
EMPTY_RETRIEVAL_TTL = 3600
#: Redis key 前缀
_KEY = "chat:empty_retrieval:{cid}"


def _key(conversation_id: int) -> str:
    return _KEY.format(cid=conversation_id)


async def record_retrieval_result(conversation_id: int, empty: bool) -> int:
    """记录一次检索结果,返回「当前连续为空的次数」。

    Redis 不可用时返回 0 —— 隐式转人工是增强能力,不该因为它挂掉而阻断对话。
    """
    try:
        redis = await get_redis()
        key = _key(conversation_id)
        if empty:
            count = await redis.incr(key)
            await redis.expire(key, EMPTY_RETRIEVAL_TTL)
            return int(count)
        # 一旦检索命中,连续计数归零
        await redis.delete(key)
        return 0
    except Exception:
        logger.warning("记录检索结果失败(Redis 不可用?),隐式转人工计数已跳过", exc_info=True)
        return 0


async def should_handoff_implicitly(conversation_id: int) -> bool:
    """连续为空次数是否已达阈值。"""
    try:
        redis = await get_redis()
        raw = await redis.get(_key(conversation_id))
        return raw is not None and int(raw) >= IMPLICIT_HANDOFF_THRESHOLD
    except Exception:  # noqa: BLE001
        return False


async def reset(conversation_id: int) -> None:
    """清空计数(转人工后或会话结束时调用)。"""
    try:
        redis = await get_redis()
        await redis.delete(_key(conversation_id))
    except Exception:
        logger.warning("重置隐式转人工计数失败", exc_info=True)


async def empty_retrieval_count(conversation_id: int) -> int:
    """当前连续为空次数(供接口展示/调试)。"""
    try:
        redis = await get_redis()
        raw = await redis.get(_key(conversation_id))
        return int(raw) if raw is not None else 0
    except Exception:  # noqa: BLE001
        return 0
