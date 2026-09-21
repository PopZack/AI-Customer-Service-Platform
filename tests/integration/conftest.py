"""集成测试夹具：测试库生命周期 + 基础设施初始化。

会话级流程：
  重建测试库 → 装扩展 → create_all 建表 → 初始化 DB/Redis/LLM/embedding

每个测试结束后 **TRUNCATE 所有表**（RESTART IDENTITY CASCADE）做隔离。
不用"每测试一个事务 + 回滚"的原因：聊天 SSE 与文档索引后台任务都会自己开
独立 session（刻意的设计，见 ChatService 注释），它们不在测试事务里，
回滚式隔离对它们无效。

⚠️ 测试库名从 `os.environ["DATABASE_URL"]` 直接推导，**不要** `from tests.conftest
import TEST_DB_NAME` —— pytest 会以不同模块名重复导入 conftest，
跨模块导入会让 tests/conftest.py 的模块级代码跑第二遍，
测试库名被重复追加后缀（踩过：`xxx_test_test`）。
"""
import os

import psycopg2
import pytest
import pytest_asyncio
from sqlalchemy import text

import app.models  # noqa: F401  —— 必须导入，否则 Base.metadata 里没有表
from app.infrastructure.database.base import Base

#: 测试库名（此时 DATABASE_URL 已被 tests/conftest.py 换成了测试库）
TEST_DB_NAME = os.environ["DATABASE_URL"].rsplit("/", 1)[-1]


def _sync_dsn(dbname: str) -> str:
    """把 asyncpg 连接串转成 psycopg2 可用的 DSN（只换驱动前缀与库名）。"""
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    return url.rsplit("/", 1)[0] + "/" + dbname


def _pg_available() -> bool:
    """PostgreSQL 是否可达（不可达时跳过集成测试，而不是报一堆连接错误）。"""
    try:
        psycopg2.connect(_sync_dsn("postgres"), connect_timeout=5).close()
        return True
    except Exception:  # noqa: BLE001 —— 这里就是"探测能否连上",任何异常都等价于不可用
        return False


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    """会话级：重建测试库并装好扩展。"""
    if not _pg_available():
        pytest.skip("PostgreSQL 不可达，跳过集成测试（先 docker compose up -d）")

    admin = psycopg2.connect(_sync_dsn("postgres"))
    admin.autocommit = True
    with admin.cursor() as cur:
        # WITH (FORCE) 会踢掉残留连接，避免 "database is being accessed by other users"
        cur.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)')
        cur.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    admin.close()

    # 扩展是**数据库级**的，新库里必须重新创建
    target = psycopg2.connect(_sync_dsn(TEST_DB_NAME))
    target.autocommit = True
    with target.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    target.close()

    yield


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _infra(_prepare_test_database):
    """会话级：建表 + 初始化全部基础设施，结束后释放。

    embedding 用**真实模型**（不是 mock）—— 它是本地纯函数，
    真跑才能验证"切块 → 向量化 → 检索"这条链路真的通；
    mock 掉 embedding 会让 RAG 测试退化成"永远命中"的假测试。
    LLM 则在具体用例里用假客户端替换（见 test_chat_sse.py）。
    """
    from app.infrastructure.database import close_db, init_db
    from app.infrastructure.database.session import engine
    from app.infrastructure.embedding import close_embedding, init_embedding
    from app.infrastructure.llm import close_llm, init_llm
    from app.infrastructure.redis import close_redis, init_redis

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await init_db()
    await init_redis()
    await init_llm()
    if not await init_embedding():
        pytest.skip("embedding 模型不可用，跳过需要检索的集成测试")

    yield

    await close_embedding()
    await close_llm()
    await close_redis()
    await close_db()
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _truncate_tables(_infra):
    """每个测试后清空所有表与相关 Redis 状态，保证用例之间互不影响。"""
    yield

    from app.infrastructure.database.session import engine
    from app.infrastructure.redis import get_redis

    names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))

    # ⚠️ 必须一起清 Redis：隐式转人工的计数 key 是 `chat:empty_retrieval:{会话ID}`，
    # 而 TRUNCATE ... RESTART IDENTITY 会让下一条用例复用同样的会话 ID，
    # 上一条用例遗留的计数就会被算进来 —— 表现为"莫名其妙提前转人工"的偶发失败。
    try:
        redis = await get_redis()
        keys = [k async for k in redis.scan_iter(match="chat:*")]
        if keys:
            await redis.delete(*keys)
    except Exception as exc:  # noqa: BLE001 —— Redis 不可用不影响数据库清理
        # 清理失败只记录不抛：它不该掩盖真正的测试失败
        print(f"[warn] 清理 Redis 测试键失败: {exc}")


@pytest_asyncio.fixture
async def db_session():
    """直连测试库的 session，供用例直接做断言查询。"""
    from app.infrastructure.database.session import async_session_factory

    async with async_session_factory() as session:
        yield session
