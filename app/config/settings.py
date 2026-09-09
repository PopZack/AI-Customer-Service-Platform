"""应用配置:从 .env 读取,集中管理所有配置项。

第 9 阶段仅含基础配置,数据库/Redis/Milvus/LLM 等配置在后续阶段补充。
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── 应用基础 ──
    APP_NAME: str = "企业 AI 客服平台"
    APP_ENV: str = "dev"  # dev / prod
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # ── 数据库(PostgreSQL,第 10 阶段启用)──
    # 格式:postgresql+asyncpg://user:pass@host:5432/dbname
    DATABASE_URL: str | None = None

    # ── Redis(第 12 阶段启用)──
    # 格式:redis://localhost:6379/0
    REDIS_URL: str | None = None

    # ── JWT(第 11 阶段启用,第 12 阶段调整:access 缩短 + refresh)──
    JWT_SECRET: str = "change_me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # 引入 refresh 后标准值(第 11 阶段曾临时 1440/24h)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── 限流(第 12 阶段启用)──
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_ROUTES: str = "/api/v1/auth/login,/api/v1/auth/register"
    RATE_LIMIT_MAX_REQUESTS: int = 5
    RATE_LIMIT_WINDOW_SECONDS: int = 60


@lru_cache
def get_settings() -> Settings:
    """返回全局 Settings 单例。"""
    return Settings()
