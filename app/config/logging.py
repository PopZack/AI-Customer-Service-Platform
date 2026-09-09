"""日志配置:基于 logging.dictConfig 的集中式配置。"""
import logging.config

from app.config.settings import get_settings


def get_logging_config() -> dict:
    """返回日志配置字典。"""
    settings = get_settings()
    level = "DEBUG" if settings.DEBUG else "INFO"
    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s | "
        "%(filename)s:%(lineno)d | %(message)s"
    )

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": log_format},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": level,
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            # 应用代码日志
            "app": {"level": level, "handlers": ["console"], "propagate": False},
            # 第三方库日志降噪
            "uvicorn": {"level": "INFO", "handlers": ["console"], "propagate": False},
            "fastapi": {"level": "INFO", "handlers": ["console"], "propagate": False},
        },
        # 兜底:未命名的其它日志
        "root": {"level": "WARNING", "handlers": ["console"]},
    }


def setup_logging() -> None:
    """初始化全局日志配置。"""
    logging.config.dictConfig(get_logging_config())
