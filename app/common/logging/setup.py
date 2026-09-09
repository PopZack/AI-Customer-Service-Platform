"""日志初始化入口:转发到 config.logging,统一对外暴露。"""
from app.config.logging import setup_logging

__all__ = ["setup_logging"]
