"""WebUI HTTP 服务 — 用 Python 标准库 http.server 实现，零额外依赖。"""

from __future__ import annotations

import json
import logging
import re
import threading
from functools import cached_property
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib import resources
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from percep_bot_os.framework.manager import ModuleManager

logger = logging.getLogger("webui")


def _json_resp(ok: bool, data: Any = None, error: str = "") -> bytes:
    if ok:
        return json.dumps({"ok": True, "data": data}, default=str).encode()
    return json.dumps({"ok": False, "error": error}).encode()


class _Handler(BaseHTTPRequestHandler):
    manager: ModuleManager

    def log_message(self, fmt: str, *args: Any) -> None:
        pass

    @cached_property
    def _index_html(self) -> bytes:
        ref = resources.files("percep_bot_os.framework.webui.static").joinpath("index.html")
        return ref.read_bytes()

    def _send(self, code: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?")[0].rstrip("/") or "/"
        query = self.path.split("?")[1] if "?" in self.path else ""

        if path == "/":
            self._send(200, self._index_html, "text/html; charset=utf-8")
            return

        if path == "/api/status":
            mods = self.manager.list()
            self._send(200, _json_resp(True, {
                "uptime": round(self.manager.uptime(), 1),
                "total_modules": len(mods),
                "running": sum(1 for m in mods if m["state"] == "RUNNING"),
                "failed": sum(1 for m in mods if m["state"] == "FAILED"),
                "stopped": sum(1 for m in mods if m["state"] == "STOPPED"),
            }))
            return

        if path == "/api/modules":
            self._send(200, _json_resp(True, self.manager.list()))
            return

        m = re.match(r"^/api/modules/([^/]+)$", path)
        if m:
            name = m.group(1)
            try:
                mod = self.manager.get(name)
                h = mod.health()
                self._send(200, _json_resp(True, {
                    "name": name,
                    "description": mod.description,
                    "state": mod.state,
                    "health_ok": h.ok,
                    "health_message": h.message,
                    "error": mod.error,
                }))
            except KeyError:
                self._send(404, _json_resp(False, error=f"Module not found: {name}"))
            return

        m = re.match(r"^/api/logs/([^/]+)$", path)
        if m:
            name = m.group(1)
            tail = 200
            for part in query.split("&"):
                if part.startswith("tail="):
                    try:
                        tail = int(part.split("=")[1])
                    except ValueError:
                        pass
            self._send(200, _json_resp(True, {
                "name": name,
                "tail": tail,
                "lines": [],
            }))
            return

        if path == "/api/topics":
            topics = self.manager.bus.topics()
            data = [{"name": t, "rate": round(self.manager.bus.rate(t), 1)} for t in topics]
            self._send(200, _json_resp(True, data))
            return

        m = re.match(r"^/api/topics/([^/]+)/latest$", path)
        if m:
            topic = m.group(1)
            payload = self.manager.bus.latest(topic)
            self._send(200, _json_resp(True, payload))
            return

        self._send(404, _json_resp(False, error="Not found"))

    def do_POST(self) -> None:
        path = self.path.split("?")[0].rstrip("/")

        m = re.match(r"^/api/modules/([^/]+)/(start|stop|restart)$", path)
        if m:
            name, action = m.group(1), m.group(2)
            try:
                getattr(self.manager, action)(name)
                self._send(200, _json_resp(True, {"action": action, "module": name}))
            except KeyError:
                self._send(404, _json_resp(False, error=f"Module not found: {name}"))
            except Exception as e:
                self._send(500, _json_resp(False, error=str(e)))
            return

        system_actions = {
            "/api/system/start_all": "start_all",
            "/api/system/stop_all": "stop_all",
            "/api/system/restart_all": "restart_all",
        }
        if path in system_actions:
            getattr(self.manager, system_actions[path])()
            self._send(200, _json_resp(True, {"action": system_actions[path]}))
            return

        if path == "/api/system/shutdown":
            self.manager._shutdown_requested = True
            self._send(200, _json_resp(True, {"action": "shutdown"}))
            return

        self._send(404, _json_resp(False, error="Not found"))


class WebUIServer:
    def __init__(self, manager: ModuleManager, config: dict) -> None:
        self._manager = manager
        self._bind = config.get("bind", "127.0.0.1")
        self._port = config.get("port", 8080)
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        handler_cls = type("Handler", (_Handler,), {"manager": self._manager})
        self._server = HTTPServer((self._bind, self._port), handler_cls)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("WebUI listening on http://%s:%d", self._bind, self._port)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
