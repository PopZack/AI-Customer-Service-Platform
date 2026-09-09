"""Alembic 迁移环境配置。

- 从项目 settings 读取 DATABASE_URL(而非 alembic.ini 硬编码)
- 将 async 驱动 URL 转为 sync 驱动(alembic 只能同步运行)
  - postgresql+asyncpg:// -> postgresql+psycopg2://
  - sqlite+aiosqlite://    -> sqlite:///
- target_metadata 指向 app.models 的 Base.metadata,支持 autogenerate
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# 确保项目根目录在 sys.path 中(alembic 从 alembic/ 子目录运行)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infrastructure.database import Base  # noqa: E402
import app.models  # noqa: E402,F401  (导入模型以注册到 Base.metadata)
from app.config.settings import get_settings  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 指向项目所有模型的元数据
target_metadata = Base.metadata


def _sync_url(async_url: str) -> str:
    """将 async 驱动 URL 转为 sync 驱动 URL(alembic 必须同步运行)。"""
    if async_url.startswith("postgresql+asyncpg://"):
        return async_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if async_url.startswith("sqlite+aiosqlite://"):
        return async_url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    return async_url


def get_url() -> str:
    """从项目 settings 获取数据库 URL,转为同步驱动。"""
    settings = get_settings()
    url = settings.DATABASE_URL
    if not url:
        raise RuntimeError(
            "DATABASE_URL 未配置,请在 .env 中设置数据库连接串后再运行 alembic。"
        )
    return _sync_url(url)


def run_migrations_offline() -> None:
    """离线模式: 仅生成 SQL 脚本,不连库。"""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式: 连接数据库执行迁移。"""
    # 用 settings 中的 URL 覆盖 alembic.ini 中的 sqlalchemy.url
    config.set_main_option("sqlalchemy.url", get_url())

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
