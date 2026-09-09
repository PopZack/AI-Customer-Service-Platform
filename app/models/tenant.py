"""租户模型: 多租户隔离的顶层实体。"""
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, BigIntPKMixin, TimestampMixin


class Tenant(Base, BigIntPKMixin, TimestampMixin):
    """租户(企业)表。"""

    __tablename__ = "tenant"

    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="企业名称")
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="企业编码")
    contact_name: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="联系人")
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="联系电话")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
