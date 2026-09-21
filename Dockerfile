# 企业 AI 客服平台 —— 生产镜像（Phase 19）
#
# 两阶段构建：
#   builder 装依赖到独立 venv，runtime 只带 venv + 代码，不带编译工具链。
# 以非 root 运行，并内置 healthcheck（探 liveness，不查依赖）。
#
# ⚠️ 两个容易踩的点（都已在下面处理）：
#   1. **onnxruntime 依赖 libgomp1**。python:3.x-slim 默认没有它，
#      不装会在加载 embedding 模型时报 "libgomp.so.1: cannot open shared object file"。
#   2. **必须拷贝 static/**。演示页由 FastAPI 挂 /static 提供，
#      漏掉它容器里访问 / 会 302 到 404。
#
# 关于本机构建：本机 Docker Hub 不可达（registry-1.docker.io 超时），
# 基础镜像与 uv 镜像拉不下来，因此**本机无法完成构建**。
# 该 Dockerfile 由 CI（GitHub Actions 的 build job）实际构建验证 ——
# GitHub 的 runner 能正常访问 Docker Hub 与 ghcr.io。
ARG PYTHON_VERSION=3.12
# 与开发机 `uv --version` 保持一致；用浮动 tag 会让构建不可复现
ARG UV_VERSION=0.12.11


# ── 构建阶段：装依赖 ──────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:${UV_VERSION} /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# 先只拷依赖清单，依赖没变时可复用这层缓存
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

# 再拷源码并把本项目装进 venv
COPY app/ ./app/
RUN uv sync --frozen --no-dev


# ── 运行阶段 ──────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS runtime

# libgomp1：onnxruntime（fastembed 的推理后端）必需
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 非 root 运行；uid 固定便于挂载卷时对齐权限
RUN useradd --create-home --uid 10001 appuser

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --chown=appuser:appuser app/ ./app/
# 演示页：漏了这一行，容器里访问 / 会跳到一个不存在的页面
COPY --chown=appuser:appuser static/ ./static/
# 迁移脚本：容器内可用 `alembic upgrade head` 做发布
COPY --chown=appuser:appuser alembic/ ./alembic/
COPY --chown=appuser:appuser alembic.ini ./

# 上传目录须可写；提前建好并交给 appuser，否则非 root 首次上传会 Permission denied
RUN mkdir -p data/uploads && chown -R appuser:appuser data

USER appuser

EXPOSE 8000

# 探 liveness（/health 不查依赖）。readiness 用 /api/v1/health，由编排层配置。
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request as u, sys; sys.exit(0 if u.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
