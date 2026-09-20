"""Embedding 基础设施层:fastembed 本地 ONNX 推理。

与 llm/ 的 __init__ 风格保持一致,统一在此 re-export。
"""
from app.infrastructure.embedding.client import (
    close_embedding,
    embed_passages,
    embed_query,
    embedding_dim,
    init_embedding,
    is_embedding_available,
)

__all__ = [
    "close_embedding",
    "embed_passages",
    "embed_query",
    "embedding_dim",
    "init_embedding",
    "is_embedding_available",
]
