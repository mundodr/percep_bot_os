# percep_bot_os 本地模块管理框架设计文档

## 1. 目标与定位

**这是什么**：`percep_bot_os` 内置的一个**本地、轻量**的模块管理系统，把项目里所有功能模块（视觉、障碍、导航、底盘、Web UI 等）统一拉起、统一观测。

**为什么做这个**：

- 模块多了之后，一个一个手动启动很繁琐
- 模块多了容易漏启某一个，造成系统功能不完整
- 单进程内运行，需要一个集中点知道"现在谁在跑、谁挂了"

**核心承诺**：

- **一条命令默认拉起全部模块**
- **内置 Web UI**，浏览器打开就能看 / 启停 / 看日志，无需 CLI
- 状态实时刷新，模块挂了一眼就能看到

**明确不做的事**（保持简单）：

- 分布式 / 跨主机 / 跨进程消息
- 容器化、插件 entry point、动态发现
- 自动重启 / 故障级联 / 多重恢复策略
- 高度抽象的多种注册方式
- 用户/权限管理

## 2. 总体架构

```text
                ┌────────────────────────────────────────┐
                │  python -m percep_bot_os               │
                │  └─ 一条命令启动整个系统               │
                └───────────────┬────────────────────────┘
                                │
                ┌───────────────▼─────────────┐
                │     ModuleManager           │
                │  - 注册中心                  │
                │  - 启停所有模块              │
                │  - 持有 MessageBus           │
                │  - 启动 Web UI              │
                └────┬────────────┬────────┬──┘
                     │            │        │
              ┌──────▼─────┐  ┌───▼────┐  ┌▼─────────────┐
              │ MessageBus │  │  WebUI │  │  Modules     │
              │ (in-proc)  │  │  HTTP  │  │  Vision      │
              │            │  │  :8080 │  │  Obstacle    │
              │            │  │        │  │  Navigator   │
              │            │  │        │  │  Chassis     │
              │            │  │        │  │  ...         │
              └────────────┘  └────┬───┘  └──────────────┘
                                   │
                                   │  http://<host>:8080
                                   │
                            ┌──────▼──────┐
                            │   Browser   │
                            └─────────────┘
```

只有 **3 个**框架组件 + 任意多个用户模块：

- **ModuleManager**：注册 + 一键启停 + 持有内部服务（单例）
- **MessageBus**：模块间 pub/sub（极简：publish / subscribe / latest）
- **WebUI**：HTTP 服务 + 单页 HTML，浏览器直接访问

## 3. 模块生命周期

简化为 3 个对外状态：

```text
STOPPED ──start()──> RUNNING ──stop()──> STOPPED
                       │
                       └── 抛异常 ──> FAILED ──手动 restart──> RUNNING
```

- **STOPPED**：未启动（注册后默认）
- **RUNNING**：正常运行
- **FAILED**：主循环抛了未捕获异常

`STARTING / STOPPING` 仅作为内部瞬态，对 UI 只展示主状态。
不引入 INITIALIZED、DEGRADED、STALE 等中间态——多状态会让 UI 和代码都变复杂。

## 4. Module 基类

```python
import abc
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HealthStatus:
    ok: bool = True
    message: str = ""
    last_heartbeat: float = field(default_factory=time.monotonic)


class Module(abc.ABC):
    """所有功能模块的基类。子类只需要实现 _run() 即可。"""

    name: str = ""              # 必填：全局唯一
    description: str = ""

    def __init__(self, config: dict, manager: "ModuleManager"):
        self.config = config
        self.manager = manager
        self.bus = manager.bus
        self.log = manager.get_logger(self.name)

        self.state = "STOPPED"
        self.error: str | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._health = HealthStatus()

    # ---- 子类只需要写这一个 ----
    def _run(self) -> None:
        """模块主循环。每隔一段时间检查 self._stop_event.is_set()。"""
        raise NotImplementedError

    # ---- 框架调用 ----

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

    # ---- 内部 ----

    def _safe_run(self) -> None:
        try:
            self._run()
        except Exception as e:
            self.log.exception("module crashed")
            self.error = str(e)
            self._health = HealthStatus(ok=False, message=str(e))
            self.state = "FAILED"
```

子类最小实现：

```python
class HelloModule(Module):
    name = "hello"
    description = "示例模块，每秒发一次 tick"

    def _run(self):
        n = 0
        while not self._stop_event.wait(timeout=1.0):
            n += 1
            self.heartbeat(f"ticked {n}")
            self.bus.publish("hello/tick", {"n": n})
```

## 5. ModuleManager

`ModuleManager` 是单例，集成了"注册 + 启停 + Bus + WebUI"。一个对象搞定全部。

```python
class ModuleManager:
    def __init__(self, config: dict):
        self.config = config
        self.bus = MessageBus()
        self.web = WebUI(self)
        self._modules: dict[str, Module] = {}

    # ---- 注册 ----

    def register(self, cls: type[Module], cfg: dict | None = None) -> None:
        """登记并实例化一个模块。同名重复抛异常。"""

    def list(self) -> list[dict]:
        """列出所有已注册模块的当前状态（供 UI 用）。"""

    def get(self, name: str) -> Module: ...

    # ---- 启停 ----

    def start_all(self) -> None:
        """启动所有 enabled 模块，按 depends_on 拓扑排序。"""
    def stop_all(self) -> None: ...
    def restart_all(self) -> None: ...

    def start(self, name: str) -> None: ...
    def stop(self, name: str) -> None: ...
    def restart(self, name: str) -> None: ...

    # ---- 运行 ----

    def run(self) -> int:
        """阻塞主线程：start_all + WebUI + 等 SIGINT 后 stop_all，返回退出码。"""

    def get_logger(self, name: str): ...
```

依赖处理保持极简：每个模块通过配置 `depends_on` 列出依赖，`start_all` 时一次拓扑排序；检测到环立刻报错。`stop_all` 用反序。

## 6. MessageBus（极简）

```python
class MessageBus:
    def publish(self, topic: str, payload: Any) -> None: ...
    def subscribe(self, topic: str, handler: Callable[[Any], None]) -> None: ...
    def latest(self, topic: str) -> Any | None: ...
    def topics(self) -> list[str]: ...
    def rate(self, topic: str, window: float = 1.0) -> float: ...
```

- 只支持回调订阅 + "最近一条快照"
- 不支持队列、背压、序列化、跨进程
- 实现目标 ≤ 60 行 Python

topic 命名约定：`<source>/<event>`，如 `vision/goal`、`obstacle/scan`、`nav/cmd`、`chassis/state`。

## 7. 内置 Web UI（重点）

### 7.1 设计目标

- 启动后自动监听 `http://127.0.0.1:8080`，浏览器直接打开即可
- **单页 + 原生 JS**，无需任何前端构建工具，HTML/CSS/JS 内嵌在 Python 包里
- 1 秒自动刷新一次状态
- 网页上能完成所有日常操作（启停、看日志、看 topic），CLI 不必需

### 7.2 页面布局

```text
┌─────────────────────────────────────────────────────────────────────┐
│  percep_bot_os    ●Running  Uptime 00:12:34  [Stop All] [Restart All]│
├─────────────────────────────────────────────────────────────────────┤
│  Module     │ State    │ Health │ Rate    │ Message      │ Action  │
├─────────────┼──────────┼────────┼─────────┼──────────────┼─────────┤
│  vision     │ ● RUNNING│ OK     │ 28.5 Hz │ ok           │ ⏹ ↻     │
│  obstacle   │ ● RUNNING│ OK     │ 14.9 Hz │ ok           │ ⏹ ↻     │
│  navigator  │ ● RUNNING│ OK     │ 19.8 Hz │ tracking     │ ⏹ ↻     │
│  chassis    │ ● FAILED │ ERR    │ -       │ serial timeout│ ▶ ↻    │
│  webui      │ ● RUNNING│ OK     │ -       │ ok           │ ⏹       │
├─────────────────────────────────────────────────────────────────────┤
│  Logs (last 200 lines, auto scroll)         [vision ▼] [Pause]      │
│  17:30:01.123 INFO  [vision]    Detected target conf=0.82           │
│  17:30:01.140 WARN  [obstacle]  Lidar packet drop count=3           │
│  17:30:01.150 INFO  [navigator] state=TRACKING dist=1.42            │
│  ...                                                                 │
└─────────────────────────────────────────────────────────────────────┘
```

页面分三块：

1. **顶栏**：系统总状态、运行时长、全局 Stop All / Restart All 按钮
2. **模块表格**：每行一个模块，状态颜色徽章 + 单独的启 / 停 / 重启按钮
3. **日志面板**：下拉切换查看哪个模块的最近日志，可暂停滚动

状态颜色约定：

- `● RUNNING` 绿
- `● STOPPED` 灰
- `● FAILED` 红

### 7.3 后端端点

| 方法 | 路径                              | 说明                         |
|------|-----------------------------------|------------------------------|
| GET  | `/`                               | 单页 HTML                    |
| GET  | `/api/status`                     | 系统总状态（uptime、模块数） |
| GET  | `/api/modules`                    | 全部模块状态 JSON 数组       |
| GET  | `/api/modules/<name>`             | 单模块详情                   |
| POST | `/api/modules/<name>/start`       | 启动                         |
| POST | `/api/modules/<name>/stop`        | 停止                         |
| POST | `/api/modules/<name>/restart`     | 重启                         |
| POST | `/api/system/start_all`           | 一键启动                     |
| POST | `/api/system/stop_all`            | 一键停止                     |
| POST | `/api/system/restart_all`         | 一键重启                     |
| POST | `/api/system/shutdown`            | 优雅关闭整个进程             |
| GET  | `/api/logs/<name>?tail=N`         | 该模块最近 N 行日志          |
| GET  | `/api/topics`                     | 所有 topic 与 rate           |
| GET  | `/api/topics/<name>/latest`       | 该 topic 最近一条 payload    |

返回统一格式：

```json
{ "ok": true,  "data": ... }
{ "ok": false, "error": "..." }
```

### 7.4 实现选型

- 第一版用 Python 标准库 `http.server` + 后台线程，**零额外依赖**
- HTML/CSS/JS 单文件 ~250 行，放在 `framework/webui/static/index.html`，用 `importlib.resources` 读取
- 前端用原生 `fetch` + `setInterval(1000)` 轮询，不引入任何前端框架
- 如果未来需要 WebSocket 推日志，可平滑迁移到 `aiohttp`

### 7.5 安全

- 默认绑定 `127.0.0.1`，只允许本机访问
- 配置 `webui.bind: 0.0.0.0` 才暴露到局域网
- 不做认证（局域网内自用）；如有需要后续加 token

## 8. 配置文件

`config.yaml`：

```yaml
manager:
  log_dir: ./logs
  shutdown_timeout: 5.0

webui:
  enabled: true
  bind: 127.0.0.1
  port: 8080
  refresh_interval: 1.0

modules:
  vision:
    enabled: true
    class: percep_bot_os.modules.vision.VisionModule
    config:
      confidence_threshold: 0.6

  obstacle:
    enabled: true
    class: percep_bot_os.modules.obstacle.LidarObstacleModule
    config:
      port: /dev/ttyUSB1

  navigator:
    enabled: true
    class: percep_bot_os.modules.navigator.ReactiveNavigatorModule
    depends_on: [vision, obstacle]
    config:
      # 详见 reactive_navigation_design.md §12
      max_linear_speed: 0.35

  chassis:
    enabled: true
    class: percep_bot_os.modules.chassis.SerialChassisModule
    config:
      port: /dev/ttyUSB0
      baudrate: 115200
```

加载规则：

- `enabled: false` 的模块仍会注册（出现在 UI 列表），但不会被 `start_all` 启动
- `class` 是完整 Python 类路径，import 后自动注册
- `depends_on` 决定启动顺序（停止时反序）

## 9. 启动入口

```bash
# 一行命令，整个系统起来
python -m percep_bot_os --config config.yaml
```

执行流程：

1. 读取 `config.yaml`
2. 按 `modules.<name>.class` 逐一 `import` 并注册
3. 启动 WebUI 线程
4. ModuleManager 拓扑排序后顺序 `start()` 所有 enabled 模块
5. 终端打印：

   ```text
   ✓ percep_bot_os ready
     5 modules running, 0 failed
     → http://127.0.0.1:8080
   ```

6. 阻塞主线程，等 `SIGINT/SIGTERM`
7. 收到信号 → 反序 `stop_all()` → 退出

启动失败处理：

- 任意模块 `start()` 抛异常 → 记录、其他已启动模块继续运行（默认）
- 用户在 UI 上看到红色 FAILED → 按重启或修复后再启动

## 10. 与现有导航设计的对接

| 模块名     | 类路径                                         | 依赖              | 发布                 | 订阅                          |
|------------|------------------------------------------------|-------------------|----------------------|-------------------------------|
| vision     | `modules.vision.VisionModule`                  | -                 | `vision/goal`        | -                             |
| obstacle   | `modules.obstacle.LidarObstacleModule`         | -                 | `obstacle/scan`      | -                             |
| navigator  | `modules.navigator.ReactiveNavigatorModule`    | vision, obstacle  | `nav/cmd`, `nav/state` | `vision/goal`, `obstacle/scan` |
| chassis    | `modules.chassis.SerialChassisModule`          | -                 | `chassis/state`      | `nav/cmd`                     |

`navigator._run` 内即 `reactive_navigation_design.md` §10 的主循环：

```python
def _run(self):
    while not self._stop_event.wait(timeout=1.0 / self.config["control_rate"]):
        goal = self.bus.latest("vision/goal")
        scan = self.bus.latest("obstacle/scan")
        cmd = self.navigator.compute_command(goal, scan, time.monotonic())
        self.bus.publish("nav/cmd", cmd)
        self.bus.publish("nav/state", self.navigator.state_info())
        self.heartbeat(f"state={self.navigator.state_name}")
```

## 11. 验收测试用例

| 编号  | 场景 | 通过条件 |
|-------|------|----------|
| TC-1  | 注册：定义模块并 `manager.register(M)` | `manager.list()` 包含 M，state="STOPPED" |
| TC-2  | 一键启动：`python -m percep_bot_os` | 所有 enabled 模块进入 RUNNING |
| TC-3  | WebUI 打开：浏览器访问 `http://127.0.0.1:8080` | 看到模块表格，1s 自动刷新 |
| TC-4  | WebUI 启停：点 vision 行的 ⏹ | vision 状态在 1s 内变 STOPPED，其他模块不受影响 |
| TC-5  | WebUI 一键停：点 Stop All | 所有模块按反序停止，UI 全灰 |
| TC-6  | 模块崩溃：vision `_run` 抛异常 | state 变 FAILED，进程不退出，UI 标红 |
| TC-7  | 优雅停机：Ctrl-C | 反序停止所有模块，5s 内退出，退出码 0 |
| TC-8  | 依赖排序：navigator 依赖 vision/obstacle | start 顺序 vision→obstacle→navigator，stop 顺序倒过来 |
| TC-9  | 循环依赖 | `start_all` 报错并拒绝启动 |
| TC-10 | enabled=false | 模块出现在 UI 列表但状态保持 STOPPED |
| TC-11 | 日志面板：UI 选 vision，看 tail | 显示该模块最近 200 行日志 |
| TC-12 | 漏启检测：所有模块都 enabled，却有 1 个未注册成功 | 终端启动报告显示"4 running, 1 failed"，UI 红色提示 |

## 12. 开发阶段

**Phase 0：跑通骨架**

- `Module` 基类 + `ModuleManager.register / start / stop`
- `HelloModule` 跑通
- 命令行入口：`python -m percep_bot_os`
- 对应 TC-1、TC-2、TC-7

**Phase 1：内置 WebUI**

- HTTP 服务（标准库）+ 单页 HTML
- 模块表格 + 启停按钮 + 顶栏 Stop/Restart All
- 1s 自动刷新
- 对应 TC-3、TC-4、TC-5

**Phase 2：把现有模块接入**

- vision / obstacle / navigator / chassis 改为 `Module` 子类
- 配置整合
- MessageBus 接入
- 端到端联调

**Phase 3：增强 UI**

- 日志面板
- topic 速率显示
- 简单可视化（极坐标障碍图、目标方向指示）

## 13. 结论

- **一条命令**起整套系统：`python -m percep_bot_os`
- **一个浏览器标签**看清谁在跑、谁挂了，并能直接启停
- 框架代码量目标控制在 ~1000 行以内
- 后续新加的任何模块，只要继承 `Module`、写个 `_run`、在 yaml 里加一节，立即纳入管理
