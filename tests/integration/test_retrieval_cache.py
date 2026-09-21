"""检索缓存的集成测试:同查询第二次搜索应命中缓存;/metrics 应可观测。"""

import pytest


@pytest.mark.asyncio
async def test_同查询第二次搜索命中缓存(client, auth_headers: dict):
    """同一查询连搜两次:第二次必须命中 Redis 缓存,且指标可见。"""
    from app.common import metrics

    # 走 HTTP 建库 + 上传(复用 helper)
    kb_id = await _create_kb(client, auth_headers)
    await _upload_and_wait(client, auth_headers, kb_id)

    payload = {"query": "退款多久能到账", "top_k": 5}
    r1 = await client.post(f"/api/v1/knowledge-bases/{kb_id}/search", json=payload, headers=auth_headers)
    assert r1.status_code == 200
    assert r1.json()["data"]["total"] > 0

    hits_before = metrics.value("retrieval_cache_hits_total")

    r2 = await client.post(f"/api/v1/knowledge-bases/{kb_id}/search", json=payload, headers=auth_headers)
    assert r2.status_code == 200
    # 结果必须与第一次一致(来自缓存)
    assert r2.json()["data"] == r1.json()["data"]
    assert metrics.value("retrieval_cache_hits_total") == hits_before + 1, "第二次搜索应命中缓存"


# ── 复用 test_knowledge_rag 的 helper ─────────────────


async def _create_kb(client, headers) -> int:
    r = await client.post("/api/v1/knowledge-bases", json={"name": "缓存测试库"}, headers=headers)
    return r.json()["data"]["id"]


async def _upload_and_wait(client, headers, kb_id: int) -> int:
    import asyncio

    content = (
        "# 售后服务政策\n\n"
        "## 退款时效\n"
        "用户提交退款申请后,系统会在 1 个工作日内完成审核。"
        "审核通过后,款项一般 3 到 5 个工作日退回原支付渠道。\n"
    ).encode()
    r = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        headers=headers,
        files={"file": ("售后.md", content, "text/markdown")},
    )
    doc_id = r.json()["data"]["id"]
    for _ in range(60):
        await asyncio.sleep(0.5)
        d = await client.get(
            f"/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}", headers=headers
        )
        if d.json()["data"]["status"] in (4, 5):
            break
    return doc_id
