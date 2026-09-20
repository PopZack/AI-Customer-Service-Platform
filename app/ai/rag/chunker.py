"""文本切块:把长文档切成适合 embedding 的片段(第 14 阶段 M1)。

不引入 langchain 等重依赖,保持策略可控、可调试。策略:

1. **标题行(# / ## …)是软边界**。同一小节内容不会被不同小节"挤"在一起:
   当前块已达到 MIN_CHUNK_SIZE 时,遇到新标题就断块 —— 政策/FAQ 类文档通常
   一节一个主题,小节级粒度对检索最有利。若当前块还太短,则继续合并,避免
   一份满是短小标题的文档碎成一堆没有信息量的片段。
2. **标题作为上下文前缀**带到该小节的每一块上。中文技术文档里,"退款政策"这种标题
   被切掉后正文本体往往语义模糊,带上标题能明显提升检索命中率。
3. 正文按空行切段,再贪心累积到 CHUNK_SIZE。
4. 同小节内的块间按 CHUNK_OVERLAP_RATIO 回带尾部,避免语义被硬切断;
   **跨小节断块时不回带**,避免把一个主题的句子带进另一个主题的块里。
5. 超长单段(长于 MAX_CHUNK_CHARS)按中文句末标点二次切分,每段补上标题。

块大小用字符数近似而非 token 数:bge-small-zh 对中文约 1 字 ≈ 1 token,
字符数足够指导切块,不值得为此引入 tokenizer 依赖。
"""
import re

from app.ai.rag.config import (
    CHUNK_OVERLAP_RATIO,
    CHUNK_SIZE,
    MAX_CHUNK_CHARS,
    MIN_CHUNK_SIZE,
)

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+\S")
_SENTENCE_RE = re.compile(r"(?<=[。！？；.!?;])")
_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_TRAILING_WS_RE = re.compile(r"[ \t\u3000]+$", re.MULTILINE)


def _normalize(text: str) -> str:
    """统一换行、去掉行尾空白、压缩连续空行。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TRAILING_WS_RE.sub("", text)
    return _MULTI_BLANK_RE.sub("\n\n", text).strip()


def _to_blocks(text: str) -> list[tuple[str, str]]:
    """把正文拆成 (标题, 段落) 列表。标题相同的连续段落归属同一小节。"""
    blocks: list[tuple[str, str]] = []
    heading = ""
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        body = "\n".join(buf).strip()
        if body:
            blocks.append((heading, body))
        buf = []

    for line in text.split("\n"):
        if _HEADING_RE.match(line):
            flush()
            heading = line.strip().lstrip("#").strip()
            continue
        if not line.strip():
            flush()
            continue
        buf.append(line)
    flush()
    return blocks


def _split_long(piece: str) -> list[str]:
    """把超长段落按句子边界切成不超过 MAX_CHUNK_CHARS 的段。"""
    if len(piece) <= MAX_CHUNK_CHARS:
        return [piece]

    segments: list[str] = []
    cur = ""
    for sentence in _SENTENCE_RE.split(piece):
        if not sentence:
            continue
        if cur and len(cur) + len(sentence) > MAX_CHUNK_CHARS:
            segments.append(cur)
            cur = sentence
        else:
            cur += sentence
    if cur:
        segments.append(cur)
    return segments


def _overlap_tail(chunk: str) -> str:
    """取上一块尾部作为下一块的前缀,长度按 CHUNK_OVERLAP_RATIO 计算。"""
    size = int(CHUNK_SIZE * CHUNK_OVERLAP_RATIO)
    if size <= 0 or len(chunk) <= size:
        return ""
    return chunk[-size:]


def split_text(text: str) -> list[str]:
    """把整篇文档切成块列表。空输入返回空列表。"""
    normalized = _normalize(text)
    if not normalized:
        return []

    # ── 1. 展开成 (标题, 片段),超长小节二次切分并给每段补标题 ──
    pieces: list[tuple[str, str]] = []
    for heading, body in _to_blocks(normalized):
        piece = f"{heading}\n{body}" if heading else body
        segments = _split_long(piece)
        if len(segments) > 1 and heading:
            segments = [
                seg if seg.startswith(heading) else f"{heading}\n{seg}"
                for seg in segments
            ]
        for seg in segments:
            pieces.append((heading, seg))

    # ── 2. 贪心成块,标题变化且当前块够长时断块 ──
    chunks: list[str] = []
    cur = ""
    cur_heading: str | None = None

    for heading, seg in pieces:
        if not cur:
            cur, cur_heading = seg, heading
            continue

        section_break = cur_heading is not None and heading != cur_heading
        size_full = len(cur) + len(seg) + 1 > CHUNK_SIZE
        break_here = size_full or (section_break and len(cur) >= MIN_CHUNK_SIZE)

        if break_here:
            chunks.append(cur)
            if section_break:
                # 换小节:不继承上一节尾部,避免跨主题污染
                cur = seg
            else:
                tail = _overlap_tail(cur)
                cur = f"{tail}\n{seg}" if tail else seg
            cur_heading = heading
        else:
            cur = f"{cur}\n{seg}"

    if cur:
        # 尾块太短则并回上一块,避免产生"半句话"碎片
        if chunks and len(cur) < MIN_CHUNK_SIZE:
            chunks[-1] = f"{chunks[-1]}\n{cur}"
        else:
            chunks.append(cur)

    return [c.strip() for c in chunks if c.strip()]
