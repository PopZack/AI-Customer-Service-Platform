# 企业 AI 客服平台 Docker 镜像
# 注:第 19 阶段(Docker + Nginx + CI/CD)完善多阶段构建与生产配置

FROM python:3.12-slim

WORKDIR /app

# 安装 uv(从官方镜像拷贝二进制,无需 pip)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 先拷依赖清单,利用缓存层
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 拷贝应用代码并以可编辑模式安装本项目
COPY app/ ./app/
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
