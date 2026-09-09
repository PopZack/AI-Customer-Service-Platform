"""AI 配置模型: model_config / prompt_template。"""
from sqlalchemy import Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, BigIntPKMixin


# ── 模型配置 ────────────────────────────────────────────
class ModelConfig(Base, BigIntPKMixin):
    """AI 模型配置。"""

    __tablename__ = "model_config"

    model_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="模型名称")
    provider: Mapped[str] = mapped_column(String(50), nullable=False, comment="供应商:openai/deepseek/qwen/anthropic")
    api_url: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="API 地址")
    temperature: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True, comment="温度参数")
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最大 token 数")


# ── 提示词模板 ──────────────────────────────────────────
class PromptTemplate(Base, BigIntPKMixin):
    """提示词模板。"""

    __tablename__ = "prompt_template"

    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="模板名称")
    scene: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="场景:customer_service/sales/complaint")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="模板内容")
    version: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="版本号")
