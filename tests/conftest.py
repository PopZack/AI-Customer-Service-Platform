"""pytest 全局夹具与测试环境准备（第 18 阶段 M3）。

⚠️ 本文件顶部的环境变量设置**必须在任何 app 模块被导入之前执行**。
原因：`app/infrastructure/database/session.py` 在**导入时**就用 settings 建好了
engine，之后再改 DATABASE_URL 已经来不及 —— engine 已经指向开发库了。
所以这里先把 URL 换成测试库，再让后续 import 生效。

测试库策略：**独立的 PostgreSQL 数据库**（`<开发库名>_test`），不是 schema。
本项目检索层有手写 SQL（`document_chunk` 等不带 schema 前缀），
用 schema 会踩 search_path 解析的坑：一旦测试 schema 里缺少某张表，
查询会静默落到 public 的开发表上，测试既读到脏数据又可能写坏开发库。
独立数据库从根上排除这类问题。

不用 SQLite：模型统一用 `BigIntPKMixin`，SQLite 的自增行为与之不符；
而且 pgvector 的 `vector` 类型、`pg_trgm` 索引在 SQLite 上根本不存在。

⚠️ 这里的逻辑必须**幂等**：pytest 可能以不同模块名（`conftest` / `tests.conftest`）
多次导入同一个文件，模块级代码就会执行多次。若不做判断，
测试库名会被反复追加后缀，变成 `xxx_test_test` —— 这个坑真的踩过。
"""
import os

from app.config.settings import Settings, get_settings

TEST_DB_SUFFIX = "_test"


def _test_database_url(url: str) -> tuple[str, str]:
    """由开发库 URL 推导测试库 URL，返回 (测试库 URL, 测试库名)。

    幂等：若库名已以 _test 结尾，不再重复追加。
    """
    base, _, name = url.rpartition("/")
    if not name.endswith(TEST_DB_SUFFIX):
        name += TEST_DB_SUFFIX
    return f"{base}/{name}", name


_dev_url = Settings().DATABASE_URL or ""

if _dev_url:
    _test_url, TEST_DB_NAME = _test_database_url(_dev_url)
    os.environ["DATABASE_URL"] = _test_url
else:  # pragma: no cover - 未配置数据库时集成测试会被跳过
    TEST_DB_NAME = ""

# 测试里会反复注册/登录，必须放开限流，否则会被 429 拦住（默认 5 次/分钟）
os.environ["RATE_LIMIT_MAX_REQUESTS"] = "1000000"

# 关掉 SQL 回显：DEBUG=true 时 echo=True，测试输出会被 SQL 日志淹没
os.environ["DEBUG"] = "false"

# settings 是 lru_cache 的，改完环境变量必须清缓存
get_settings.cache_clear()

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


def pytest_configure(config: pytest.Config) -> None:
    """注册自定义标记，避免 pytest 报 unknown marker 警告。"""
    config.addinivalue_line("markers", "needs_db: 需要 PostgreSQL / Redis 的集成测试")


@pytest.fixture(scope="session")
def test_db_name() -> str:
    """测试库名（integration/conftest.py 也用它，避免跨模块导入导致重复执行）。"""
    return TEST_DB_NAME


@pytest_asyncio.fixture
async def client():
    """ASGI 直连的异步 HTTP 客户端（不启真实端口、不经网络）。

    注意：ASGITransport 不执行 lifespan，因此数据库/Redis/LLM/embedding
    的初始化由 integration/conftest.py 的 `_infra` 夹具显式完成。
    """
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """注册并登录一个随机用户，返回带 Bearer token 的请求头。

    走真实接口拿 token（而不是伪造），这样鉴权链路本身也在测试覆盖内。
    """
    import uuid

    username = f"u{uuid.uuid4().hex[:12]}"
    password = "test123456"

    r = await client.post(
        "/api/v1/auth/register", json={"username": username, "password": password}
    )
    assert r.status_code == 200, r.text

    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
