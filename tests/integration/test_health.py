"""健康检查与静态资源（集成测试的地基用例）。

这一组同时充当"测试基建自检"：如果测试库、Redis、embedding 初始化有问题，
这里会最先失败。
"""
from httpx import AsyncClient


async def test_存活探针(client: AsyncClient):
    """顶层 /health 不查依赖，只代表进程活着。"""
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_就绪探针会真实检查数据库与Redis(client: AsyncClient):
    """v1 /health 是 readiness：必须真的连通 DB 与 Redis 才返回 ok。"""
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["database"] == "connected"
    assert body["redis"] == "connected"


async def test_演示页可访问(client: AsyncClient):
    """静态演示页可访问，且根路径会重定向过去。"""
    r = await client.get("/static/index.html")
    assert r.status_code == 200
    # 页面标题在 UI 改版时可能变,断言只锁"这是本项目的演示页"的最小特征:
    # 页面主标识 + 后端交互入口(且不被版本库里的旧文案绑死)
    assert "AI 客服控制台" in r.text
    assert "/api/v1" in r.text

    # 根路径是 307 重定向（follow_redirects=False 才看得到）
    r = await client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"].endswith("/static/index.html")


async def test_未认证请求被拒绝(client: AsyncClient):
    """所有业务接口都要求 Bearer token。"""
    for path in ("/api/v1/knowledge-bases", "/api/v1/tickets", "/api/v1/conversations"):
        r = await client.get(path)
        assert r.status_code == 401, f"{path} 竟然返回 {r.status_code}"
