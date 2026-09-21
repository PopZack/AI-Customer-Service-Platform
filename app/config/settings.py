"""应用配置:从 .env 读取,集中管理所有配置项。

第 9 阶段仅含基础配置,数据库/Redis/Milvus/LLM 等配置在后续阶段补充。
"""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: JWT 密钥的默认值。生产环境继续用它 = 任何人都能伪造 token。
_DEFAULT_JWT_SECRET = "change_me"
#: HS256 的密钥长度下限。低于 32 字节时 PyJWT 会告警,且抗暴力破解能力不足。
_MIN_JWT_SECRET_LEN = 32


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
    # 开发环境可留默认值;生产环境(APP_ENV=prod)不设会直接启动失败,见下方校验
    JWT_SECRET: str = _DEFAULT_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # 引入 refresh 后标准值(第 11 阶段曾临时 1440/24h)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── 限流(第 12 阶段启用)──
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_ROUTES: str = "/api/v1/auth/login,/api/v1/auth/register"
    RATE_LIMIT_MAX_REQUESTS: int = 5
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # ── LLM(第 13 阶段启用)──
    # OpenAI 兼容接口,支持 DeepSeek / Qwen / Moonshot / 豆包等
    LLM_API_KEY: str | None = None
    LLM_BASE_URL: str | None = None  # 例如 https://api.deepseek.com/v1
    LLM_MODEL: str = "deepseek-chat"
    LLM_MAX_TOKENS: int = 2048
    LLM_TEMPERATURE: float = 0.7
    LLM_TIMEOUT: float = 30.0
    LLM_SYSTEM_PROMPT: str = "你是企业级 AI 客服助手,请专业、礼貌、准确地回答用户问题。"
    LLM_MAX_CONTEXT_MESSAGES: int = 20  # 每次最多带入的历史消息数

    # ── 知识库 / RAG(第 14 阶段启用)──
    # 上传文件落盘目录(本地磁盘;生产可换对象存储,storage_path 字段已预留)
    UPLOAD_DIR: str = "./data/uploads"
    MAX_UPLOAD_MB: int = 20  # 单文件大小上限
    EMBED_BATCH_SIZE: int = 64  # 向量化批大小(单批过大时 ONNX 推理内存会飙升)


    @model_validator(mode="after")
    def _guard_production_secrets(self) -> "Settings":
        """生产环境不允许沿用默认 JWT 密钥。

        为什么放在配置层而不是业务代码里：密钥是全局的，一旦用默认值签发 token，
        任何人都能自己造一个合法 token 冒充管理员 —— 这类问题必须在**启动时**暴露，
        而不是等出事才发现。开发/测试环境(APP_ENV != prod)不受影响。
        """
        if self.APP_ENV == "prod":
            if self.JWT_SECRET == _DEFAULT_JWT_SECRET:
                raise ValueError(
                    "生产环境必须设置 JWT_SECRET,不能使用默认值(否则 token 可被伪造)"
                )
            if len(self.JWT_SECRET) < _MIN_JWT_SECRET_LEN:
                raise ValueError(
                    f"生产环境的 JWT_SECRET 至少 {_MIN_JWT_SECRET_LEN} 个字符"
                    f"(当前 {len(self.JWT_SECRET)})"
                )
        return self

@lru_cache
def get_settings() -> Settings:
    """返回全局 Settings 单例。"""
    return Settings()
