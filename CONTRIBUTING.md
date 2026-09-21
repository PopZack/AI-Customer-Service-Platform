# 贡献指南

感谢关注本项目！这是一个 **学习型项目**（22 阶段路线从骨架到生产的全程留痕），欢迎 issue 交流与 PR。

## 本地跑起来

```bash
# 1. 依赖与基础设施（Docker 提供 PostgreSQL(pgvector) + Redis）
uv sync --extra dev
docker compose up -d
uv run alembic upgrade head

# 2. 配置
cp .env.example .env          # LLM key 可不配，聊天接口会返回 503（其余功能都可用）

# 3. 启动 + 验证
uv run uvicorn app.main:app --reload
uv run pytest                 # 77 个测试；单元测试不需要任何外部服务
uv run ruff check .           # 必须全绿
```

## 提 PR 前的自查清单

- [ ] `uv run ruff check .` 全绿（CI 会挂）
- [ ] 新增/修改的行为有对应测试；**改动被任何测试断言引用的产物（含页面文案）后，先跑全量 `uv run pytest`**
- [ ] 全量测试本地通过（CI 的 test job 与本地同构，挂了必是代码问题）

## 项目约定（不遵守的 PR 大概率被拒）

- **只 mock LLM**。embedding 与工具必须真跑 —— mock 掉它们会让 RAG 测试退化成"永远命中"的假测试。
- 分层职责：Router 薄 / Service 唯一业务入口 / Repository 唯一数据访问通道 / Infrastructure 隔离外部技术。
- 文档处理入队必须走 `enqueue_document()`，不允许绕过（这是将来换队列的唯一接缝）。
- 换 embedding 模型 = 全量向量重建，模型名与维度写死在 `app/ai/rag/config.py`，不要做成配置项。
- 中文文案、简洁注释，注释里写"为什么"而不是"是什么"。

## 提交规范

`feat|fix|docs|test|refactor|chore|ci|style(作用域): 描述`，正文写清动机与取舍。
