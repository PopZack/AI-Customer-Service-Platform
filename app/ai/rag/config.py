"""RAG 配置常量(第 14 阶段 M1)。

为什么这些值写死在代码里、而不做成 .env 配置项:

embedding 模型名与向量维度是一对强绑定关系。换模型意味着**所有已入库向量全部失效、
必须全量重建**。把它做成配置项是"假灵活性":改了配置却没重建向量,检索会静默返回
垃圾结果 —— 比直接报错更难排查。

所以这里写死为常量。换模型时必须同时做两件事:
  1. 改本文件的 EMBEDDING_MODEL_NAME / EMBEDDING_DIM
  2. 写一条重建 document_chunk.embedding 的迁移

入库时会把当前模型名写入 `knowledge_base.embedding_model`,用于日后识别哪些 chunk
是旧模型算出来的,而不是全库盲冲。

技术选型:
  - 向量库:pgvector(复用现有 PostgreSQL,不引入 Milvus)
  - embedding:fastembed 本地 ONNX 推理(BAAI/bge-small-zh-v1.5,512 维,模型约 90MB)
全程无需外部服务、无需 API key,可离线运行。
"""

# ── Embedding ────────────────────────────────────────────
EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
EMBEDDING_DIM = 512  # 必须与 EMBEDDING_MODEL_NAME 匹配,改了要重建向量

# ── 切块 ─────────────────────────────────────────────────
CHUNK_SIZE = 480  # 目标块长度(字符)
CHUNK_OVERLAP_RATIO = 0.12  # 块间重叠比例(bge 系列建议 10%~15%)
MIN_CHUNK_SIZE = 60  # 短于此长度不单独成块,并入前一块
MAX_CHUNK_CHARS = 1200  # 单块硬上限,防止超长段落把上下文撑爆

# ── 检索 ─────────────────────────────────────────────────
RETRIEVAL_TOP_K = 6  # 最终送入 LLM 的片段数
RETRIEVAL_CANDIDATES = 20  # 每路召回的候选数(RRF 融合前)
RRF_K = 60  # RRF(Reciprocal Rank Fusion)平滑常数,论文默认值
MAX_CONTEXT_CHARS = 4000  # 拼进 prompt 的检索内容总长度上限

# ── 文件解析 ─────────────────────────────────────────────
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}
