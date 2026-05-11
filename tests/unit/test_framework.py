"""框架核心组件测试。"""

from __future__ import annotations

import time

import pytest

from percep_bot_os.framework.bus import MessageBus
from percep_bot_os.framework.manager import ModuleManager
from percep_bot_os.framework.module import Module

# ---------------------------------------------------------------------------
# 测试辅助模块
# ---------------------------------------------------------------------------


class _DummyModule(Module):
    name = "dummy"
    description = "用于测试的虚拟模块"

    def _run(self) -> None:
        while not self._stop_event.wait(timeout=0.05):
            self.heartbeat("ok")


class _CrashModule(Module):
    name = "crash"
    description = "启动后立即崩溃"

    def _run(self) -> None:
        raise RuntimeError("boom")


class _DepA(Module):
    name = "dep_a"
    depends_on: list[str] = []

    def _run(self) -> None:
        while not self._stop_event.wait(0.05):
            pass


class _DepB(Module):
    name = "dep_b"
    depends_on = ["dep_a"]

    def _run(self) -> None:
        while not self._stop_event.wait(0.05):
            pass


class _CycleA(Module):
    name = "cycle_a"
    depends_on = ["cycle_b"]

    def _run(self) -> None:
        pass


class _CycleB(Module):
    name = "cycle_b"
    depends_on = ["cycle_a"]

    def _run(self) -> None:
        pass


def _make_manager(**overrides: object) -> ModuleManager:
    cfg: dict = {"manager": {"log_dir": "./logs"}, "modules": {}}
    cfg.update(overrides)  # type: ignore[arg-type]
    return ModuleManager(cfg)


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------


def test_module_register() -> None:
    mgr = _make_manager()
    mgr.register(_DummyModule)
    names = [m["name"] for m in mgr.list()]
    assert "dummy" in names
    assert mgr.list()[0]["state"] == "STOPPED"


def test_module_start_stop() -> None:
    mgr = _make_manager()
    mgr.register(_DummyModule)
    mod = mgr.get("dummy")

    mod.start()
    assert mod.state == "RUNNING"
    time.sleep(0.1)
    assert mod.health().ok

    mod.stop()
    assert mod.state == "STOPPED"


def test_message_bus_publish_subscribe() -> None:
    bus = MessageBus()
    received: list[dict] = []
    bus.subscribe("test/topic", received.append)
    bus.publish("test/topic", {"val": 42})
    assert len(received) == 1
    assert received[0]["val"] == 42


def test_message_bus_latest() -> None:
    bus = MessageBus()
    assert bus.latest("x") is None
    bus.publish("x", "hello")
    assert bus.latest("x") == "hello"
    bus.publish("x", "world")
    assert bus.latest("x") == "world"


def test_manager_start_all_stop_all() -> None:
    mgr = _make_manager(modules={
        "dep_a": {"enabled": True},
        "dep_b": {"enabled": True},
    })
    mgr.register(_DepA)
    mgr.register(_DepB)
    mgr.start_all()
    time.sleep(0.1)

    states = {m["name"]: m["state"] for m in mgr.list()}
    assert states["dep_a"] == "RUNNING"
    assert states["dep_b"] == "RUNNING"

    mgr.stop_all()
    states = {m["name"]: m["state"] for m in mgr.list()}
    assert states["dep_a"] == "STOPPED"
    assert states["dep_b"] == "STOPPED"


def test_hello_module() -> None:
    from percep_bot_os.modules.hello import HelloModule

    mgr = _make_manager()
    mgr.register(HelloModule)
    mod = mgr.get("hello")
    mod.start()
    time.sleep(1.5)
    mod.stop()

    tick = mgr.bus.latest("hello/tick")
    assert tick is not None
    assert tick["n"] >= 1


def test_circular_dependency_detection() -> None:
    mgr = _make_manager(modules={
        "cycle_a": {"enabled": True},
        "cycle_b": {"enabled": True},
    })
    mgr.register(_CycleA)
    mgr.register(_CycleB)
    with pytest.raises(RuntimeError, match="Circular dependency"):
        mgr.start_all()


def test_module_crash_to_failed() -> None:
    mgr = _make_manager()
    mgr.register(_CrashModule)
    mod = mgr.get("crash")
    mod.start()
    time.sleep(0.3)
    assert mod.state == "FAILED"
    assert mod.error == "boom"
    assert not mod.health().ok
