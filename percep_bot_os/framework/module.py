"""Module 基类和 HealthStatus。

所有功能模块继承 Module，只需实现 _run() 即可。
"""

from __future__ import annotations

import abc
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from percep_bot_os.framework.manager import ModuleManager


@dataclass
class HealthStatus:
    ok: bool = True
    message: str = ""
    last_heartbeat: float = field(default_factory=time.monotonic)


class Module(abc.ABC):
    """所有功能模块的基类。子类只需要实现 _run() 即可。"""

    name: str = ""
    description: str = ""
    depends_on: list[str] = []

    def __init__(self, config: dict, manager: ModuleManager) -> None:
        self.config = config
        self.manager = manager
        self.bus = manager.bus
        self.log = manager.get_logger(self.name)
        self.state = "STOPPED"
        self.error: str | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._health = HealthStatus()

    @abc.abstractmethod
    def _run(self) -> None:
        """模块主循环。每隔一段时间检查 self._stop_event.is_set()。"""
        raise NotImplementedError

    def start(self) -> None:
        if self.state == "RUNNING":
            return
        self._stop_event.clear()
        self.error = None
        self._thread = threading.Thread(
            target=self._safe_run, name=f"mod-{self.name}", daemon=True
        )
        self._thread.start()
        self.state = "RUNNING"

    def stop(self, timeout: float = 5.0) -> None:
        if self.state != "RUNNING":
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        self.state = "STOPPED"

    def health(self) -> HealthStatus:
        return self._health

    def heartbeat(self, message: str = "") -> None:
        """子类在 _run 循环里调用，刷新心跳和提示文案。"""
        self._health = HealthStatus(ok=True, message=message)

    def _safe_run(self) -> None:
        try:
            self._run()
        except Exception as e:
            self.log.exception("module crashed")
            self.error = str(e)
            self._health = HealthStatus(ok=False, message=str(e))
            self.state = "FAILED"
