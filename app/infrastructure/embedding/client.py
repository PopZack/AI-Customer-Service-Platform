"""Embedding 客户端:fastembed 本地 ONNX 推理(进程内,无外部服务)。

与 infrastructure/llm 的两点关键差异:

1. **必须用线程池包装**。LLM 是异步 HTTP 客户端,本身 await 友好;而 fastembed 是
   同步 CPU 推理(单次编码几十毫秒),直接调用会在 async 环境里阻塞整个事件循环。
   因此所有推理都走 `asyncio.to_thread`。

2. **模型懒加载单例**。加载含 ONNX 会话初始化(首次还含约 90MB 下载),必须复用,
   否则每次请求重载一次模型会慢到不可用。

模型名与维度见 app/ai/rag/config.py(写死,不做配置项)。
"""
import asyncio
import os
from collections.abc import Sequence
from pathlib import Path

# OpenBLAS / OpenMP 在部分环境(容器、线程栈受限的桌面环境)下会因线程栈分配失败而报
# "OpenBLAS error: Memory allocation still failed after 10 retries, giving up"。
# onnxruntime 依赖它,且这两个变量**必须在导入 numpy/onnxruntime 之前设置才生效**,
# 所以放在模块顶部,并在 app/main.py 最顶部再设一次作为双保险。
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

# 以下两个 import 刻意放在环境变量设置之后(本项目 ruff 未启用 E402)。
from fastembed import TextEmbedding

from app.ai.rag.config import EMBEDDING_DIM, EMBEDDING_MODEL_NAME

_model: TextEmbedding | None = None


def _cache_dir() -> Path:
    """模型缓存目录。

    不能用 fastembed 默认的 %TEMP%/fastembed_cache:临时目录被系统清理后,
    下次启动要重新下载 90MB。放到用户级持久缓存目录下。
    """
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
    return base / "fastembed_cache"


# 有效 onnx 模型文件的最小体积。bge-small-zh 的 model_optimized.onnx 约 90MB,
# 用 1MB 作阈值足以识别"下载失败产生的 0 字节 / 截断文件"。
_MIN_VALID_ONNX_BYTES = 1_000_000


def _model_dir_name() -> str:
    """fastembed 从 CDN 解压后的模型目录名,规则是 fast-<模型名末段>。"""
    return f"fast-{EMBEDDING_MODEL_NAME.split('/')[-1]}"


def _resolve_specific_model_path(cache: Path) -> str | None:
    """本地已有完整模型时返回其目录,用于绕过 fastembed 的下载/缓存解析逻辑。

    为什么必须这么做:fastembed 的解析优先级是
        specific_model_path → HuggingFace 缓存(local_files_only=True) → CDN
    国内网络下 HF 下载可能产出**0 字节**的 model_optimized.onnx,而这个损坏的 HF
    缓存一旦落盘就会被持续优先命中,报 `ModelProto does not have a graph`,
    且不会自动降级去用 CDN 拉到的完好副本。

    显式指定 specific_model_path 是最高优先级,可彻底绕开该问题。
    """
    model_dir = cache / _model_dir_name()
    if not model_dir.is_dir():
        return None
    for onnx_file in model_dir.glob("*.onnx"):
        if onnx_file.stat().st_size >= _MIN_VALID_ONNX_BYTES:
            return str(model_dir)
    return None


def _load_model_sync() -> TextEmbedding:
    """同步加载模型(带单例缓存)。仅供线程池内部调用。"""
    global _model
    if _model is None:
        cache = _cache_dir()
        cache.mkdir(parents=True, exist_ok=True)
        # 注意参数名是 cache_dir:fastembed 0.8 用 cache_dir,
        # 传 local_cache_dir 会被 **kwargs 静默吞掉,缓存设置不生效。
        kwargs: dict = {
            "model_name": EMBEDDING_MODEL_NAME,
            "cache_dir": str(cache),
        }
        specific = _resolve_specific_model_path(cache)
        if specific:
            kwargs["specific_model_path"] = specific
        _model = TextEmbedding(**kwargs)
    return _model


def _passages_sync(texts: list[str]) -> list[list[float]]:
    """同步编码文档片段。"""
    model = _load_model_sync()
    return [vec.tolist() for vec in model.passage_embed(texts)]


def _query_sync(text: str) -> list[float]:
    """同步编码查询串。"""
    model = _load_model_sync()
    vecs = list(model.query_embed([text]))
    return vecs[0].tolist()


async def init_embedding() -> bool:
    """启动时预热模型。返回是否成功。

    失败不抛异常:embedding 不可用时应用仍应能启动(知识库功能降级),
    由调用方通过 is_embedding_available() 判断并给出明确错误。
    """
    try:
        await asyncio.to_thread(_load_model_sync)
        return True
    except Exception:  # noqa: BLE001 —— 刻意吞掉任何加载异常:模型缺失/损坏时应用仍要能启动
        return False


async def close_embedding() -> None:
    """释放模型引用(fastembed 无显式 close,置空即可让 GC 回收)。"""
    global _model
    _model = None


def is_embedding_available() -> bool:
    """模型是否已加载(无需 await)。仅反映"已预热",未预热时调用 embed_* 仍会触发加载。"""
    return _model is not None


def embedding_dim() -> int:
    """当前向量维度(与 pgvector 列定义一致)。"""
    return EMBEDDING_DIM


# ── 对外接口(async)────────────────────────────────────


async def embed_passages(texts: Sequence[str]) -> list[list[float]]:
    """批量编码文档片段。用于文档入库。

    用 passage_embed 而非 embed:bge 系列是非对称模型,文档与查询走不同前缀,
    混用会静默降低检索质量。
    """
    if not texts:
        return []
    return await asyncio.to_thread(_passages_sync, list(texts))


async def embed_query(text: str) -> list[float]:
    """编码查询串。用于检索时编码用户问题。"""
    return await asyncio.to_thread(_query_sync, text)
