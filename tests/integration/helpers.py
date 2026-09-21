"""集成测试共用辅助：样例文档、上传并等待索引、SSE 解析。

抽出来的原因：知识库测试与聊天测试都需要"先有一个已索引的知识库"，
否则聊天里的 `search_knowledge` 工具检索不到任何东西，测不出真东西。
"""
import asyncio
import json

from httpx import AsyncClient

#: 覆盖 5 个小节的样例文档，用于验证切块与检索
SAMPLE_DOC = """# 售后服务政策

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


async def create_kb(client: AsyncClient, headers: dict, name: str = "测试知识库") -> int:
    """建一个知识库，返回 kb_id。"""
    r = await client.post("/api/v1/knowledge-bases", json={"name": name}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


async def upload_and_wait(
    client: AsyncClient,
    headers: dict,
    kb_id: int,
    name: str = "售后政策.md",
    content: str = SAMPLE_DOC,
) -> int:
    """上传文档并轮询到索引完成(status=4)，返回文档 ID。

    用轮询而不是直接断言 status=4：不依赖框架"何时跑后台任务"的调度细节。
    """
    r = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        headers=headers,
        files={"file": (name, content.encode("utf-8"), "text/markdown")},
    )
    assert r.status_code == 200, r.text
    doc_id = r.json()["data"]["id"]

    doc: dict = {}
    for _ in range(60):
        r = await client.get(f"/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}", headers=headers)
        doc = r.json()["data"]
        if doc["status"] in (4, 5):
            break
        await asyncio.sleep(0.3)

    assert doc.get("status") == 4, f"索引未完成: {doc}"
    return doc_id


async def create_conversation(client: AsyncClient, headers: dict, title: str = "测试会话") -> int:
    r = await client.post(
        "/api/v1/conversations", json={"title": title, "channel": "web"}, headers=headers
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def parse_sse(text: str) -> list[dict]:
    """把 SSE 响应体解析成事件 dict 列表(只取 data 行)。"""
    events = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:") :].strip()
            if payload:
                events.append(json.loads(payload))
    return events


def event_types(events: list[dict]) -> list[str]:
    """取出事件类型序列，便于断言流程。"""
    return [e.get("type") for e in events]


def joined_content(events: list[dict]) -> str:
    """把 content 事件拼成完整回答。"""
    return "".join(e.get("content", "") for e in events if e.get("type") == "content")
