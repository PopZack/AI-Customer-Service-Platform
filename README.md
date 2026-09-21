# 🤖 企业 AI 客服平台

> AI 自动解决客户问题，解决不了无缝交给人工。一套 **模块化单体** 架构，22 个阶段从骨架到生产。

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-green)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-red)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED)](https://www.docker.com/)
[![CI](https://github.com/PopZack/AI-Customer-Service-Platform/actions/workflows/ci.yml/badge.svg)](https://github.com/PopZack/AI-Customer-Service-Platform/actions/workflows/ci.yml)

---

## ✨ 功能亮点

### 已实现（Phase 9-22，全部完成）

| 能力 | 说明 | 阶段 |
|---|---|---|
| 🏗️ 工程骨架 | FastAPI + Pydantic 分层架构，模块化单体 | Phase 9 |
| 🗄️ 数据库集成 | SQLAlchemy async + Alembic 迁移 + Repository 模式 | Phase 10 |
| 🔐 用户认证 | 注册 / 登录 / JWT 双 token（access + refresh）/ 刷新轮换 / 登出黑名单 | Phase 11 |
| ⚡ Redis 异步 | 限流中间件 / 健康检查 / 缓存工具类（铺路） | Phase 12 |
| 🤖 LLM + AI Chat | OpenAI 兼容客户端 / SSE 流式输出 / 多轮上下文 / 会话 CRUD | Phase 13 |
| 📚 RAG 知识库 | 文档上传解析切块 / 本地 embedding / pgvector 入库 / 混合检索 / 带引用回答 | Phase 14 |
| 🛠️ Agent + Tool | 5 个工具的 function calling：检索 / 查工单 / 建单 / 转人工 / 查用户资料 | Phase 15 |
| 👥 AI + 人工协同 | 会话状态机（AI→等待人工→人工接管→结束）/ 显式+隐式转人工 / 工单闭环 | Phase 16 |
| 📝 测试与工程化 | 67 个测试（单元 + 集成，真实 PG/Redis/embedding）/ 生产 Dockerfile / GitHub Actions | Phase 18 |
| 🐳 Docker + CI/CD | 全栈 compose 编排 + Nginx 反代（SSE 调优）/ 镜像自动发布 ghcr.io | Phase 19 |
| 📊 监控（精简版） | 零依赖进程内计数器 + Prometheus 格式 `/metrics`；检索缓存（带数据版本失效）；LLM fallback | Phase 20 |
| 🧪 RAG 评测 | 24 条评测集，Recall@1 95% / Recall@3 100% / faithfulness 96%（LLM 裁判） | Phase 21 |

### 规划中

核心路线图（Phase 9-22）已全部完成（Phase 17 消息队列按精简决策跳过）。
后续可扩展方向：多知识库权限隔离、OCR 支持（扫描版 PDF）、对象存储、完整监控接入。

> 收尾采用**精简路线**：**Phase 17 消息队列跳过**（文档解析与 embedding 改用 FastAPI BackgroundTasks，本项目无高并发场景），Phase 18-22 按精简版收尾。

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

### Agent 的三个关键取舍

**1. 流式做工具轮，不用非流式。**

非流式要等整轮生成完才返回，多轮工具调用会让用户干等几十秒。流式下模型先说的思考文字可以立刻推给用户，工具参数则**按 index 跨 chunk 累积**到完整再执行 —— OpenAI 兼容接口会把一次工具调用切成多个 chunk 下发，id 和函数名往往只在第一个 chunk 出现，`arguments` 是被切碎的 JSON 字符串。这是本项目最容易写错的一处，因此专门写了确定性单测覆盖（`tests/unit/test_agent_loop.py`）。

**2. RAG 预注入与工具检索并存，不是二选一。**

常见问答题由 M1 的「检索结果预先拼进 system prompt」直接兜住，不必多花一次工具往返；`search_knowledge` 工具则留给需要换措辞再检索、或多跳追问的场景。两者叠加的代价是偶尔重复检索一次，换来的是常见路径的低延迟与高可靠性。

**3. 轮数上限要「强制收尾」，不能直接报错。**

`MAX_STEPS=5` 防止模型在两个工具之间打转烧 token。但达到上限时不是抛异常，而是**带 `tools=None` 再调一次**，强制模型给出文本答案 —— 否则用户会看到一句"我还在调工具"，体验比慢更差。

### 转人工的两条路径

```
显式：用户点「转人工」按钮  ┐
                          ├→ request_handoff() → 会话置「等待人工」+ 落 system 消息 + 保证有工单
隐式：连续 3 次检索为空    ┘
```

两条路径**共用同一个函数**，否则「转人工」会出现两种不同的落库形态，排查时无法统一。

隐式计数用 Redis（`chat:empty_retrieval:{id}`，带 1 小时 TTL）而非数据库：它是短期会话状态、不是审计数据，天然需要过期；命中非空检索时立即清零。Redis 不可用时该能力静默降级，不阻断对话。

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
| 测试 | pytest + pytest-asyncio（真实 PG / Redis，仅 mock LLM） | 67 个用例 |
| 代码规范 | ruff（check 已全绿） | 0.16+ |
| CI | GitHub Actions（lint / test / build / release 四 job） | — |
| 部署 | Docker Compose（开发态）+ prod 叠加文件（全栈） | Phase 19 |

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
#    豆包:       https://ark.cn-beijing.volces.com/api/v3, model=方舟的模型ID或接入点ep-xxx
#    ⚠️ 方舟 Agent Plan 是独立产品线,端点不同:
#               https://ark.cn-beijing.volces.com/api/plan/v3, model=ark-code-latest
#               (Agent Plan 的 key 是 ark- 开头,用普通 /api/v3 端点会 401)
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
- **演示页**：<http://localhost:8000/static/index.html>（知识库 / 带引用对话 / 检索预览 / **工单客服台**）
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

# 静态检查(Phase 18 已收敛至全绿)
uv run ruff check .
uv run ruff format .          # 格式化(ruff 的 formatter 兼容 black,已不再单独引 black)

# 跑测试
uv run pytest                 # 全量
uv run pytest tests/unit      # 只跑单元测试(不需要数据库)
uv run pytest -k 转人工        # 按名字筛

# 重建 pgvector 镜像(仅当 docker compose 拉不到镜像时需要)
docker build -t pgvector/pgvector:pg16 docker/pgvector/
```

### 测试

```bash
uv run pytest
```

**67 个测试**，分两层：

| 层 | 位置 | 依赖 | 说明 |
|---|---|---|---|
| 单元 | `tests/unit/` | 无 | Agent 循环（假 LLM 驱动脚本化的工具调用增量）、配置层密钥守卫 |
| 集成 | `tests/integration/` | PostgreSQL + Redis + embedding 模型 | 认证链路、RAG 全链路、聊天 SSE、转人工与工单 |

集成测试的几个刻意设计：

- **真实 PostgreSQL / Redis / embedding，只 mock LLM。** embedding 是本地纯函数，
  真跑才能验出"切块 → 向量化 → 检索"是否真的可用；mock 掉它会让 RAG 测试退化成
  "永远命中"的假测试。LLM 是唯一必须 mock 的（要联网、要花钱、结果不确定）。
- **工具是真实执行的。** 聊天测试里模型输出由假客户端顶替，但它发出的
  `search_knowledge` 调用会真的去查数据库里的向量 —— 整条
  "模型调工具 → 工具真检索 → 结果回填 → 模型作答"都在覆盖内。
- **测试库是独立数据库**（`<开发库名>_test`，每次会话重建），不是 schema。
  检索层有手写 SQL，用 schema 会踩 search_path 解析的坑。
- 每个用例结束 `TRUNCATE` 所有表**并清理 Redis 里 `chat:*` 的计数键** ——
  后者是隐式转人工的计数器，而 `RESTART IDENTITY` 会让下一条用例复用会话 ID，
  不清就会"莫名其妙提前转人工"。这个坑真踩过。

> 单元测试不依赖任何外部服务，可以直接 `uv run pytest tests/unit` 秒级跑完。

### 用 Docker 跑

```bash
docker build -t ai-customer-service .
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://ai_cs:ai_cs_pwd@host.docker.internal:5432/ai_customer_service \
  -e REDIS_URL=redis://host.docker.internal:6379/0 \
  -e JWT_SECRET=<至少 32 字符> \
  ai-customer-service
```

镜像以**非 root** 运行、内置 healthcheck（探 liveness）。两个容易漏的点已在
Dockerfile 里处理并注明：`static/` 必须拷进去（否则容器里演示页 404）、
以及 onnxruntime 依赖 `libgomp1`（slim 基础镜像默认没有）。

> ⚠️ 本机 Docker Hub 不可达，**该镜像无法在本地构建验证**，
> 由 CI 实际构建（GitHub runner 能正常访问 Docker Hub 与 ghcr.io）。

### 生产部署（Phase 19）

CI 在每次 push 到 `main` 且 lint/test/build 全过后，自动把镜像发布到
`ghcr.io/popzack/ai-customer-service-platform`（`latest` + git sha 两个标签）。

服务器上一份 `.env` + 两条命令即可起全栈：

```bash
# 1. 准备 .env（参考 .env.example；注意 DATABASE_URL 会被 compose 覆盖为容器网络地址）
#    ⚠️ 生产必须设置强 JWT_SECRET（≥32 字符），APP_ENV=prod 时用默认值会拒绝启动

# 2. 起全栈（postgres + redis + app + nginx）
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 3. 首次部署/版本升级：在应用容器里执行迁移
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm app alembic upgrade head
```

架构与分工：

```
用户 → Nginx :80 → app :8000 → postgres(pgvector) / redis
                        └─ embedding 本地推理，无外部依赖
```

- **`docker-compose.yml`（开发态）**：只有 postgres + redis，`uv run uvicorn` 直跑。
- **`docker-compose.prod.yml`（叠加文件）**：追加 app + nginx。`depends_on` 带
  `condition: service_healthy`，库没就绪应用不启动；上传文件放 `uploads` 卷，容器重建不丢。
- **迁移与容器启停解耦**：不在容器启动时自动跑迁移 —— 迁移是显式的一次性动作，
  自动化会在多副本时重复执行，也把"改 schema"藏进了部署过程。
- **Nginx 对 SSE 的处理**：`/api/v1/chat` 单独一个 location，`proxy_buffering off`
  + 300s 读超时。不关缓冲的话，逐字输出会被攒成大块再发，用户看到"卡半天突然全出来"。
- **回滚**：`image:` 改成具体的 sha 标签再 `up -d` 即可（这就是为什么除了 latest 还推 sha 标签）。

> nginx 镜像与 ghcr 拉取本机均不可达，`docker-compose.prod.yml` 的完整性由
> `docker compose ... config` 静态校验，端到端拉起由服务器侧执行。

> ⚠️ **第 16 阶段的权限取舍**：工单的指派/回复采用**基于数据归属的最小门槛**
> （认领即接管、已指派者才能回复），**未启用角色权限校验**。
> 设计文档定义了 `ticket:view` / `ticket:edit` 权限码，但角色与权限数据尚未播种，
> 此时强校验会让所有人 403。等权限体系落地后再收紧。
>
> ✅ **Phase 18 已解决**：`uv run ruff check .` 从 57 条存量错误收敛到**全绿**；
> schemas 已全部迁到 Pydantic V2 的 `model_config = ConfigDict(...)`（V1 的
> `class Config` 在 V3 会失效）；全项目路由的依赖注入统一为
> `Annotated[AsyncSession, Depends(...)]`，消掉了 FastAPI 写法触发的 `B008`。
>
> ⚠️ **仍未做**：`ruff format` 尚未作为检查项接入 CI（存量文件格式未统一），
> 只跑 `ruff check`。

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

SSE 事件流（第 15/16 阶段扩展了工具与转人工事件）：
```
data: {"type":"start"}
data: {"type":"content","content":"退款"}
data: {"type":"content","content":"通常"}
data: {"type":"tool_start","tool":"search_knowledge","content":"正在检索知识库…"}
data: {"type":"tool_end","tool":"search_knowledge"}
data: {"type":"handoff","status":2,"ticket_id":12,"content":"已为您转接人工客服"}
data: {"type":"notice","content":"（已达到工具调用轮数上限，直接作答）"}
data: {"type":"error","message":"LLM 超时"}    ← 出错
data: {"type":"done","status":1}              ← 附带会话最新状态
```

回答会基于知识库检索结果，并在正文里标注引用编号（如 `退款一般 3 到 5 个工作日到账[1]`）。

### RAG 评测（Phase 21）

`evals/` 内置 24 条评测集（20 知识题 + 4 拒答题）与评测脚本，语料索引、检索、生成全部走生产同款代码：

```bash
uv run python evals/run_eval.py          # 完整评测(需要 LLM key)
uv run python evals/run_eval.py --skip-faithfulness   # 只测检索
```

首轮结果（模型 ark-code-latest / bge-small-zh-v1.5）：

| 指标 | 结果 | 说明 |
|---|---|---|
| Recall@1 | **95%**（19/20） | 唯一漏检是两节语义相近（退款时效 vs 退换货流程）被挤到第 2 位 |
| Recall@3 | **100%** | |
| 拒答正确率 | 4/4 | 知识库外的问题不编造，明确说不知道并引导 |
| faithfulness | **96%**（23/24） | LLM 裁判；唯一"编造"是模型在资料外补了一句常识建议（检查垃圾邮件文件夹）—— 提示词收紧的方向 |

> ⚠️ 两点局限：① faithfulness 用同一个 LLM 当裁判有自我偏好，但它能稳定抓住"编造资料外信息"这类最危险的失败；② Agent Plan 模型非流式调用**偶发空输出**（疑似推理预算被吞），评测脚本已做"空输出 → 加大预算重试"，生产流式路径未观察到此问题。

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

### Tickets — 工单与人工协同（Phase 16）

| 方法 | 端点 | 说明 |
|---|---|---|
| GET | `/api/v1/tickets` | 工单列表（`?status=0` 待处理队列 / `?assigned_user=0` 未认领） |
| GET | `/api/v1/tickets/{id}` | 工单详情（含往来记录） |
| POST | `/api/v1/tickets/{id}/assign` | 指派；不传 `agent_id` 表示**认领给自己** |
| POST | `/api/v1/tickets/{id}/reply` | 客服回复 |
| POST | `/api/v1/tickets/{id}/close` | 关单（同时结束会话） |
| POST | `/api/v1/conversations/{id}/handoff` | **显式转人工**（用户点按钮） |
| GET | `/api/v1/conversations/{id}/handoff-signal` | 查看转人工判定信号（连续空检索次数 / 阈值） |

**人工回复是双写的**：既写 `ticket_message`（客服侧审计留痕），也写 `message`（用户在聊天窗口能看到）。
只写工单表的话，客服回了话、用户在自己的会话里却看不到 —— 这是"AI + 人工协同"最影响体感的一处。

会话状态机：

```
1 AI 服务中 ──转人工──→ 2 等待人工 ──客服认领──→ 3 人工接管 ──关单──→ 0 已结束
```

处于 2 / 3 的会话，AI 不再作答（用户消息仍入库，等客服处理）。

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
│   │   └── ticket/             # ✅ 工单：列表/指派/人工回复/关单
│   ├── ai/                     # 🤖 AI 能力层（独立于业务模块）
│   │   ├── router/             # AI Router（意图识别）
│   │   ├── agent/              # ✅ Agent 循环 + 转人工判定（handoff.py）
│   │   ├── rag/                # ✅ 检索增强生成
│   │   │   ├── config.py       #   模型名/维度/切块/检索参数（写死的常量）
│   │   │   ├── parser.py       #   PDF/DOCX/MD/TXT 文本抽取
│   │   │   ├── chunker.py      #   标题软边界 + 重叠切块
│   │   │   ├── vector_store.py #   VectorStore 抽象 + pgvector 实现
│   │   │   └── retriever.py    #   向量 + 关键词混合检索（RRF 融合）
│   │   ├── memory/             # 对话记忆
│   │   ├── prompt/             # Prompt 模板（system.py，含 RAG 提示词）
│   │   ├── llm/                # LLM 客户端（预留）
│   │   └── tools/              # ✅ 工具定义（definitions）+ 执行器（executor）
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
├── alembic/                    # 数据库迁移（含 pgvector 扩展与索引）
├── tests/                      # ✅ 测试
│   ├── conftest.py             #   测试环境准备（切测试库、放开限流、关 SQL 回显）
│   ├── unit/                   #   单元测试：Agent 循环、配置守卫（不需要外部服务）
│   └── integration/            #   集成测试：真实 PG / Redis / embedding
├── evals/                      # ✅ RAG 评测：语料 + 24 条用例 + 脚本（Recall/faithfulness）
├── .github/workflows/ci.yml    # ✅ CI：lint / test / build / release
├── Dockerfile                  # ✅ 生产镜像（多阶段、非 root、healthcheck）
├── .dockerignore
├── docker/
│   ├── pgvector/Dockerfile     # ✅ 本地构建 pgvector 镜像（不依赖 Docker Hub）
│   └── nginx/nginx.conf        # ✅ 反代配置（SSE 关缓冲 / 上传体积对齐）
├── docker-compose.yml          # 开发态：PostgreSQL(pgvector) + Redis
├── docker-compose.prod.yml     # ✅ 生产态：追加 app + nginx（全栈）
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
| 15 | V7 Agent + Tool | 🛠️ | ✅ |
| 16 | V8 AI + 人工协同 | 👥 | ✅ |
| 17 | V9 消息队列 / Worker | 📨 | ⏭️ 已跳过 |
| 18 | V10 测试与工程化 | 📝 | ✅ |
| 19 | V11 Docker + Nginx + CI/CD | 🐳 | ✅ |
| 20 | V12 日志 / 监控 / Tracing | 📊 | ✅ 精简为 /metrics + 结构化日志 |
| 21 | V13 AI Evaluation | 🧪 | ✅ 24 条评测集 |
| 22 | V14 生产级优化 | 🚀 | ✅ 精简完成 |

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
