# 接口契约文档

## 1. 目的

本文档冻结系统所有模块之间的数据结构、输入输出接口和坐标约定。所有 Agent 按此契约实现，任何修改必须提交 `interface_change_request.md` 并由 Main Agent 协调。

## 2. 坐标约定

### 2.1 机器人局部坐标（base_link）

```text
x：机器人前方
y：机器人左侧
z：向上
angular_z：左转为正（从上方看逆时针）
```

### 2.2 地图坐标（map）

长距离导航和地图持久化使用 `map` 坐标系。系统不依赖 ROS TF，但必须通过 `TransformService` 提供等价变换：

```text
map <-> base_link
map <-> camera / LingBot local map
```

### 2.3 距离语义

所有模块输出的"距离"均为**机器人边缘到障碍的有效距离**（已扣除 footprint）：

```text
effective_distance = max(0, raw_distance - footprint_radius)
```

所有安全阈值（`safety_distance`、`emergency_stop_distance` 等）均为纯安全裕度，与机器人尺寸解耦。

## 3. 核心数据结构

### 3.1 导航基座

```python
from dataclasses import dataclass, field
from typing import Sequence
import math

@dataclass
class LocalGoal:
    """纯局部导航的最小目标接口。"""
    x: float
    y: float
    confidence: float
    timestamp: float

@dataclass
class LocalSubgoal:
    """长距离导航和探索模式使用的扩展目标。
    ReactiveNavigator 只读取 x, y, confidence, timestamp 四个字段，
    其余字段用于路径管理和调试追踪。"""
    x: float
    y: float
    confidence: float
    route_id: str
    waypoint_id: str
    timestamp: float
    source: str = "global_route"  # global_route | semantic_goal | exploration | recovery

@dataclass
class ObstacleScan:
    """角度-距离数组，距离已扣除 footprint。"""
    angles: Sequence[float]      # rad，单调递增
    distances: Sequence[float]   # m，无效值为 math.inf
    timestamp: float

@dataclass
class VelocityCommand:
    linear_x: float    # m/s
    angular_z: float   # rad/s

@dataclass
class RobotFootprint:
    shape: str = "rectangle"
    length: float = 0.40
    width: float = 0.30
    height: float = 0.50
    radius: float = 0.0

    @property
    def inscribed_radius(self) -> float:
        if self.shape == "circle":
            return self.radius
        return min(self.length, self.width) / 2.0

    @property
    def circumscribed_radius(self) -> float:
        if self.shape == "circle":
            return self.radius
        return math.hypot(self.length / 2.0, self.width / 2.0)

@dataclass
class EdgeFollowContext:
    active: bool = False
    bypass_side: str = "left"
    obstacle_side: str = "right"
    start_time: float = 0.0
    last_seen_obstacle_distance: float = math.inf
    last_progress_time: float = 0.0

@dataclass
class NavigatorState:
    state: str = "IDLE"
    last_goal_seen_time: float = 0.0
    last_emergency_stop_time: float = 0.0
    last_command: VelocityCommand = field(
        default_factory=lambda: VelocityCommand(0.0, 0.0)
    )
    edge_follow: EdgeFollowContext = field(default_factory=EdgeFollowContext)
```

### 3.2 大脑

```python
@dataclass
class BrainObservation:
    timestamp: float
    user_command: str
    image_ref: str | None
    map_summary: dict
    semantic_summary: dict
    navigation_state: dict
    exploration_state: dict
    safety_state: dict

@dataclass
class BrainDecision:
    intent: str       # navigate | explore | semantic_search | inspect | return_home | pause | stop | ask_user
    target_query: str | None
    map_goal_id: str | None
    mode: str
    constraints: dict
    requires_confirmation: bool
    confidence: float
    explanation: str
    timestamp: float
```

`BrainDecision` 约束：

- `intent` 必须在白名单内，否则拒绝
- `confidence` 范围 [0, 1]
- 不允许包含 `linear_x`、`angular_z` 或任何速度字段
- 解析失败或超时时按 `fallback_on_error` 执行（默认 pause）

### 3.3 全局导航

```python
@dataclass
class GlobalNavigationGoal:
    query: str | None
    map_goal_id: str | None
    map_position: tuple[float, float, float] | None
    timestamp: float
    mode: str = "navigate"  # navigate | explore | inspect

@dataclass
class RouteWaypoint:
    waypoint_id: str
    position_map: tuple[float, float, float]
    heading: float | None = None
    semantic_hint: str | None = None

@dataclass
class GlobalRoute:
    route_id: str
    waypoints: list[RouteWaypoint]
    corridor_width: float
    timestamp: float

@dataclass
class ExploreRoute:
    route_id: str
    exploration_target_id: str
    waypoints: list[RouteWaypoint]
    corridor_width: float
    expected_information_gain: float
    timestamp: float
```

### 3.4 探索

```python
@dataclass
class ExplorationTarget:
    target_id: str
    position_map: tuple[float, float, float]
    yaw_hint: float | None
    score: float
    target_type: str = "frontier"  # frontier | semantic_unknown | coverage_gap | inspection
    timestamp: float = 0.0

@dataclass
class ExplorationState:
    active: bool = False
    mode: str = "frontier"  # frontier | coverage | semantic_search
    current_target_id: str | None = None
    visited_target_ids: list[str] = field(default_factory=list)
    last_saved_map_time: float = 0.0
    last_progress_time: float = 0.0
```

### 3.5 语义地图

```python
@dataclass
class MapFrame:
    frame_id: int
    timestamp: float
    image_path: str | None
    intrinsic: object
    camera_to_map: object
    depth: object | None = None
    world_points: object | None = None
    confidence: object | None = None

@dataclass
class SemanticRegion:
    frame_id: int
    bbox_xyxy: tuple[float, float, float, float]
    mask: object | None
    label_hint: str | None
    image_embedding: object
    clip_confidence: float
    timestamp: float

@dataclass
class SemanticObject:
    object_id: int
    position_map: tuple[float, float, float]
    position_robot: tuple[float, float, float]
    embedding: object
    score: float
    observations: int
    first_seen_time: float
    last_seen_time: float
    radius: float = 0.25
    label: str | None = None
    status: str = "active"  # active | stale | rejected

@dataclass
class SemanticGoal:
    object_id: int
    x: float
    y: float
    z: float
    semantic_score: float
    geometric_confidence: float
    confidence: float
    timestamp: float
    text_query: str
```

### 3.6 地图持久化

```python
@dataclass
class MapUpdate:
    update_id: str
    timestamp: float
    robot_pose_map: tuple[float, float, float]
    occupied_points: object
    free_space_rays: object
    semantic_objects: list[int]
    changed_area_bounds: tuple[float, float, float, float]

@dataclass
class SavedMapManifest:
    map_id: str
    version: int
    created_time: float
    updated_time: float
    metric_map_path: str
    semantic_db_path: str
    route_graph_path: str
    snapshot_dir: str
```

## 4. 模块接口

### 4.1 ReactiveNavigator

```text
输入:
  LocalGoal | LocalSubgoal    (只读取 x, y, confidence, timestamp)
  ObstacleScan
  NavigatorState

输出:
  VelocityCommand
  NavigatorState (更新后)

频率: 20 Hz
Owner: Navigation Core Agent
```

### 4.2 Qwen3-VL Brain

```text
输入:
  BrainObservation

输出:
  BrainDecision

频率: 按需（每次任务决策或状态变化时调用）
禁止输出: VelocityCommand 或任何速度字段
Owner: Brain Agent
```

### 4.3 Route Manager

```text
输入:
  GlobalRoute | ExploreRoute
  当前机器人位姿 (base_link 或 map)
  ObstacleScan (用于阻塞检测)

输出:
  LocalSubgoal
  ReplanRequest (阻塞时)

频率: 10-20 Hz
Owner: Route Manager Agent
```

### 4.4 Global Planner

```text
输入:
  GlobalNavigationGoal
  Persistent Map (occupancy grid / route graph)
  ReplanRequest (可选)

输出:
  GlobalRoute | ExploreRoute

接口: PlannerClient (抽象)
实现: SimplePlanner (A*/Dijkstra) | MockPlanner (测试用)
Owner: Route Manager Agent
```

### 4.5 Geometry Adapter (LingBot-Map -> ObstacleScan)

```text
输入:
  MapFrame (depth / world_points / camera pose / confidence)

输出:
  ObstacleScan

频率: 2-10 Hz (取决于 LingBot-Map 推理速度)
Owner: Semantic Map Agent
```

### 4.6 CLIP Encoder

```text
输入:
  图像 crop / mask (SemanticRegion)
  文本查询 (str)

输出:
  image_embedding (向量)
  text_embedding (向量)
  similarity (float)

频率: 1-5 Hz
Owner: Semantic Map Agent
```

### 4.7 Goal Selector

```text
输入:
  text_embedding
  SemanticObject 列表
  当前机器人位姿

输出:
  SemanticGoal | None

Owner: Semantic Map Agent
```

### 4.8 Exploration Planner

```text
输入:
  Persistent Map
  ExplorationState
  BrainDecision (intent=explore 时)

输出:
  ExplorationTarget 列表
  ExploreRoute (通过 PlannerClient 生成)

Owner: Exploration Agent
```

### 4.9 Map Store

```text
输入:
  MapUpdate

输出:
  SavedMapManifest (版本递增)
  snapshot 文件

约束:
  atomic write
  versioned manifest
  动态障碍只写入 dynamic layer
Owner: Map Store Agent
```

### 4.10 Transform Service

```text
输入:
  源坐标系、目标坐标系、点或位姿

输出:
  变换后的点或位姿

支持的变换:
  map <-> base_link
  map <-> camera
  camera <-> base_link

Owner: Semantic Map Agent
```

## 5. 安全优先级

所有模块必须遵守以下优先级，高优先级可覆盖低优先级决策：

```text
Emergency Stop
    >
ObstacleScan Safety
    >
Global Route Corridor Validity
    >
Exploration Frontier Validity
    >
Target Geometry Validity
    >
BrainDecision Validity
    >
CLIP Semantic Score
```

## 6. 接口变更流程

任何 Agent 需要修改本文档中的接口时：

```text
1. 提交 interface_change_request.md，说明：
   - 变更内容
   - 变更原因
   - 受影响的模块和 Agent
   - 向后兼容性

2. Main Agent 评估影响范围

3. 受影响 Agent 确认可行性

4. 更新本文档

5. 受影响 Agent 同步修改
```

禁止未经此流程的单方面接口修改。

## 7. 辅助函数契约

```python
def distance_in_sector(scan: ObstacleScan, a_min: float, a_max: float,
                       quantile: float = 0.2) -> float:
    """返回扇区 [a_min, a_max] 内的代表距离（默认 20% 分位数）。
    若扇区内无有效采样，返回 math.inf。"""

def distance_at_angle(scan: ObstacleScan, angle: float,
                      tolerance: float = 0.05) -> float:
    """返回最接近 angle 的采样点距离。"""
```

## 8. 配置接口

所有模块通过统一 YAML 配置文件加载参数。配置前缀分组：

```text
brain.*          → Brain Agent
global_planner.* → Route Manager Agent
route_manager.*  → Route Manager Agent
exploration.*    → Exploration Agent
map_persistence.* → Map Store Agent
semantic_map.*   → Semantic Map Agent
lingbot_map.*    → Semantic Map Agent
clip.*           → Semantic Map Agent
region_proposal.* → Semantic Map Agent
geometry_adapter.* → Semantic Map Agent
goal_selection.* → Semantic Map Agent
nav.*            → Navigation Core Agent
safety.*         → Navigation Core Agent
edge.*           → Navigation Core Agent
robot.*          → Architecture Agent (共享)
sensors.*        → Architecture Agent (共享)
chassis.*        → Navigation Core Agent
```

启动时参数自检：

```text
assert safety.emergency_stop_distance < safety.safety_distance
assert safety.safety_distance < safety.slowdown_distance
assert safety.emergency_clear_distance > safety.emergency_stop_distance
assert nav.goal_tolerance >= robot.inscribed_radius + 0.05
assert brain.allow_direct_velocity_command == false
```
