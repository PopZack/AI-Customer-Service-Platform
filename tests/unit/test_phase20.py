"""Phase 20 新增能力的测试:进程内指标、检索缓存键、LLM fallback。"""

from app.ai.rag.cache import make_cache_key
from app.common import metrics
from app.common.metrics import render, reset, value

# ── 指标 ──────────────────────────────────────────────


def test_计数器递增与标签区分():
    reset()
    metrics.inc("x_total")
    metrics.inc("x_total")
    metrics.inc("x_total", kind="a")
    metrics.inc("x_total", kind="b")

    assert value("x_total") == 2
    assert value("x_total", kind="a") == 1
    assert value("x_total", kind="b") == 1
    # 同一标签不同顺序等价(frozenset 语义)
    metrics.inc("x_total", kind="a")
    assert value("x_total", kind="a") == 2


def test_prometheus_文本格式():
    """渲染输出应是合法的 Prometheus 文本格式。"""
    reset()
    metrics.inc("tool_calls_total", tool="search_knowledge")
    text = render()

    assert text.startswith("# HELP app_uptime_seconds")
    assert "app_uptime_seconds " in text
    line = next(l for l in text.splitlines() if "tool_calls_total" in l)
    assert 'tool_calls_total{tool="search_knowledge"} 1' == line


# ── 检索缓存键 ────────────────────────────────────────


def test_缓存键_归一化与维度():
    base = make_cache_key("退款多久到账", None, 6, "0")

    # 前后空白与大小写不影响(英文部分)
    assert make_cache_key("  退款多久到账 ", None, 6, "0") == base
    assert make_cache_key("REFUND", None, 6, "0") == make_cache_key("refund", None, 6, "0")

    # 以下任一维度变化都必须换键
    assert make_cache_key("退款多久到账", None, 6, "1") != base, "数据版本必须参与键"
    assert make_cache_key("退款多久到账", [1], 6, "0") != base, "知识库范围必须参与键"
    assert make_cache_key("退款多久到账", None, 8, "0") != base, "top_k 必须参与键"

    # kb_ids 顺序无关
    assert make_cache_key("q", [3, 1, 2], 6, "0") == make_cache_key("q", [1, 2, 3], 6, "0")


# ── LLM fallback ──────────────────────────────────────


async def test_主模型失败时切换备用模型(monkeypatch):
    from app.infrastructure.llm import client as llm_client

    calls: list[str] = []

    class FakeCompletions:
        async def create(self, **kwargs):
            calls.append(kwargs["model"])
            if kwargs["model"] == "primary-model":
                raise RuntimeError("primary down")
            return "ok"

    class FakeClient:
        chat = type("C", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(llm_client, "settings", type(
        "S", (), {"LLM_FALLBACK_MODEL": "fallback-model"}
    )())

    result = await llm_client._create_with_fallback(
        FakeClient(), {"model": "primary-model"}
    )
    assert result == "ok"
    assert calls == ["primary-model", "fallback-model"]


async def test_未配置备用模型时原样抛错(monkeypatch):
    import pytest

    from app.infrastructure.llm import client as llm_client

    class FakeCompletions:
        async def create(self, **kwargs):
            raise RuntimeError("down")

    class FakeClient:
        chat = type("C", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(llm_client, "settings", type(
        "S", (), {"LLM_FALLBACK_MODEL": ""}
    )())

    with pytest.raises(RuntimeError):
        await llm_client._create_with_fallback(FakeClient(), {"model": "primary-model"})
