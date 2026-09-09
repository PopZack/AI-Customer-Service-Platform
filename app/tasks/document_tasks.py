"""文档处理异步任务。

第 17 阶段(消息队列 / Worker)填充:
- 文档上传后的解析(PDF / Word / Markdown → 纯文本)
- 文本分块(Chunk)
- 触发 embedding_tasks 入向量库
"""
