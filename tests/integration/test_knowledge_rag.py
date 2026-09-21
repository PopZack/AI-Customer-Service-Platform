"""知识库与 RAG 集成测试：上传 → 解析 → 切块 → 向量化 → 混合检索。

⚠️ 这里的 embedding 是**真实模型**，不是 mock。
mock 掉 embedding 会让 RAG 测试退化成"永远命中"的假测试 ——
检索分数、切块粒度、向量维度这些问题一个都测不出来。
它跑得慢一点（首次加载模型 + 编码），但换来的是"这条链路真的通"。

文档索引本身走 FastAPI BackgroundTasks。Starlette 会在响应体发送后、
同一个 ASGI 调用内等待后台任务完成，所以 `await client.post(...)` 返回时
通常已经索引完了。这里仍然用轮询而不是直接断言 status=4 ——
不依赖框架的调度细节，也让测试在后台任务真变成异步时依然成立。
"""
import asyncio

import pytest
from httpx import AsyncClient

DOC = """# 售后服务政策

## 退款时效
用户提交退款申请后,系统会在 1 个工作日内完成审核。审核通过后,款项一般 3 到 5 个工作日退回原支付渠道。如遇银行系统维护或法定节假日,可能延迟至 7 个工作日。

## 退款条件
商品需保持完好,不影响二次销售,吊牌与包装需齐全。定制类商品一经制作不支持无理由退款。虚拟商品一旦售出不支持退款。

## 发票问题
电子发票会在订单完成后 24 小时内自动发送至预留邮箱。如需开具增值税专用发票,请提供公司全称、税号与开户行信息,处理周期为 3 个工作日。

## 物流与配送
现货商品在付款后 48 小时内发出。偏远地区(新疆、西藏、内蒙古部分地区)配送时效延长 2 至 3 天。

## 账号与安全
请勿将账号密码告知他人。如发现账号异常登录,请立即修改密码并联系客服冻结账号。平台不会以任何形式索要支付密码或短信验证码。
"""


async def _create_kb(client: AsyncClient, headers: dict, name: str = "测试知识库") -> int:
    r = await client.post("/api/v1/knowledge-bases", json={"name": name}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


async def _upload_and_wait(
    client: AsyncClient, headers: dict, kb_id: int, name: str = "售后政策.md", content: str = DOC
) -> int:
    """上传文档并轮询到索引完成，返回文档 ID。"""
    r = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        headers=headers,
        files={"file": (name, content.encode("utf-8"), "text/markdown")},
    )
    assert r.status_code == 200, r.text
    doc_id = r.json()["data"]["id"]

    for _ in range(60):
        r = await client.get(
            f"/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}", headers=headers
        )
        doc = r.json()["data"]
        if doc["status"] in (4, 5):
            break
        await asyncio.sleep(0.3)

    assert doc["status"] == 4, f"索引未完成: status={doc['status']} reason={doc['error_reason']}"
    return doc_id


async def test_上传文档会被切块并向量化(client: AsyncClient, auth_headers: dict):
    """端到端：一个 5 小节的文档应切成多块，且每块都写入向量。"""
    kb_id = await _create_kb(client, auth_headers)
    doc_id = await _upload_and_wait(client, auth_headers, kb_id)

    r = await client.get(
        f"/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}/chunks", headers=auth_headers
    )
    assert r.status_code == 200
    chunks = r.json()["data"]["items"]

    # 5 个小节 → 至少 3 块(切块策略见 app/ai/rag/chunker.py)
    assert len(chunks) >= 3, f"只切出 {len(chunks)} 块,切块策略可能失效"
    # 所有块都必须已向量化
    assert all(c["embedding_status"] == 1 for c in chunks), "存在未向量化的块"
    # 标题应作为上下文前缀保留在块里(中文文档切掉标题后语义会变模糊)
    assert any("退款" in c["content"] for c in chunks)


async def test_混合检索能命中对应小节(client: AsyncClient, auth_headers: dict):
    """这是 RAG 是否真的可用的判据：问某小节的事，Top-1 就该是那一节。"""
    kb_id = await _create_kb(client, auth_headers)
    await _upload_and_wait(client, auth_headers, kb_id)

    cases = [
        ("退款多久能到账", "退款时效"),
        ("发票什么时候发给我", "发票问题"),
        ("新疆发货要几天", "物流与配送"),
        ("账号被别人登录了怎么办", "账号与安全"),
        ("定制商品可以退吗", "退款条件"),
    ]
    hit = 0
    for query, section in cases:
        r = await client.post(
            f"/api/v1/knowledge-bases/{kb_id}/search",
            json={"query": query, "top_k": 3},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        hits = r.json()["data"]["hits"]
        assert hits, f"{query!r} 竟然没有任何命中"
        if section in hits[0]["content"]:
            hit += 1

    # 允许个别措辞差异，但整体命中率必须够高，否则检索形同虚设
    assert hit >= 4, f"Top-1 仅命中 {hit}/5，检索质量不达标"


async def test_知识库与文档的过滤_删除(client: AsyncClient, auth_headers: dict):
    """删除文档后，它的块与向量都不该再被检索到。"""
    kb_id = await _create_kb(client, auth_headers)
    doc_id = await _upload_and_wait(client, auth_headers, kb_id)

    r = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/search",
        json={"query": "退款多久到账", "top_k": 5},
        headers=auth_headers,
    )
    assert r.json()["data"]["total"] > 0

    r = await client.delete(
        f"/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}", headers=auth_headers
    )
    assert r.status_code == 200

    r = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/search",
        json={"query": "退款多久到账", "top_k": 5},
        headers=auth_headers,
    )
    assert r.json()["data"]["total"] == 0, "删除后仍能检索到,块或向量未清理干净"


async def test_支持格式之外的文件被拒绝(client: AsyncClient, auth_headers: dict):
    kb_id = await _create_kb(client, auth_headers)
    r = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        headers=auth_headers,
        files={"file": ("virus.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert r.status_code == 400
    assert "不支持" in r.json()["message"]


async def test_空文件被拒绝(client: AsyncClient, auth_headers: dict):
    kb_id = await _create_kb(client, auth_headers)
    r = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        headers=auth_headers,
        files={"file": ("empty.md", b"", "text/markdown")},
    )
    assert r.status_code == 400


async def test_不存在的知识库返回404(client: AsyncClient, auth_headers: dict):
    r = await client.get("/api/v1/knowledge-bases/999999/documents", headers=auth_headers)
    assert r.status_code == 404

    r = await client.post(
        "/api/v1/knowledge-bases/999999/documents",
        headers=auth_headers,
        files={"file": ("a.md", b"# hi", "text/markdown")},
    )
    assert r.status_code == 404


async def test_没有正文的文档会以失败原因落库(client: AsyncClient, auth_headers: dict):
    """解析不出文字的文档必须给出可读原因，而不是静默失败。"""
    kb_id = await _create_kb(client, auth_headers)
    r = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        headers=auth_headers,
        files={"file": ("blank.md", b"   \n\n   \n", "text/markdown")},
    )
    assert r.status_code == 200
    doc_id = r.json()["data"]["id"]

    for _ in range(40):
        r = await client.get(
            f"/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}", headers=auth_headers
        )
        doc = r.json()["data"]
        if doc["status"] in (4, 5):
            break
        await asyncio.sleep(0.3)

    assert doc["status"] == 5, "空白文档不该被当作索引成功"
    assert doc["error_reason"], "失败时必须写入原因,否则用户无从排查"


@pytest.mark.parametrize("top_k", [1, 5, 20])
async def test_检索预览的top_k参数(client: AsyncClient, auth_headers: dict, top_k: int):
    kb_id = await _create_kb(client, auth_headers)
    await _upload_and_wait(client, auth_headers, kb_id)

    r = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/search",
        json={"query": "退款", "top_k": top_k},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert len(r.json()["data"]["hits"]) <= top_k
