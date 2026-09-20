# 🤖 企业 AI 客服平台

> AI 自动解决客户问题，解决不了无缝交给人工。一套 **模块化单体** 架构，22 个阶段从骨架到生产。

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-green)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-red)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED)](https://www.docker.com/)

---

## ✨ 功能亮点

### 已实现（Phase 9-14）

| 能力 | 说明 | 阶段 |
|---|---|---|
| 🏗️ 工程骨架 | FastAPI + Pydantic 分层架构，模块化单体 | Phase 9 |
| 🗄️ 数据库集成 | SQLAlchemy async + Alembic 迁移 + Repository 模式 | Phase 10 |
| 🔐 用户认证 | 注册 / 登录 / JWT 双 token（access + refresh）/ 刷新轮换 / 登出黑名单 | Phase 11 |
| ⚡ Redis 异步 | 限流中间件 / 健康检查 / 缓存工具类（铺路） | Phase 12 |
| 🤖 LLM + AI Chat | OpenAI 兼容客户端 / SSE 流式输出 / 多轮上下文 / 会话 CRUD | Phase 13 |
| 📚 RAG 知识库 | 文档上传解析切块 / 本地 embedding / pgvector 入库 / 混合检索 / 带引用回答 | Phase 14 |

### 规划中（Phase 15-22）

Agent + Tool → 人工协同 → 测试与工程化 → Docker + CI/CD → 监控 → AI 评估 → 生产优化

> 收尾采用**精简路线**：Phase 15/16 做满，**Phase 17 消息队列跳过**（文档解析与 embedding 改用 FastAPI BackgroundTasks，本项目无高并发场景），Phase 18-22 按精简版收尾。

---

## 🧠 设计思路

### 为什么模块化单体？

先单体、后微服务，是大多数创业项目的正确姿势。**模块化单体** 兼顾开发效率和架构可演进：

```
一个 FastAPI 进程，内部按业务边界划模块
  ↓ 模块间零耦合（只走公共接口）
  ↓ 未来某个模块流量爆了 → 单独拆成微服务
  ↓ 数据库从一库 → 按模块分库
```

**不一开始就上微服务**：分布式事务、链路追踪、服务发现……这些复杂度在 MVP 阶段全是负资产。

### 三层架构

```
Router（薄，只做参数解析）
  ↓
Service（业务逻辑，唯一入口）
  ↓
Repository（CRUD + 查询，Service 唯一的数据访问通道）
```

外加 **Infrastructure** 层隔离外部技术细节（数据库 / Redis / pgvector / LLM / embedding），业务代码不直接碰 `redis.set(...)`、`pg.query(...)`、`llm.stream(...)`、`model.embed(...)`。

### AI 能力独立成层

AI 相关（Router → Agent → RAG → LLM）不混进业务模块，单独在 `app/ai/`，未来可独立部署成 AI 网关。

### SSE 流式的坑

SSE 端点不能用 FastAPI 依赖注入的 DB session——`EventSourceResponse` 返回后依赖就 teardown 了，但 AI 回复要在流式结束后才入库。解决办法：**在 event_generator 内部用 `async_session_factory()` 创建独立 session**，由 generator 自己管理生命周期。

同样的理由适用于**后台任务**：文档上传后要异步做「解析 → 切块 → 向量化」，而那时请求的 session 已关闭，所以 `app/tasks/document_tasks.py` 每一步都自己开新 session、短事务提交，状态才能被前端轮询到。

> ⚠️ 前端注意：`/api/v1/chat` 是 **POST**，而浏览器的 `EventSource` 只支持 GET。
> 所以演示页用 `fetch` + `ReadableStream` 手工解析 SSE 帧（见 `static/index.html`）。

### RAG 的两个关键取舍

**1. 向量库用 pgvector，不用 Milvus。**

复用已在跑的 PostgreSQL，向量与业务数据**同库同事务**——上传文档时「切块入库 + 向量入库」是一个原子操作，不会出现跨库双写的脏状态。代价是放弃了 Milvus 的分布式能力，但本项目单机规模远没到那个量级，换来的是零新增容器、零一致性维护。

**2. 关键词检索用 bigram，不用 `tsvector`。**

PostgreSQL 的全文检索**没有中文分词器**（需要 zhparser 扩展，官方镜像里没有），`tsvector` 对中文基本不可用。这里用**字符二元组匹配**：把查询切成 bigram，统计命中数排序，配合 `pg_trgm` 的 GIN 索引加速。对客服场景的短查询足够鲁棒，且完全在 SQL 内完成。

---

## 🛠️ 技术栈

| 层 | 技术 | 版本 |
|---|---|---|
| 后端框架 | FastAPI + Pydantic | FastAPI 0.110+ / Pydantic 2 |
| Python | uv 包管理 | 3.11+ |
| 数据库 | PostgreSQL（Docker） | 16-alpine |
| ORM | SQLAlchemy async + Alembic | asyncpg / psycopg2 |
| 缓存/异步 | Redis（Docker） | 7-alpine |
| 认证 | bcrypt + PyJWT | 双 token + 黑名单 |
| **LLM** | **openai SDK + sse-starlette** | **OpenAI 兼容接口** |
| **向量库** | **pgvector**（PostgreSQL 扩展，非独立服务） | **0.8.0，512 维** |
| **Embedding** | **fastembed**（进程内 ONNX 推理，无需外部服务 / API key） | **BAAI/bge-small-zh-v1.5** |
| 文档解析 | pymupdf（PDF）+ python-docx（DOCX） | Phase 14 |
| 部署 | Docker Compose | Phase 19 |

---

## 🚀 快速开始

### 前置

- Python 3.11+ + [uv](https://docs.astral.sh/uv/)
- Docker Desktop（跑 PostgreSQL + Redis）

### 一步到位

```bash
# 1. 启动 PostgreSQL + Redis（Docker）
#    ⚠️ postgres 用的是 pgvector/pgvector:pg16 镜像（PG16 + vector 扩展）。
#    网络能直连 Docker Hub 时 compose 会自动拉取；拉不动（国内常见）就先本地构建同名镜像：
#        docker build -t pgvector/pgvector:pg16 docker/pgvector/
#    该 Dockerfile 只用「本地已有的 postgres:16-alpine + Alpine apk 源 +
#    随仓库携带的 pgvector 源码包」，完全不依赖 Docker Hub。
docker compose up -d

# 2. 安装依赖 + 配环境
uv sync --extra dev
cp .env.example .env

# 3. 数据库迁移（会创建 pgvector / pg_trgm 扩展、向量列与 HNSW 索引）
uv run alembic upgrade head

# 4. （可选）配置 LLM，不配置也能跑，AI 聊天会返回 503
#    换 base_url 即可切换厂商:
#    DeepSeek:   https://api.deepseek.com/v1, model=deepseek-chat
#    Qwen:       https://dashscope.aliyuncs.com/compatible-mode/v1, model=qwen-plus
#    Moonshot:   https://api.moonshot.cn/v1, model=moonshot-v1-8k
#    豆包:       https://ark.cn-beijing.volces.com/api/v3
#    编辑 .env:
#      LLM_API_KEY=sk-xxx
#      LLM_BASE_URL=https://api.deepseek.com/v1
#    注意：embedding 用的是本地模型，**不需要**任何 API key。

# 5. 启动
uv run uvicorn app.main:app --reload
```

首次启动会下载 embedding 模型（`BAAI/bge-small-zh-v1.5`，约 90MB），缓存在
`%LOCALAPPDATA%/fastembed_cache`（Windows）或 `~/.cache/fastembed_cache`。
下载失败不影响启动，只是向量检索降级为纯关键词检索。

访问：
- **演示页**：<http://localhost:8000/static/index.html>（上传文档 / 带引用对话 / 检索预览）
- 健康检查（liveness）：<http://localhost:8000/health>
- 健康检查（readiness，含 DB + Redis）：<http://localhost:8000/api/v1/health>
- API 文档（Swagger）：<http://localhost:8000/docs>
- ReDoc：<http://localhost:8000/redoc>

上传的原始文件落在 `./data/uploads/`（已 gitignore）。

### 常用命令

```bash
# 数据库迁移
uv run alembic revision --autogenerate -m "描述"
uv run alembic upgrade head
uv run alembic downgrade -1

# 重新生成依赖锁
uv lock

# 静态检查
uv run ruff check .
uv run ruff format .          # 格式化(ruff 的 formatter 兼容 black,已不再单独引 black)

# 重建 pgvector 镜像(仅当 docker compose 拉不到镜像时需要)
docker build -t pgvector/pgvector:pg16 docker/pgvector/
```

> ⚠️ **已知待收敛**：`uv run ruff check .` 目前**不是全绿**（存量错误，主要是 FastAPI
> 依赖注入写法触发的 `B008`）。收敛排在 Phase 18「测试与工程化」。新代码请保证自己的
> 文件零新增错误 —— 例如用 `Annotated[AsyncSession, Depends(...)]` 代替 `db: AsyncSession = Depends(...)`。

---

## 📡 API 概览

### Auth（已实现）

| 方法 | 端点 | 说明 |
|---|---|---|
| POST | `/api/v1/auth/register` | 注册新用户 |
| POST | `/api/v1/auth/login` | 登录，返回 access + refresh token |
| POST | `/api/v1/auth/refresh` | 用 refresh token 续签（轮换吊销旧 token） |
| POST | `/api/v1/auth/logout` | 登出，吊销 refresh token（幂等） |
| GET | `/api/v1/auth/me` | 获取当前用户信息（需 Bearer access token） |

### Conversations（已实现）

| 方法 | 端点 | 说明 |
|---|---|---|
| POST | `/api/v1/conversations` | 创建会话 |
| GET | `/api/v1/conversations` | 当前用户的会话列表 |
| GET | `/api/v1/conversations/{id}` | 会话详情 |
| GET | `/api/v1/conversations/{id}/messages` | 会话的消息列表 |

### Chat — AI 聊天（SSE 流式）

| 方法 | 端点 | 说明 |
|---|---|---|
| POST | `/api/v1/chat` | AI 聊天，SSE 流式输出 |

请求体：
```json
{
    "conversation_id": 1,
    "message": "退款多久到账？"
}
```

SSE 事件流：
```
data: {"type":"start"}
data: {"type":"content","content":"退款"}
data: {"type":"content","content":"通常"}
data: {"type":"content","content":"会在"}
data: {"type":"error","message":"LLM 超时"}    ← 出错
data: {"type":"done"}
```

回答会基于知识库检索结果，并在正文里标注引用编号（如 `退款一般 3 到 5 个工作日到账[1]`）。

### Knowledge — 知识库与 RAG（Phase 14）

| 方法 | 端点 | 说明 |
|---|---|---|
| POST | `/api/v1/knowledge-bases` | 创建知识库 |
| GET | `/api/v1/knowledge-bases` | 知识库列表 |
| POST | `/api/v1/knowledge-bases/{kb_id}/documents` | 上传文档（multipart），立即返回并异步索引 |
| GET | `/api/v1/knowledge-bases/{kb_id}/documents` | 文档列表 |
| GET | `/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}` | 文档详情（含索引状态与失败原因） |
| GET | `/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}/chunks` | 查看切块结果 |
| DELETE | `/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}` | 删除文档及其切块与向量 |
| POST | `/api/v1/knowledge-bases/{kb_id}/search` | 检索预览：直接看混合检索命中了哪些块 |

支持 PDF / DOCX / MD / TXT，单文件上限 20MB。

**文档索引状态**（对应 `document.status`，前端轮询详情接口即可看到进度）：

```
0 上传中 → 1 解析中 → 2 切块中 → 3 向量化中 → 4 已完成
                                    任意一步失败 → 5 失败（原因写入 error_reason）
```

**检索预览**是调试切块参数最有用的接口——不经过 LLM，直接返回命中的块与 RRF 分数：

```json
// POST /api/v1/knowledge-bases/1/search
{ "query": "退款要多长时间", "top_k": 3 }
```

```json
{
  "code": 0,
  "data": {
    "query": "退款要多长时间",
    "total": 3,
    "hits": [
      { "chunk_id": 6, "document_id": 2, "file_name": "售后服务政策.md",
        "content": "退款时效\n用户提交退款申请后…", "rrf_score": 0.03279 }
    ]
  }
}
```

### 认证流程

```
登录 → 拿到 access(30min) + refresh(7d)
       ↓
用 access 调业务接口
       ↓
access 过期 → 用 refresh 调 /refresh
       ↓ 旧 refresh 立即吊销，签发新双 token（轮换）
登出 → refresh 加入 Redis 黑名单（TTL = 剩余寿命）
```

### 限流

`/api/v1/auth/login` 和 `/api/v1/auth/register` 默认 **5 次/60 秒**，超限返回 `429 {"code":429,"message":"请求过于频繁,请稍后再试"}`。Redis 未配置时 **fail-open**（放行 + warning）。

可在 `.env` 调整：
```
RATE_LIMIT_MAX_REQUESTS=5
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_ROUTES=/api/v1/auth/login,/api/v1/auth/register
```

---

## 📂 项目结构

```
AI-Customer-Service-Platform/
├── app/
│   ├── main.py                 # 应用入口 + lifespan + 中间件
│   ├── api/
│   │   ├── router.py           # 总路由聚合
│   │   └── dependencies.py     # 依赖注入（get_db_session / get_redis / get_current_user）
│   ├── modules/                # 业务模块（模块化单体）
│   │   ├── auth/               # 🔐 用户认证（register/login/refresh/logout/me）
│   │   ├── user/               # 用户管理
│   │   ├── chat/               # 💬 会话 + AI 聊天（SSE 流式）
│   │   ├── knowledge/          # 📚 知识库 + 文档上传 + 检索预览
│   │   └── ticket/             # 工单
│   ├── ai/                     # 🤖 AI 能力层（独立于业务模块）
│   │   ├── router/             # AI Router（意图识别）
│   │   ├── agent/              # Agent + Tool（Phase 15）
│   │   ├── rag/                # ✅ 检索增强生成
│   │   │   ├── config.py       #   模型名/维度/切块/检索参数（写死的常量）
│   │   │   ├── parser.py       #   PDF/DOCX/MD/TXT 文本抽取
│   │   │   ├── chunker.py      #   标题软边界 + 重叠切块
│   │   │   ├── vector_store.py #   VectorStore 抽象 + pgvector 实现
│   │   │   └── retriever.py    #   向量 + 关键词混合检索（RRF 融合）
│   │   ├── memory/             # 对话记忆
│   │   ├── prompt/             # Prompt 模板（system.py，含 RAG 提示词）
│   │   ├── llm/                # LLM 客户端（预留）
│   │   └── tools/              # Tool 定义
│   ├── infrastructure/         # 外部技术实现
│   │   ├── database/           # PostgreSQL（async engine + session）
│   │   ├── redis/              # Redis（client + ratelimit + cache）
│   │   ├── llm/                # LLM API 封装（init/close/chat_stream）
│   │   ├── embedding/          # ✅ 本地 embedding（fastembed ONNX 进程内推理）
│   │   ├── milvus/             # 向量库（已改用 pgvector，此目录保留占位）
│   │   ├── mq/                 # 消息队列（Phase 17 已按精简路线跳过）
│   │   └── storage/            # 对象存储
│   ├── common/                 # 通用层
│   │   ├── exceptions/         # 统一异常 + 全局 handler
│   │   ├── response/           # ResponseBase[T] 统一响应格式
│   │   ├── middleware/         # RequestID + RateLimit
│   │   ├── security/           # password / jwt / token_blacklist
│   │   ├── logging/            # 日志配置
│   │   ├── repository/         # BaseRepository[T]
│   │   └── utils/
│   ├── models/                 # SQLAlchemy ORM 模型
│   ├── config/                 # settings + logging
│   ├── schemas/                # 全局 Pydantic schemas
│   └── tasks/                  # ✅ 文档索引后台任务（解析→切块→向量化）
├── static/
│   └── index.html              # ✅ 最小演示页（原生 HTML + fetch 流式）
├── docker/
│   └── pgvector/Dockerfile     # ✅ 本地构建 pgvector 镜像（不依赖 Docker Hub）
├── alembic/                    # 数据库迁移
├── docker-compose.yml          # PostgreSQL(pgvector) + Redis
├── pyproject.toml              # 依赖声明（uv）
├── .env.example                # 环境变量模板
└── design_docs/                # 完整设计文档
```

---

## 🗺️ 开发进度

完整 22 阶段，设计文档见 [design_docs/](./design_docs/)。

| # | 阶段 | V 版本 | 状态 |
|---|---|---|---|
| 1 | PRD 产品需求 | — | ✅ |
| 2 | 领域模型 | — | ✅ |
| 3 | 核心业务流程 | — | ✅ |
| 4 | 数据库 ER 模型 | — | ✅ |
| 5 | 数据库表结构 | — | ✅ |
| 6 | 系统架构设计 | — | ✅ |
| 7 | API 接口设计 | — | ✅ |
| 8 | 项目工程结构 | — | ✅ |
| 9 | V1 基础后端 | 🏗️ | ✅ |
| 10 | V2 数据库 | 🗄️ | ✅ |
| 11 | V3 认证与权限 | 🔐 | ✅ |
| 12 | V4 Redis + 异步 | ⚡ | ✅ |
| 13 | V5 LLM + AI Chat | 🤖 | ✅ |
| 14 | V6 RAG 知识库 | 📚 | ✅ |
| 15 | V7 Agent + Tool | 🛠️ | ⏳ 下一阶段 |
| 16 | V8 AI + 人工协同 | 👥 | ⏳ |
| 17 | V9 消息队列 / Worker | 📨 | ⏭️ 已跳过 |
| 18 | V10 测试与工程化 | 📝 | ⏳ |
| 19 | V11 Docker + Nginx + CI/CD | 🐳 | ⏳ |
| 20 | V12 日志 / 监控 / Tracing | 📊 | ⏳ |
| 21 | V13 AI Evaluation | 🧪 | ⏳ |
| 22 | V14 生产级优化 | 🚀 | ⏳ |

---

## 📖 设计文档

所有设计阶段都有对应的文档，放在 [design_docs/](./design_docs)：

| 文件 | 内容 |
|---|---|
| [0-完整开发路线图](./design_docs/0-企业AI客服平台-完整开发路线图-V1.0.md) | 22 阶段总施工图 |
| [1-PRD](./design_docs/1-PRD-V1.0-企业AI客服平台.md) | 产品需求文档 |
| [2-领域模型](./design_docs/2-企业AI客服平台-领域模型设计-V1.0.md) | 核心领域对象 |
| [3-核心业务流程](./design_docs/3-企业AI客服平台-核心业务流程设计-V1.0.md) | 5 条核心链路逐步拆解 |
| [4-ER 模型](./design_docs/4-企业AI客服平台-数据库ER模型设计-V1.0.md) | 数据库实体关系 |
| [5-表结构](./design_docs/5-企业AI客服平台-数据库表结构设计-V1.0.md) | 完整 DDL |
| [6-系统架构](./design_docs/6-企业AI客服平台-系统架构设计-V1.0.md) | 架构决策 + 分层 |
| [7-API 设计](./design_docs/7-企业AI客服平台-API接口设计-V1.0.md) | 接口规范 |
| [8-工程结构](./design_docs/8-企业AI客服平台-项目工程结构设计-V1.0.md) | 目录 + 文件职责 |

---

## 📝 License

MIT
