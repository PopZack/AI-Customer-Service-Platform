"""轻量进程内指标:内存计数器 + Prometheus 文本格式。

为什么不用 prometheus-client / OpenTelemetry:本项目收尾采用精简路线,
需要的是"能看到请求量、缓存命中、工具调用次数"这几个关键计数,
为此引入一个客户端库(或整套 OTel)不成比例。这里的实现约 60 行、零依赖,
格式与 Prometheus 兼容 —— 将来真要接监控系统,一个抓取端点就能直接用。

线程安全:CPython 下 `dict[k] = dict[k] + 1` 的读改写对 int 而言,
最坏情况是并发下少计几次(计数器场景可接受),不值得为此上锁。
"""

from __future__ import annotations

import time

# {(指标名, frozenset(labels)): value}
_counters: dict[tuple[str, frozenset[tuple[str, str]]], int] = {}
#: 进程启动时间,用于计算 uptime
_STARTED_AT = time.time()


def inc(name: str, **labels: str) -> None:
    """计数器 +1。labels 顺序无关。"""
    key = (name, frozenset(labels.items()))
    _counters[key] = _counters.get(key, 0) + 1


def value(name: str, **labels: str) -> int:
    """读取某个计数器的当前值(测试用)。"""
    return _counters.get((name, frozenset(labels.items())), 0)


def render() -> str:
    """输出 Prometheus 文本格式。无计数时输出注释行,仍是合法响应。"""
    lines = [
        "# HELP app_uptime_seconds Process uptime in seconds",
        "# TYPE app_uptime_seconds gauge",
        f"app_uptime_seconds {time.time() - _STARTED_AT:.0f}",
    ]
    for (name, labels), v in sorted(_counters.items()):
        label_str = ""
        if labels:
            inner = ",".join(f'{k}="{v}"' for k, v in sorted(labels))
            label_str = f"{{{inner}}}"
        lines.append(f"{name}{label_str} {v}")
    return "\n".join(lines) + "\n"


def reset() -> None:
    """清空计数器。仅供测试。"""
    _counters.clear()
