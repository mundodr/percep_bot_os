"""HelloModule —— 示例模块，每秒发一次 tick。"""

from percep_bot_os.framework.module import Module


class HelloModule(Module):
    name = "hello"
    description = "示例模块，每秒发一次 tick"

    def _run(self) -> None:
        n = 0
        while not self._stop_event.wait(timeout=1.0):
            n += 1
            self.heartbeat(f"ticked {n}")
            self.bus.publish("hello/tick", {"n": n})
