"""认证链路集成测试：注册 → 登录 → 刷新轮换 → 登出黑名单。

这里刻意走真实 HTTP + 真实 Redis（黑名单与轮换都落在 Redis 上），
而不是 mock —— 双 token 的"轮换吊销"语义只有在真实存储上才验得出来。
"""
import uuid

import pytest
from httpx import AsyncClient

PWD = "test123456"


def _name() -> str:
    return f"u{uuid.uuid4().hex[:12]}"


async def test_注册登录并获取当前用户(client: AsyncClient):
    """完整主路径：注册 → 登录 → 用 token 查自己。"""
    username = _name()
    r = await client.post("/api/v1/auth/register", json={"username": username, "password": PWD})
    assert r.status_code == 200
    assert r.json()["data"]["username"] == username

    r = await client.post("/api/v1/auth/login", json={"username": username, "password": PWD})
    assert r.status_code == 200
    token = r.json()["data"]
    assert token["token_type"] == "bearer"
    assert token["expires_in"] > 0

    r = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token['access_token']}"}
    )
    assert r.status_code == 200
    assert r.json()["data"]["username"] == username


async def test_重复注册被拒绝(client: AsyncClient):
    username = _name()
    assert (
        await client.post("/api/v1/auth/register", json={"username": username, "password": PWD})
    ).status_code == 200

    r = await client.post("/api/v1/auth/register", json={"username": username, "password": PWD})
    assert r.status_code == 400
    assert "已存在" in r.json()["message"]


@pytest.mark.parametrize(
    ("payload", "why"),
    [
        ({"username": "ab", "password": PWD}, "用户名过短"),
        ({"username": "validname", "password": "12345"}, "密码过短"),
        ({"username": "validname"}, "缺密码"),
    ],
)
async def test_参数校验(client: AsyncClient, payload: dict, why: str):
    """请求体校验由 Pydantic 兜住，返回 422 而不是 500。"""
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 422, f"{why} 应被拒绝"


async def test_密码错误返回401(client: AsyncClient):
    username = _name()
    await client.post("/api/v1/auth/register", json={"username": username, "password": PWD})

    r = await client.post("/api/v1/auth/login", json={"username": username, "password": "wrongpwd"})
    assert r.status_code == 401


async def test_不存在的用户登录同样返回401(client: AsyncClient):
    """安全考虑：不区分"用户不存在"与"密码错误"，避免枚举用户名。"""
    r = await client.post("/api/v1/auth/login", json={"username": "nobody_here", "password": PWD})
    assert r.status_code == 401


@pytest.mark.parametrize(
    ("header", "why"),
    [
        (None, "完全没有 Authorization 头"),
        ({"Authorization": "Bearer not-a-jwt"}, "token 不是合法 JWT"),
        ({"Authorization": "Bearer "}, "token 为空"),
    ],
)
async def test_无效token无法访问受保护接口(client: AsyncClient, header, why: str):
    r = await client.get("/api/v1/auth/me", headers=header or {})
    assert r.status_code == 401, f"{why} 应被拒绝"


async def test_刷新会轮换并吊销旧refresh_token(client: AsyncClient):
    """双 token 的核心安全语义：refresh 一次就作废旧的那把。"""
    username = _name()
    await client.post("/api/v1/auth/register", json={"username": username, "password": PWD})
    first = (
        await client.post("/api/v1/auth/login", json={"username": username, "password": PWD})
    ).json()["data"]

    # 第一次刷新：成功，拿到新的 refresh_token
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 200
    second = r.json()["data"]
    assert second["refresh_token"] != first["refresh_token"]

    # 旧的 refresh_token 已被吊销，再用必须失败
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 401
    assert "失效" in r.json()["message"]

    # 新的仍然可用
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]})
    assert r.status_code == 200


async def test_登出后refresh_token失效(client: AsyncClient):
    """登出的核心语义：拉黑后这把 refresh token 再也换不出新 token。"""
    username = _name()
    await client.post("/api/v1/auth/register", json={"username": username, "password": PWD})
    tokens = (
        await client.post("/api/v1/auth/login", json={"username": username, "password": PWD})
    ).json()["data"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    r = await client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    assert r.json()["data"]["revoked"] is True

    # 已吊销的 refresh 不能再换 token
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401

    # access token 是否随登出失效取决于实现:这里是"只吊销 refresh"的策略,
    # 断言它是显式的,避免以后误改成"登出即禁用 access"而无人察觉
    r = await client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200, "当前策略:登出只吊销 refresh,access 到期自然失效"


async def test_重复登出不报错(client: AsyncClient):
    """幂等：重复登出仍返回 200，且 token 保持已吊销状态（不会把它"解封"）。"""
    username = _name()
    await client.post("/api/v1/auth/register", json={"username": username, "password": PWD})
    refresh = (
        await client.post("/api/v1/auth/login", json={"username": username, "password": PWD})
    ).json()["data"]["refresh_token"]

    assert (
        await client.post("/api/v1/auth/logout", json={"refresh_token": refresh})
    ).status_code == 200
    r = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh})
    assert r.status_code == 200
    # 注意语义：revoked=True 表示"该 token 当前处于已吊销状态"，
    # 而不是"本次调用新吊销了它"。所以重复登出仍然返回 True。
    assert r.json()["data"]["revoked"] is True

    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    ).status_code == 401


async def test_登出无法解码的token返回未吊销(client: AsyncClient):
    """revoked=False 的语义是"token 根本解码不了"，无需吊销。"""
    r = await client.post("/api/v1/auth/logout", json={"refresh_token": "not-a-jwt"})
    assert r.status_code == 200
    assert r.json()["data"]["revoked"] is False
