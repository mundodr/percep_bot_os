"""MessageBus — 极简进程内 pub/sub。

目标 ≤60 行。支持回调订阅 + 最近一条快照 + 频率统计。
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any, Callable


class MessageBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[Callable[[Any], None]]] = defaultdict(list)
        self._latest: dict[str, Any] = {}
        self._timestamps: dict[str, list[float]] = defaultdict(list)

    def publish(self, topic: str, payload: Any) -> None:
        with self._lock:
            self._latest[topic] = payload
            self._timestamps[topic].append(time.monotonic())
            handlers = list(self._subscribers[topic])
        for handler in handlers:
            try:
                handler(payload)
            except Exception:
                pass

    def subscribe(self, topic: str, handler: Callable[[Any], None]) -> None:
        with self._lock:
            self._subscribers[topic].append(handler)

    def latest(self, topic: str) -> Any | None:
        with self._lock:
            return self._latest.get(topic)

    def topics(self) -> list[str]:
        with self._lock:
            return list(self._latest.keys())

    def rate(self, topic: str, window: float = 1.0) -> float:
        now = time.monotonic()
        with self._lock:
            stamps = self._timestamps.get(topic, [])
            cutoff = now - window
            recent = [t for t in stamps if t >= cutoff]
            self._timestamps[topic] = recent
        if len(recent) < 2:
            return 0.0
        span = recent[-1] - recent[0]
        return (len(recent) - 1) / span if span > 0 else 0.0
