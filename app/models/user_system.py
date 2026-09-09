"""用户权限系统模型: user / role / permission / user_role / role_permission。"""
from sqlalchemy import BigInteger, Column, ForeignKey, SmallInteger, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, BigIntPKMixin, TimestampMixin

# ── 关联表 ──────────────────────────────────────────────
user_role = Table(
    "user_role",
    Base.metadata,
    Column("user_id", BigInteger, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", BigInteger, ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
    comment="用户-角色关联表",
)

role_permission = Table(
    "role_permission",
    Base.metadata,
    Column("role_id", BigInteger, ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        BigInteger,
        ForeignKey("permission.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    comment="角色-权限关联表",
)


# ── 用户表 ──────────────────────────────────────────────
class User(Base, BigIntPKMixin, TimestampMixin):
    """用户表。"""

    __tablename__ = "user"

    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="登录账号")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="加密密码")
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="昵称")
    email: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="邮箱")
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="手机号")
    avatar: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="头像URL")
    status: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False, comment="状态:1启用 0禁用")
    tenant_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tenant.id", ondelete="SET NULL"), nullable=True, comment="所属租户"
    )

    # 关联
    roles: Mapped[list["Role"]] = relationship(secondary=user_role, back_populates="users")


# ── 角色表 ──────────────────────────────────────────────
class Role(Base, BigIntPKMixin):
    """角色表。"""

    __tablename__ = "role"

    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="角色名称")
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="角色编码")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")

    # 关联
    users: Mapped[list["User"]] = relationship(secondary=user_role, back_populates="roles")
    permissions: Mapped[list["Permission"]] = relationship(
        secondary=role_permission, back_populates="roles"
    )


# ── 权限表 ──────────────────────────────────────────────
class Permission(Base, BigIntPKMixin):
    """权限表。"""

    __tablename__ = "permission"

    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="权限名称")
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, comment="权限编码")
    api_path: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="API路径")
    method: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="HTTP方法")

    # 关联
    roles: Mapped[list["Role"]] = relationship(secondary=role_permission, back_populates="permissions")
