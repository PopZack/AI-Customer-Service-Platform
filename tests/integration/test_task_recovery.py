"""Phase 17 精简补强的测试:启动恢复扫描 + 任务重试包装。

背景:BackgroundTasks 随进程死亡,文档会卡在中间状态。
- recover_stuck_document_ids: 找出卡住的文档(纯查询)
- process_document_with_retry: 失败(FAILED)后自动重跑
"""

from pathlib import Path

import pytest

from app.models.knowledge import Document, DocumentStatus, KnowledgeBase


async def _make_kb_and_stuck_doc(client, headers, db_session, status: int, with_file: bool = True) -> int:
    """造一个知识库 + 一个指定状态的文档(不走上传接口,模拟"被重启打断"的现场)。"""
    from app.config.settings import get_settings
    from app.models.knowledge import Document

    kb_id = (await client.post("/api/v1/knowledge-bases", json={"name": "恢复测试库"}, headers=headers)).json()["data"]["id"]

    storage_path = None
    if with_file:
        corpus = "# 售后\n\n## 退款\n退款审核 1 个工作日内完成,款项 3 到 5 个工作日退回。\n"
        p = Path(get_settings().UPLOAD_DIR) / f"recovery_{status}_{id(db_session)}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(corpus, encoding="utf-8")
        storage_path = str(p)

    doc = Document(
        kb_id=kb_id,
        file_name="被中断的文档.md",
        file_size=100,
        file_type="md",
        storage_path=storage_path,
        status=status,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc.id


@pytest.mark.asyncio
async def test_恢复扫描_只找中间状态的文档(client, auth_headers, db_session):
    """卡在 0/1/2/3 的文档要被恢复;已完成/失败的不要。"""
    from app.tasks.document_tasks import recover_stuck_document_ids

    stuck_id = await _make_kb_and_stuck_doc(client, auth_headers, db_session, DocumentStatus.CHUNKING)
    done_id = await _make_kb_and_stuck_doc(client, auth_headers, db_session, DocumentStatus.INDEXED)

    ids = await recover_stuck_document_ids()

    assert stuck_id in ids, "卡在切块中的文档必须被找回"
    assert done_id not in ids, "已完成的文档不该被重复入队"


@pytest.mark.asyncio
async def test_恢复后重跑能走完索引(client, auth_headers, db_session):
    """找回的文档重新处理,应走到完成(或明确的失败),不再卡住。"""
    from sqlalchemy import select

    from app.tasks.document_tasks import (
        process_document_with_retry,
        recover_stuck_document_ids,
    )

    doc_id = await _make_kb_and_stuck_doc(client, auth_headers, db_session, DocumentStatus.EMBEDDING)
    assert doc_id in await recover_stuck_document_ids()

    await process_document_with_retry(doc_id)

    doc = (await db_session.execute(select(Document).where(Document.id == doc_id))).scalar_one()
    await db_session.refresh(doc)
    assert doc.status in (DocumentStatus.INDEXED, DocumentStatus.FAILED), (
        f"恢复处理后不应再卡在中间状态,实际 status={doc.status} ({doc.error_reason})"
    )


@pytest.mark.asyncio
async def test_重试包装_失败会重跑成功即止(monkeypatch, db_session):
    """第一次失败 → 自动重跑;第二次成功 → 立即返回,不再多跑。"""
    from app.tasks import document_tasks

    # 造一个真实文档(不入上传流程,重试包装只按 id 找状态)
    kb = KnowledgeBase(name="重试测试库", status=1)
    doc = Document(
        kb_id=1, file_name="x.md", file_size=1, file_type="md",
        storage_path=None, status=DocumentStatus.PARSING,
    )
    db_session.add(kb)
    await db_session.flush()
    doc.kb_id = kb.id
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    calls = {"n": 0}

    async def fake_process(document_id: int) -> None:
        calls["n"] += 1
        # 第一次失败,第二次成功
        status = DocumentStatus.FAILED if calls["n"] == 1 else DocumentStatus.INDEXED
        await document_tasks._set_status(document_id, status, "boom" if calls["n"] == 1 else None)

    monkeypatch.setattr(document_tasks, "process_document", fake_process)

    await document_tasks.process_document_with_retry(doc.id, max_attempts=3)
    assert calls["n"] == 2, "失败后应重跑,成功后应立即停止"

    await db_session.refresh(doc)
    assert doc.status == DocumentStatus.INDEXED


@pytest.mark.asyncio
async def test_重试包装_重试耗尽保持失败(monkeypatch, db_session):
    """永久性失败(如扫描版 PDF)重试也不会成功 —— 耗尽后保持 FAILED,不无限循环。"""
    from app.tasks import document_tasks

    kb = KnowledgeBase(name="重试耗尽测试库", status=1)
    db_session.add(kb)
    await db_session.flush()
    doc = Document(
        kb_id=kb.id, file_name="y.md", file_size=1, file_type="md",
        storage_path=None, status=DocumentStatus.PARSING,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    calls = {"n": 0}

    async def always_fail(document_id: int) -> None:
        calls["n"] += 1
        await document_tasks._set_status(document_id, DocumentStatus.FAILED, "永久失败")

    monkeypatch.setattr(document_tasks, "process_document", always_fail)

    await document_tasks.process_document_with_retry(doc.id, max_attempts=2)
    assert calls["n"] == 2, "恰好跑 max_attempts 次"

    await db_session.refresh(doc)
    assert doc.status == DocumentStatus.FAILED
