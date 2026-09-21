"""RAG 评测脚本:对评测集跑检索 + 生成回答,产出 Recall 与 faithfulness 表格。

用法(在项目根目录):
    uv run python evals/run_eval.py

流程:
    1. 建临时知识库 → 上传语料 → 等索引完成(真实 embedding + pgvector)
    2. 逐条用例:混合检索 → 判定 Recall@1 / Recall@3(期望小节是否在结果里)
    3. 用与生产一致的 RAG prompt 生成回答
    4. 两道质检:
       - 关键词覆盖:回答是否含 must_mention 里的要点(硬校验)
       - faithfulness:LLM 当裁判,回答是否完全被资料支撑、不编造(软校验)
    5. 输出逐条表格 + 汇总,末尾清理临时知识库

注意:faithfulness 用同一个 LLM 评判有"自我偏好"的局限,
但它能稳定抓住"编造资料里没有的信息"这类最危险的失败。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# 评测输出要干净:关掉 DEBUG 的 SQL 回显(env 优先级高于 .env,须在导入 app 前设置)
os.environ.setdefault("DEBUG", "false")

from app.ai.prompt.system import build_rag_system_prompt, get_system_prompt  # noqa: E402
from app.ai.rag.cache import bump_version  # noqa: E402
from app.ai.rag.config import MAX_CONTEXT_CHARS, RETRIEVAL_TOP_K  # noqa: E402
from app.ai.rag.retriever import build_context_block, retrieve  # noqa: E402
from app.config.settings import get_settings  # noqa: E402
from app.infrastructure.database.session import async_session_factory  # noqa: E402
from app.infrastructure.embedding import init_embedding  # noqa: E402
from app.infrastructure.llm import chat_non_stream, init_llm  # noqa: E402
from app.models.knowledge import Document, DocumentStatus, KnowledgeBase  # noqa: E402
from app.tasks.document_tasks import process_document  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
JUDGE_PROMPT = """你是严格的质检员。判断下面的【回答】是否完全被【资料】支撑。

规则:
1. 回答中的每个事实性陈述都必须能在资料中找到依据,否则为"编造"。
2. 资料里没有答案、而回答明确表示不知道/建议转人工,为"合格"(这是期望行为)。
3. 回答里包含资料之外的猜测性信息(哪怕是常识),也算"编造"。

【资料】
{context}

【问题】{question}

【回答】{answer}

只输出一个词:合格 或 编造"""


def load_cases(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


async def setup_corpus(corpus_text: str) -> tuple[int, int]:
    """建临时库并索引语料,返回 (kb_id, doc_id)。"""
    async with async_session_factory() as s:
        kb = KnowledgeBase(name=f"评测临时库 {int(time.time())}", status=1)
        s.add(kb)
        await s.commit()
        await s.refresh(kb)
        doc = Document(
            kb_id=kb.id,
            file_name="客服知识库.md",
            file_size=len(corpus_text.encode("utf-8")),
            file_type="md",
            storage_path=None,
            status=DocumentStatus.UPLOADED,
        )
        # 评测脚本直接把语料写到临时文件,复用生产索引流程
        tmp = Path(get_settings().UPLOAD_DIR) / "eval_corpus.md"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(corpus_text, encoding="utf-8")
        doc.storage_path = str(tmp)
        s.add(doc)
        await s.commit()
        await s.refresh(doc)
        kb_id, doc_id = kb.id, doc.id

    await process_document(doc_id)
    async with async_session_factory() as s:
        doc = await s.get(Document, doc_id)
        if doc.status != DocumentStatus.INDEXED:
            raise RuntimeError(f"语料索引失败: {doc.error_reason}")
    return kb_id, doc_id


async def cleanup(kb_id: int, doc_id: int) -> None:
    """删掉临时库与文档,并把缓存版本推走。"""
    from sqlalchemy import delete as sa_delete

    from app.models.knowledge import DocumentChunk

    async with async_session_factory() as s:
        await s.execute(sa_delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))
        await s.execute(sa_delete(Document).where(Document.id == doc_id))
        await s.execute(sa_delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
        await s.commit()
    try:
        Path(get_settings().UPLOAD_DIR, "eval_corpus.md").unlink(missing_ok=True)
    except OSError as e:
        print(f"[warn] 评测语料临时文件删除失败(不影响结果): {e}")
    await bump_version()


async def judge_faithfulness(context: str, question: str, answer: str) -> str:
    """LLM 裁判:返回 合格 / 编造。输出不可解析时重试一次,仍失败记"裁判失败"。"""
    for attempt, budget in enumerate((512, 512, 2048)):
        try:
            verdict = await chat_non_stream(
                [{"role": "user", "content": JUDGE_PROMPT.format(context=context, question=question, answer=answer)}],
                temperature=0.0,
                # 8 会输出空串:Agent Plan 的模型在正文前有 token 开销,实测 64 起才有内容。
                # 偶发连续空输出(512 也空),加大到 2048 通常能出内容 —— 疑似推理型输出吞掉了预算。
                max_tokens=budget,
            )
            v = verdict.strip()
            if "合格" in v and "编造" not in v:
                return "合格"
            if "编造" in v:
                return "编造"
            # 返回了别的内容(或空串):重试
            print(f"    [judge] 第 {attempt + 1} 次输出不可解析: {v!r:.60}")
        except Exception as e:  # noqa: BLE001 —— 裁判失败不应中断整场评测
            print(f"    [judge] 第 {attempt + 1} 次调用异常: {type(e).__name__}")
    return "裁判失败"


async def run(k: int, do_faithfulness: bool) -> None:
    settings = get_settings()
    if do_faithfulness and not settings.LLM_API_KEY:
        print("⚠️ 未配置 LLM_API_KEY,跳过回答生成与 faithfulness,只测检索 Recall。")
        do_faithfulness = False

    cases = load_cases(EVAL_DIR / "rag_eval_set.json")
    corpus = (EVAL_DIR / "corpus.md").read_text(encoding="utf-8")

    print(f"=== 初始化(语料索引 + 模型加载)===")
    await init_embedding()
    await init_llm()
    kb_id, doc_id = await setup_corpus(corpus)
    print(f"临时知识库 #{kb_id} 就绪\n")

    rows: list[dict] = []
    try:
        for c in cases:
            question = c["question"]
            expect = c["expect_section"]
            async with async_session_factory() as s:
                chunks = await retrieve(s, question, kb_ids=[kb_id], top_k=k)
            context = build_context_block(chunks, MAX_CONTEXT_CHARS)

            recall1 = recallk = False
            if expect:
                recall1 = bool(chunks) and expect in chunks[0].content
                recallk = any(expect in ch.content for ch in chunks)

            row = {
                "id": c["id"],
                "question": question,
                "expect": expect or "(应拒答)",
                "recall1": recall1,
                "recallk": recallk,
                "keywords_ok": None,
                "faith": None,
                "_must_mention": c["must_mention"],
            }

            if do_faithfulness:
                if chunks:
                    prompt = build_rag_system_prompt(context)
                else:
                    prompt = get_system_prompt()
                # Agent Plan 非流式调用偶发空输出(疑推理预算被吞),换大预算重试一次
                answer = ""
                for budget in (512, 2048):
                    answer = await chat_non_stream(
                        [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": question},
                        ],
                        max_tokens=budget,
                    )
                    if answer.strip():
                        break
                row["answer"] = answer.replace("\n", " ")
                if c["must_mention"]:
                    # 去掉所有空白再比对:模型写"1个工作日"还是"1 个工作日"是排版差异,不是语义差异
                    flat = "".join(answer.split())
                    row["keywords_ok"] = all("".join(m.split()) in flat for m in c["must_mention"])
                if expect is None:
                    # 拒答题:期望"不知道/无法/转人工"类表态,且没有编造小节内容
                    refused = any(w in answer for w in ("不知道", "无法", "没有找到", "暂未", "转人工", "人工客服"))
                    row["faith"] = "合格" if refused else "未拒答"
                else:
                    row["faith"] = await judge_faithfulness(context, question, answer)

            rows.append(row)
            mark = "✓" if ((not expect) or recall1) else "✗"
            print(f"  {mark} #{c['id']:2d} {question[:36]}")
    finally:
        await cleanup(kb_id, doc_id)
        print("\n(临时知识库已清理)")

    # ── 汇总表 ──
    kn = [r for r in rows if r["expect"] != "(应拒答)"]
    neg = [r for r in rows if r["expect"] == "(应拒答)"]

    print(f"\n{'=' * 78}\n评测结果(k={k}, 共 {len(rows)} 条)\n{'=' * 78}")
    print(f"{'ID':>3} {'Recall@1':^9} {'Recall@k':^9} {'要点粗检':^8} {'faithfulness':^12}  问题")
    for r in rows:
        kw = {True: "✓", False: "✗", None: "-"}[r["keywords_ok"]]
        faith = r["faith"] or "-"
        print(
            f"{r['id']:>3} {('✓' if r['recall1'] else '✗'):^9} "
            f"{('✓' if r['recallk'] else '✗'):^9} {kw:^6} {faith:^12}  {r['question'][:30]}"
        )

    print(f"\n── 汇总 ──")
    print(f"Recall@1        {sum(r['recall1'] for r in kn)}/{len(kn)} = {sum(r['recall1'] for r in kn)/len(kn):.0%}")
    print(f"Recall@{k}        {sum(r['recallk'] for r in kn)}/{len(kn)} = {sum(r['recallk'] for r in kn)/len(kn):.0%}")
    kw_rows = [r for r in kn if r["keywords_ok"] is not None]
    if kw_rows:
        n_ok = sum(r["keywords_ok"] for r in kw_rows)
        print(f"要点覆盖(粗检)  {n_ok}/{len(kw_rows)}   ← 连续子串匹配,改写会误报,漏的看人工复核区")
    if neg and all(r["faith"] for r in neg):
        refused = sum(1 for r in neg if r["faith"] == "合格")
        print(f"拒答正确率      {refused}/{len(neg)}")
    faith_rows = [r for r in rows if r["faith"] in ("合格", "编造", "未拒答")]
    if faith_rows:
        ok = sum(1 for r in faith_rows if r["faith"] == "合格")
        print(f"faithfulness    {ok}/{len(faith_rows)} = {ok/len(faith_rows):.0%}")

    # 人工复核区:要点未命中 / 被判编造的回答原文
    review = [r for r in rows if r["keywords_ok"] is False or r["faith"] == "编造"]
    if review:
        print(f"\n── 人工复核({len(review)} 条)──")
        for r in review:
            print(f"\n#{r['id']} {r['question']}")
            if r["keywords_ok"] is False:
                print(f"  要求要点: {r.get('_must_mention')}")
            print(f"  回答: {(r.get('answer') or '')[:300]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=3, help="Recall@k 的 k")
    parser.add_argument("--skip-faithfulness", action="store_true", help="只测检索,不生成回答")
    args = parser.parse_args()
    asyncio.run(run(k=args.k, do_faithfulness=not args.skip_faithfulness))
