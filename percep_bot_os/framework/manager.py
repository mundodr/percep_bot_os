"""ModuleManager — 注册中心 + 一键启停 + Bus + WebUI。"""

from __future__ import annotations

import importlib
import logging
import os
import signal
import time
from typing import Any

from percep_bot_os.framework.bus import MessageBus
from percep_bot_os.framework.module import Module


class ModuleManager:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.bus = MessageBus()
        self._modules: dict[str, Module] = {}
        self._start_time = time.monotonic()
        self._shutdown_requested = False

        log_dir = config.get("manager", {}).get("log_dir", "./logs")
        os.makedirs(log_dir, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )

    # ---- 注册 ----

    def register(self, cls: type[Module], cfg: dict | None = None) -> None:
        """登记并实例化一个模块。同名重复抛异常。"""
        name = cls.name
        if not name:
            raise ValueError(f"Module class {cls} has no name")
        if name in self._modules:
            raise ValueError(f"Duplicate module name: {name}")
        mod = cls(cfg or {}, self)
        self._modules[name] = mod

    def list(self) -> list[dict[str, Any]]:
        """列出所有已注册模块的当前状态。"""
        result = []
        for name, mod in self._modules.items():
            h = mod.health()
            result.append({
                "name": name,
                "description": mod.description,
                "state": mod.state,
                "health_ok": h.ok,
                "health_message": h.message,
                "error": mod.error,
            })
        return result

    def get(self, name: str) -> Module:
        if name not in self._modules:
            raise KeyError(f"Module not found: {name}")
        return self._modules[name]

    # ---- 启停 ----

    def _topo_sort(self) -> list[str]:
        """按 depends_on 拓扑排序，检测循环依赖。"""
        graph: dict[str, list[str]] = {}
        for name, mod in self._modules.items():
            deps = getattr(mod, "depends_on", []) or []
            if isinstance(deps, str):
                deps = [deps]
            graph[name] = list(deps)

        visited: set[str] = set()
        in_stack: set[str] = set()
        order: list[str] = []

        def dfs(node: str) -> None:
            if node in in_stack:
                raise RuntimeError(f"Circular dependency detected involving: {node}")
            if node in visited:
                return
            in_stack.add(node)
            for dep in graph.get(node, []):
                if dep in graph:
                    dfs(dep)
            in_stack.remove(node)
            visited.add(node)
            order.append(node)

        for name in graph:
            dfs(name)
        return order

    def start_all(self) -> None:
        order = self._topo_sort()
        for name in order:
            mod = self._modules[name]
            enabled = self.config.get("modules", {}).get(name, {}).get("enabled", True)
            if enabled and mod.state != "RUNNING":
                try:
                    mod.start()
                except Exception as e:
                    mod.log.error("Failed to start: %s", e)

    def stop_all(self) -> None:
        order = self._topo_sort()
        timeout = self.config.get("manager", {}).get("shutdown_timeout", 5.0)
        for name in reversed(order):
            mod = self._modules[name]
            if mod.state == "RUNNING":
                mod.stop(timeout=timeout)

    def restart_all(self) -> None:
        self.stop_all()
        self.start_all()

    def start(self, name: str) -> None:
        self.get(name).start()

    def stop(self, name: str) -> None:
        self.get(name).stop()

    def restart(self, name: str) -> None:
        mod = self.get(name)
        mod.stop()
        mod.start()

    # ---- 运行 ----

    def uptime(self) -> float:
        return time.monotonic() - self._start_time

    def run(self) -> int:
        """阻塞主线程：start_all + WebUI + 等 SIGINT 后 stop_all。"""
        from percep_bot_os.framework.webui.server import WebUIServer

        webui_cfg = self.config.get("webui", {})
        webui: WebUIServer | None = None
        if webui_cfg.get("enabled", True):
            webui = WebUIServer(self, webui_cfg)
            webui.start()

        self.start_all()

        modules = self.list()
        running = sum(1 for m in modules if m["state"] == "RUNNING")
        failed = sum(1 for m in modules if m["state"] == "FAILED")
        bind = webui_cfg.get("bind", "127.0.0.1")
        port = webui_cfg.get("port", 8080)

        print("\n✓ percep_bot_os ready")
        print(f"  {running} modules running, {failed} failed")
        if webui:
            print(f"  → http://{bind}:{port}\n")

        def _signal_handler(sig: int, frame: Any) -> None:
            self._shutdown_requested = True

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        try:
            while not self._shutdown_requested:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

        self.stop_all()
        if webui:
            webui.stop()
        return 0

    def get_logger(self, name: str) -> logging.Logger:
        return logging.getLogger(f"mod.{name}")

    def load_modules_from_config(self) -> None:
        """从 config 中动态导入并注册模块。"""
        modules_cfg = self.config.get("modules", {})
        for name, mcfg in modules_cfg.items():
            class_path = mcfg.get("class", "")
            if not class_path:
                continue
            module_path, class_name = class_path.rsplit(".", 1)
            try:
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                depends = mcfg.get("depends_on", [])
                if depends:
                    cls.depends_on = depends
                self.register(cls, mcfg.get("config", {}))
            except Exception as e:
                logging.getLogger("manager").error(
                    "Failed to load module %s (%s): %s", name, class_path, e
                )
