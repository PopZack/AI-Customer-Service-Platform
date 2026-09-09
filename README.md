# 🤖 企业 AI 客服平台

> AI 自动解决客户问题，解决不了无缝交给人工。一套 **模块化单体** 架构，22 个阶段从骨架到生产。

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-green)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-red)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED)](https://www.docker.com/)

---

## ✨ 功能亮点

### 已实现（Phase 9-12）

| 能力 | 说明 | 阶段 |
|---|---|---|
| 🏗️ 工程骨架 | FastAPI + Pydantic 分层架构，模块化单体 | Phase 9 |
| 🗄️ 数据库集成 | SQLAlchemy async + Alembic 迁移 + Repository 模式 | Phase 10 |
| 🔐 用户认证 | 注册 / 登录 / JWT 双 token（access + refresh）/ 刷新轮换 / 登出黑名单 | Phase 11 |
| ⚡ Redis 异步 | 限流中间件 / 健康检查 / 缓存工具类（铺路） | Phase 12 |

### 规划中（Phase 13-22）

LLM 对话 → RAG 知识库 → Agent + Tool → 人工协同 → 消息队列 → 测试 → Docker + CI/CD → 监控 → AI 评估 → 生产优化

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

外加 **Infrastructure** 层隔离外部技术细节（数据库/Redis/Milvus/MQ），业务代码不直接碰 `redis.set(...)`、`pg.query(...)`。

### AI 能力独立成层

AI 相关（Router → Agent → RAG → LLM）不混进业务模块，单独在 `app/ai/`，未来可独立部署成 AI 网关。

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
| 向量库 | Milvus | Phase 14 |
| 部署 | Docker Compose | Phase 19 |

---

## 🚀 快速开始

### 前置

- Python 3.11+ + [uv](https://docs.astral.sh/uv/)
- Docker Desktop（跑 PostgreSQL + Redis）

### 一步到位

```bash
# 1. 启动 PostgreSQL + Redis（Docker）
docker compose up -d

# 2. 安装依赖 + 配环境
uv sync
cp .env.example .env

# 3. 数据库迁移
uv run alembic upgrade head

# 4. 启动
uv run uvicorn app.main:app --reload
```

访问：
- 健康检查（liveness）：<http://localhost:8000/health>
- 健康检查（readiness，含 DB + Redis）：<http://localhost:8000/api/v1/health>
- API 文档（Swagger）：<http://localhost:8000/docs>
- ReDoc：<http://localhost:8000/redoc>

### 常用命令

```bash
# 数据库迁移
uv run alembic revision --autogenerate -m "描述"
uv run alembic upgrade head
uv run alembic downgrade -1

# 重新生成依赖锁
uv lock

# 格式检查
uv run ruff check .
uv run black --check .
```

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
│   │   ├── chat/               # AI 对话
│   │   ├── knowledge/          # 知识库
│   │   └── ticket/             # 工单
│   ├── ai/                     # 🤖 AI 能力层（独立于业务模块）
│   │   ├── router/             # AI Router（意图识别）
│   │   ├── agent/              # Agent + Tool
│   │   ├── rag/                # 检索增强生成
│   │   ├── memory/             # 对话记忆
│   │   ├── prompt/             # Prompt 模板
│   │   ├── llm/                # LLM 客户端
│   │   └── tools/              # Tool 定义
│   ├── infrastructure/         # 外部技术实现
│   │   ├── database/           # PostgreSQL（async engine + session）
│   │   ├── redis/              # Redis（client + ratelimit + cache）
│   │   ├── milvus/             # 向量库（Phase 14）
│   │   ├── mq/                 # 消息队列（Phase 17）
│   │   ├── storage/            # 对象存储
│   │   └── llm/                # LLM API 封装
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
│   └── tasks/                  # Background tasks
├── alembic/                    # 数据库迁移
├── docker-compose.yml          # PostgreSQL + Redis
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
| 13 | V5 LLM + AI Chat | 🤖 | ⏳ 下一阶段 |
| 14 | V6 RAG 知识库 | 📚 | ⏳ |
| 15 | V7 Agent + Tool | 🛠️ | ⏳ |
| 16 | V8 AI + 人工协同 | 👥 | ⏳ |
| 17 | V9 消息队列 / Worker | 📨 | ⏳ |
| 18 | V10 测试与工程化 | ✅ | ⏳ |
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
| [1-PRD](./design_docs/1-企业AI客服平台-PRD-V1.0.md) | 产品需求文档 |
| [2-领域模型](./design_docs/2-企业AI客服平台-领域模型设计-V1.0.md) | 核心领域对象 |
| [4-ER 模型](./design_docs/4-企业AI客服平台-数据库ER模型-V1.0.md) | 数据库实体关系 |
| [5-表结构](./design_docs/5-企业AI客服平台-数据库表结构设计-V1.0.md) | 完整 DDL |
| [6-系统架构](./design_docs/6-企业AI客服平台-系统架构设计-V1.0.md) | 架构决策 + 分层 |
| [7-API 设计](./design_docs/7-企业AI客服平台-API接口设计-V1.0.md) | 接口规范 |
| [8-工程结构](./design_docs/8-企业AI客服平台-项目工程结构设计-V1.0.md) | 目录 + 文件职责 |

---

## 📝 License

MIT
