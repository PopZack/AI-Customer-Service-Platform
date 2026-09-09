"""pytest 全局夹具。"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """FastAPI 测试客户端(第 9 阶段用于健康检查等基础测试)。"""
    with TestClient(app) as c:
        yield c
