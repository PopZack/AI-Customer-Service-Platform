# AI-Customer-Service-Platform

> 企业 AI 客服平台:让 AI 尽可能自动解决客户问题,解决不了时无缝交给人工客服。

基于 **模块化单体(Modular Monolith)+ 分层架构 + AI 能力层** 设计,配套完整设计文档见 [design_docs/](./design_docs)。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | FastAPI + Pydantic |
| 包管理 | uv |
| 关系数据库 | PostgreSQL(第 10 阶段启用) |
| 缓存/异步 | Redis(第 12 阶段启用) |
| 向量库 | Milvus(第 14 阶段 RAG) |
| 部署 | Docker + Nginx(第 19 阶段) |

> 当前进度:**第 9 阶段 — V1 基础后端**(工程骨架 + 健康检查)。

## 快速开始

```bash
# 1. 安装依赖(会创建 .venv 并生成 uv.lock)
uv sync

# 2. 复制环境变量模板(第 9 阶段无需配置,均为占位)
cp .env.example .env

# 3. 启动开发服务器
uv run uvicorn app.main:app --reload
```

启动后:

- 健康检查:<http://localhost:8000/health>
- API 文档(Swagger):<http://localhost:8000/docs>
- ReDoc:<http://localhost:8000/redoc>

## 工程结构

```
app/
├── main.py            # 应用入口
├── api/               # 总路由 + 依赖注入
├── modules/           # 业务模块(auth/user/chat/knowledge/ticket)
├── ai/                # AI 能力层(router/agent/rag/memory/prompt/llm/tools)
├── infrastructure/    # 外部技术实现(database/redis/milvus/mq/storage/llm)
├── common/            # 通用层(response/exceptions/middleware/logging/utils)
├── config/            # 配置(settings/logging)
├── models/ schemas/ tasks/
tests/
```

## 开发路线

完整 22 阶段路线见 [design_docs/0-完整开发路线图](./design_docs/0-企业AI客服平台-完整开发路线图-V1.0.md)。
