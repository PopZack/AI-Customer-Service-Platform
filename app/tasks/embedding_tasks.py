"""Embedding 异步任务。

第 14 阶段(RAG 知识库)填充:
- 接收 Chunk → 调用 Embedding 模型 → 写入 Milvus
- 更新 Document 状态为已索引
"""
