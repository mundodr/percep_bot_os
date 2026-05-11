# LingBot-Map + CLIP Embedding 长距离语义几何地图与探索设计文档

## 1. 目标

在已有《非 ROS2 反应式视觉导航与避障系统设计文档》的基础上，增加一个用于**长距离导航**的语义几何地图层。

本设计假设系统已经有：

- 可用于长距离导航的已有地图或初始种子地图
- 已有地图路径规划能力
- 可输出全局路径、路径点或导航走廊的 planner

已有地图可以是完整地图、局部地图，也可以是随着机器人探索逐步扩展的长期地图。因此，LingBot-Map + CLIP 不只作为已有地图和路径规划系统之上的**视觉语义增强层**与**局部几何校验层**，还需要支持**边探索边保存地图**。

该地图层由两部分组成：

- **LingBot-Map**：从相机视频或图像序列中恢复局部 3D 几何、深度、点云和相机位姿
- **CLIP Embedding**：把图像区域、物体候选、文本目标映射到同一个语义向量空间
- **Qwen3-VL 4B Brain**：使用 `qwen3-vl:4b` 做高层任务理解、地图问答、探索意图判断和语义目标解释

最终目标是让机器人能够完成：

```text
用户文字目标 / 地图目标点 / 长距离任务
        ↓
qwen3-vl:4b Task Brain
        ↓
已有地图 / 探索地图 + 全局路径规划
        ↓
GlobalRoute / Waypoints / Route Corridor
        ↓
LingBot-Map + CLIP 语义几何地图增强
        +
局部障碍、语义目标确认、未知区域探索
        ↓
LocalSubgoal + ObstacleScan
        ↓
ReactiveNavigator
        ↓
VelocityCommand
        ↓
Map Update 持久化保存
```

系统仍然保持非 ROS2、非 Nav2 的设计约束。全局地图和路径规划可以存在，但 LingBot-Map + CLIP 不能绕过安全导航基座直接控制底盘。

## 2. 设计边界

### 2.1 已有全局地图与路径规划职责

已有地图路径规划系统负责：

- 维护长期地图
- 接收长距离目标
- 计算全局路径
- 输出路径点、局部子目标或导航走廊
- 在大范围阻塞时触发重规划
- 接收探索产生的地图增量，并更新可通行区域、障碍区域、语义锚点和未知区域边界

建议输出接口：

```text
GlobalNavigationGoal
        ↓
GlobalRoute
        ↓
LocalSubgoal
```

### 2.2 已有导航基座职责

已有反应式导航基座的职责保持不变，但输入目标从“最终目标”变成“局部子目标”：

```text
LocalSubgoal + ObstacleScan -> ReactiveNavigator -> VelocityCommand
```

它负责：

- 急停
- 避障
- 目标跟踪
- 边缘跟随
- 速度和加速度限幅
- 底盘安全命令输出
- 沿全局路径的局部执行

### 2.3 LingBot-Map + CLIP 地图层职责

新增地图层负责：

- 从相机序列恢复局部 3D 几何
- 从点云或深度中生成局部障碍扫描 `ObstacleScan`
- 从图像区域中提取 CLIP image embedding
- 从用户文本中提取 CLIP text embedding
- 将语义目标绑定到 3D 位置
- 输出当前最可信的 `SemanticGoal`
- 将全局路径上的下一段转换为导航基座需要的 `LocalSubgoal`
- 用语义识别确认“到达的是不是正确地点或正确物体”
- 将临时障碍、动态障碍、局部不可通行区域反馈给全局 planner
- 在探索模式下发现 frontier / 未知区域边界
- 将局部几何、语义对象、探索状态增量写入长期地图

### 2.4 Qwen3-VL 4B 大脑职责

系统大脑使用 `qwen3-vl:4b`。它是高层任务编排模块，不是运动控制器。

大脑负责：

- 理解用户自然语言任务，例如“去会议室”、“继续探索”、“找红色椅子”
- 根据当前图像、地图摘要、语义对象和探索状态生成结构化任务决策
- 将自然语言目标转换为 `GlobalNavigationGoal` 或语义查询
- 判断是否进入 `navigate`、`explore`、`semantic_search`、`inspect`、`return_home` 等任务模式
- 在探索过程中根据地图摘要决定继续探索、切换 frontier、停止探索或请求人工确认
- 做地图问答，例如“刚才发现了什么”、“哪个区域还没探索”
- 生成给 CLIP 的文本查询和给 planner 的目标约束

大脑不负责：

- 直接输出 `VelocityCommand`
- 绕过 `Route Planner`、`Route Manager` 或 `ReactiveNavigator`
- 代替急停、安全距离判断和碰撞检测
- 在低置信地图或定位异常时强制继续探索

推荐输出必须是结构化 JSON，而不是自由文本直接驱动底盘。

### 2.5 明确不负责

地图层不负责：

- 直接控制底盘
- 替代急停和避障
- 替代已有全局路径规划
- 在没有定位或地图一致性约束时保证长期地图完全无漂移
- 用 CLIP 判断安全距离
- 用语义相似度代替几何碰撞检测

安全距离永远来自深度、点云、雷达或仿真几何。

## 3. 总体架构

```text
Long-range Goal / Explore Request
        ↓
Qwen3-VL 4B Task Brain
        ↓
Structured BrainDecision
        ↓
Existing Global Map / Persistent Map Store
        ↓
Route Planner / Exploration Planner
        ↓
GlobalRoute / ExploreRoute / Waypoints / Route Corridor
        ↓
Route Manager
        ↓
LocalSubgoal

RGB Camera / Video Stream
        ↓
LingBot-Map
        ↓
Depth / World Points / Camera Pose / Intrinsics
        ↓
Geometric Map Adapter
        ↓
ObstacleScan

RGB Frame
        ↓
Region Proposal / Object Detector / Segmentation
        ↓
CLIP Image Encoder
        ↓
Semantic Object Memory

Text Goal
        ↓
Qwen3-VL 4B Task Brain
        ↓
CLIP Text Encoder
        ↓
Semantic Query
        ↓
SemanticGoal / Map Anchor / Destination Confirmation
        ↓
Route Goal or LocalSubgoal Correction

Local Geometry + Semantic Objects + Route Events
        ↓
Map Fusion / Persistence
        ↓
Saved Metric-Semantic Map

LocalSubgoal + ObstacleScan
        ↓
ReactiveNavigator
        ↓
VelocityCommand
        ↓
Chassis Driver / Simulator
```

## 4. LingBot-Map 接入方式

LingBot-Map 当前适合承担“视觉重建模块”的角色。它的公开仓库说明其核心能力是流式 3D 重建，并提供：

- `demo.py`：交互式点云可视化
- `demo_render/batch_demo.py`：离线视频或图像序列处理、渲染和预测结果保存
- streaming / windowed 两种推理方式
- keyframe interval 和 window 参数，用于长序列

参考：

- https://github.com/Robbyant/lingbot-map
- https://github.com/Robbyant/lingbot-map/blob/main/demo.py
- https://github.com/Robbyant/lingbot-map/blob/main/demo_render/batch_demo.py

第一版建议先用离线模式验证，不直接上实时闭环。

```text
video.mp4 / image_folder
        ↓
LingBot-Map batch inference
        ↓
predictions
        ↓
prediction_to_scan.py
        ↓
ObstacleScan replay
```

## 5. CLIP Embedding 与 Qwen3-VL 大脑接入方式

CLIP 用于把文字目标和图像区域对齐。

输入：

- 文本：`"red chair"`、`"person"`、`"charging dock"`、`"blue box"`
- 图像区域：目标框、分割 mask、候选 crop

输出：

- `text_embedding`
- `image_embedding`
- `similarity = cosine(text_embedding, image_embedding)`

第一版推荐使用 **object-level CLIP**，不要一开始做 dense per-pixel embedding。

推荐流程：

```text
RGB frame
    ↓
候选区域生成
    ↓
crop / masked crop
    ↓
CLIP image embedding
    ↓
绑定对应 3D 点
    ↓
SemanticObject
```

候选区域来源按优先级：

1. 现成检测器，例如 YOLO、GroundingDINO、Detic、OWL-ViT
2. 分割器，例如 SAM / SAM2
3. 手工 ROI，用于早期调试
4. 网格滑窗，只用于兜底验证

### 5.1 Qwen3-VL 4B 大脑接入方式

`qwen3-vl:4b` 作为本地或局域网内的大脑模型运行。推荐通过 Ollama 或 OpenAI-compatible HTTP 服务封装为统一接口。

输入给大脑的上下文应被压缩成任务相关摘要：

```text
user_command:
  用户原始指令

current_image:
  当前关键帧或压缩图像

map_summary:
  当前地图区域、已知目标、未知 frontier、阻塞区域

semantic_summary:
  CLIP / SemanticObject 的候选对象列表

navigation_state:
  当前 route、LocalSubgoal、ReactiveNavigator 状态、安全状态

exploration_state:
  当前探索模式、coverage、frontier 列表、最近保存版本
```

大脑输出必须是结构化决策：

```json
{
  "intent": "explore",
  "target_query": "red chair",
  "map_goal_id": null,
  "mode": "semantic_search",
  "constraints": {
    "avoid_unknown_fast_motion": true,
    "max_explore_time": 600
  },
  "requires_confirmation": false,
  "confidence": 0.82,
  "explanation": "Search unexplored areas for a red chair and save map updates.",
  "timestamp": 1715400000.0
}
```

允许的 `intent`：

```text
navigate
explore
semantic_search
inspect
return_home
pause
stop
ask_user
```

若大脑输出无法解析、超时、或 intent 不在白名单内，系统必须保持当前安全状态或停车。

## 6. 核心数据结构

```python
from dataclasses import dataclass, field
from typing import Sequence
import math

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
    intent: str  # navigate | explore | semantic_search | inspect | return_home | pause | stop | ask_user
    target_query: str | None
    map_goal_id: str | None
    mode: str
    constraints: dict
    requires_confirmation: bool
    confidence: float
    explanation: str
    timestamp: float

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

@dataclass
class LocalSubgoal:
    x: float
    y: float
    confidence: float
    route_id: str
    waypoint_id: str
    timestamp: float
    source: str = "global_route"  # global_route | semantic_goal | exploration | recovery

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

@dataclass
class ObstacleScan:
    angles: Sequence[float]
    distances: Sequence[float]
    timestamp: float
```

`SemanticGoal` 可作为全局目标解析、路径锚点确认或局部纠偏输入。真正发送给反应式导航器的是 `LocalSubgoal`。`ReactiveNavigator` 只读取 `x, y, confidence, timestamp` 四个字段（与 `LocalGoal` 兼容），`route_id`、`waypoint_id`、`source` 用于路径管理和调试追踪：

```python
LocalSubgoal(
    x=route_subgoal_robot.x,
    y=route_subgoal_robot.y,
    confidence=route_confidence,
    route_id=route.route_id,
    waypoint_id=next_waypoint.waypoint_id,
    timestamp=now,
)
```

## 7. 坐标系统

系统保留原导航基座的局部坐标约定：

- `x`：机器人前方
- `y`：机器人左侧
- `z`：向上
- `angular_z`：左转为正

地图层内部可以维护短期 `map` 坐标，但输出给导航基座之前必须转换到 `base_link` 局部坐标。

```text
LingBot world/map point
        ↓ camera/map pose
point in current camera frame
        ↓ camera extrinsics
point in robot base_link
        ↓ projection
angle-distance scan
```

长距离模式下通常需要一个已有地图坐标系，例如 `map`。本系统不要求 ROS TF，但必须有等价的坐标变换服务：

```text
map <-> robot base_link
map <-> camera / LingBot local map
```

如果没有可靠定位，长距离路径规划无法闭环。此时 LingBot-Map 的视觉局部坐标只能用于短期局部避障和语义确认，不能单独承担长距离路径跟踪。

## 8. 几何地图到 ObstacleScan

地图适配器把 LingBot-Map 输出的深度或点云转换为 `ObstacleScan`。

### 8.1 输入

可选输入：

- per-frame depth
- world_points
- camera extrinsic / intrinsic
- confidence map
- sky mask
- segmentation mask

### 8.2 处理流程

```text
1. 读取当前帧对应的 3D 点
2. 转换到机器人 base_link 坐标
3. 过滤无效点、低置信度点、天空点
4. 过滤地面和过高点
5. 保留机器人高度范围内的障碍点
6. 计算 angle = atan2(y, x)
7. 计算 raw_distance = hypot(x, y)
8. 按角度 bin 聚合
9. 每个 bin 取较近分位数，例如 20% quantile
10. 扣除 footprint_radius
11. 输出 ObstacleScan
```

### 8.3 高度过滤

推荐第一版：

```text
min_obstacle_height = 0.05 m
max_obstacle_height = robot.height
```

若地面估计不稳定，优先使用相机安装高度和近似水平面做保守过滤。

### 8.4 距离语义

输出 `ObstacleScan.distances` 必须表示：

```text
机器人边缘到障碍的有效距离
```

即：

```text
effective_distance = max(0, raw_distance - robot.footprint_radius)
```

这与原导航基座的安全距离语义一致。

## 9. CLIP 语义地图

语义地图保存“物体候选 + 3D 位置 + embedding”。

### 9.1 语义对象创建

每个候选区域：

```text
region crop / mask
        ↓
CLIP image embedding
        ↓
区域内 3D 点提取
        ↓
去除离群点
        ↓
估计 object center
        ↓
创建或更新 SemanticObject
```

区域 3D 点提取方式：

- 若有 mask：取 mask 内有效 3D 点
- 若只有 bbox：取 bbox 中心 30%-60% 区域，降低背景污染
- 若点太少：拒绝该 region

位置估计推荐使用中位数：

```text
object_center = median(valid_points_xyz)
```

### 9.2 语义对象关联

新 observation 与已有对象匹配：

```text
spatial_dist = distance(new_center, old_center)
semantic_sim = cosine(new_embedding, old_embedding)

match if:
    spatial_dist < object_association_distance
    and semantic_sim > object_association_similarity
```

若匹配，更新：

```text
embedding = normalize(alpha * old_embedding + (1 - alpha) * new_embedding)
position  = beta * old_position + (1 - beta) * new_position
observations += 1
last_seen_time = now
```

若不匹配，创建新对象。

### 9.3 文本目标查询

用户输入：

```text
"go to the red chair"
```

处理：

```text
1. 提取 text query
2. CLIP text encoder -> text_embedding
3. 对每个 SemanticObject 计算 cosine similarity
4. 结合几何可达性和时效性评分
5. 选择最佳 SemanticGoal
```

推荐总评分：

```text
score = w_semantic * clip_similarity
      + w_recency   * recency_score
      + w_distance  * distance_score
      + w_stability * observation_score
      - w_blocked   * blocked_penalty
```

其中：

```text
recency_score     = exp(-(now - last_seen_time) / semantic_stale_time)
distance_score    = clamp(1 - distance / max_goal_distance, 0, 1)
observation_score = clamp(observations / min_confirm_observations, 0, 1)
```

## 10. 长距离路径执行策略

已有 planner 输出全局路径后，由 Route Manager 把长路径切成局部子目标。

```text
GlobalRoute
    ↓
选择机器人前方 lookahead_distance 处的路径点
    ↓
转换到 base_link 坐标
    ↓
LocalSubgoal
    ↓
ReactiveNavigator
```

推荐参数：

```text
lookahead_distance = 0.8 - 2.0 m
corridor_width     = 0.6 - 1.5 m
replan_block_time  = 2.0 - 5.0 s
```

### 10.1 路径跟随输入

反应式导航器不直接追最终目标，而是追局部子目标：

```text
target_angle = atan2(local_subgoal.y, local_subgoal.x)
target_dist  = hypot(local_subgoal.x, local_subgoal.y)
```

### 10.2 局部绕障与全局重规划

短时间障碍：

```text
ReactiveNavigator 使用边缘跟随绕过
```

长时间阻塞：

```text
blocked_duration > replan_block_time
        ↓
向 Global Planner 上报 blocked corridor
        ↓
请求重规划
```

### 10.3 语义目标与路径目标关系

CLIP 查询得到的语义目标有三种用途：

1. **目标解析**：用户说“去红色椅子”，系统在语义地图或已有地图 POI 中找到对应 map goal
2. **路径确认**：到达某个 waypoint 时，用 CLIP 确认门牌、物体、房间入口等语义标志
3. **局部纠偏**：全局路径到达目标附近后，用 LingBot-Map + CLIP 找到实际物体位置，生成最后 1-3 米的 `LocalSubgoal`

## 11. 语义目标接近策略

最佳语义对象被选中后，不直接作为最终导航目标撞向物体中心，而是生成一个安全接近点。该接近点可以作为路径末端的 `LocalSubgoal`，或反馈给全局 planner 作为最后一段目标。

```text
SemanticObject.position_robot = (x, y, z)
        ↓
ApproachPoint(x, y)
        ↓
LocalSubgoal(x, y, confidence, route_id, waypoint_id, timestamp)
```

目标点不要设在物体中心，尤其是椅子、箱子、墙面、充电桩这类实体。应生成一个**接近点**：

```text
approach_distance = object.radius + robot.inscribed_radius + goal_margin
```

若目标在机器人前方：

```text
direction = normalize([object.x, object.y])
goal_xy = object_xy - direction * approach_distance
```

如果目标太近：

```text
target_dist < goal_tolerance -> GOAL_REACHED
```

## 12. 探索与地图保存

探索模式用于“目标区域未知、已有地图不完整、或需要持续扩展地图”的长距离任务。它不是绕开 planner 的自由游走，而是由 Exploration Planner 生成可执行探索目标，再经过 Route Manager 和 ReactiveNavigator 安全执行。

### 12.1 探索模式触发条件

任一条件满足即可进入探索：

- 用户显式下发探索命令，例如“探索这一层”、“继续建图”、“寻找椅子”
- 全局 planner 无法到达目标，但地图中存在未知边界
- 目标语义不存在于已知地图，需要语义搜索
- 当前 route 被阻塞且 planner 无法给出替代路径
- 地图覆盖率低于任务要求

探索模式结束条件：

- 找到满足语义查询的目标
- 达到指定覆盖率
- 无可达 frontier
- 探索时间或距离达到上限
- 电量、安全状态、通信状态要求返回

### 12.2 Frontier 探索

Frontier 是已知可通行区域与未知区域的边界。探索目标应选在 frontier 前的安全可达位置，而不是直接选未知区域内部。

```text
Persistent Map
    ↓
提取 known-free 与 unknown 的边界
    ↓
生成 Frontier Candidates
    ↓
按信息增益、距离、安全性、语义价值评分
    ↓
ExplorationTarget
    ↓
Planner 生成 ExploreRoute
    ↓
Route Manager 生成 LocalSubgoal
```

推荐评分：

```text
score = w_gain     * information_gain
      + w_semantic * semantic_interest
      + w_route    * route_feasibility
      - w_dist     * route_distance
      - w_risk     * local_risk
```

其中：

- `information_gain`：从候选视角预计能看到的未知区域面积
- `semantic_interest`：该方向是否可能包含用户查询目标或地图缺失对象
- `route_feasibility`：已有 planner 是否能安全到达候选点附近
- `local_risk`：窄通道、动态障碍、低置信度几何的惩罚

### 12.3 语义探索

语义探索用于“寻找某类目标”：

```text
Text Query: "find a red chair"
        ↓
CLIP text embedding
        ↓
已知 SemanticObject 检索
        ↓
若找到高置信对象：导航到对象附近
        ↓
若未找到：选择语义价值最高的 frontier 继续探索
```

语义价值可以来自：

- 历史地图中相似物体常出现的位置
- 房间类型或区域标签
- 当前视野中低置信但可能相关的候选区域
- 用户任务的语义先验，例如“充电桩通常在墙边”

CLIP 只负责语义搜索和确认，不负责判定可通行性。

### 12.4 边探索边保存地图

地图保存采用增量写入，而不是任务结束后一次性保存。

每次 LingBot-Map 或传感器更新后生成 `MapUpdate`：

```text
MapFrame + ObstacleScan + SemanticObject
        ↓
Map Fusion
        ↓
MapUpdate
        ↓
Persistent Map Store
```

建议保存四类数据：

```text
metric_map:
  占据栅格 / TSDF / 点云 / 可通行区域

semantic_map:
  SemanticObject、CLIP embedding、标签、观测次数、最后观测时间

route_graph:
  已探索拓扑节点、可通行边、阻塞边、frontier 目标

raw_index:
  关键帧图像、LingBot-Map predictions、相机位姿、调试日志索引
```

持久化策略：

- `map_update_interval`：按时间周期写入，例如 0.5-2.0 s
- `keyframe_save_interval`：按关键帧或路程保存原始观测
- `snapshot_interval`：按较低频率生成完整快照，例如 30-120 s
- `atomic_write`：先写临时文件，再原子替换 manifest
- `versioned_manifest`：每次快照递增版本，便于回滚

### 12.5 地图融合策略

几何融合：

```text
occupied_points -> occupied probability increase
free_space_rays -> free probability increase
dynamic_obstacle -> short-term layer only
low_confidence_points -> lower weight
```

语义融合：

```text
same object association:
    spatial distance close
    semantic embedding similar
    observation time consistent

object update:
    position smoothing
    embedding moving average
    confidence / observation count update
```

地图分层：

```text
static_metric_layer:
    墙、门、固定家具、长期障碍

dynamic_obstacle_layer:
    人、临时箱子、移动物体

semantic_layer:
    物体、房间标志、门牌、任务目标

frontier_layer:
    未知边界、探索候选点、已访问/失败 frontier
```

### 12.6 探索中的安全规则

探索目标必须经过 planner 和 ReactiveNavigator 双重约束：

- 不向 unknown 直接高速前进
- frontier 目标前必须有可停靠的 known-free 区域
- `ObstacleScan` 超时立即停车
- LingBot-Map 地图漂移过大时暂停探索并请求重定位
- 探索 route 连续失败时标记 frontier 为 failed，避免反复尝试
- 动态障碍只写入短期层，不应永久污染静态地图

### 12.7 探索输出

探索模块输出：

```text
ExplorationTarget
ExploreRoute
LocalSubgoal
MapUpdate
SavedMapManifest
```

其中只有 `LocalSubgoal + ObstacleScan` 会进入 ReactiveNavigator。地图保存和探索目标选择都不能直接输出底盘速度。

## 13. 动态运行模式

### 13.1 离线回放模式

用于第一阶段验证。

```text
video/images
    ↓
LingBot-Map offline inference
    ↓
saved predictions
    ↓
CLIP region embedding
    ↓
SemanticMap replay
    ↓
GlobalRoute / ExploreRoute replay + ObstacleScan + LocalSubgoal
    ↓
ReactiveNavigator
    ↓
MapUpdate replay save
```

优点：

- 调试简单
- 不依赖实时 GPU 性能
- 可重复运行同一场景
- 适合做验收测试

### 13.2 半实时模式

LingBot-Map 每 N 帧更新一次几何地图，CLIP 每 M 帧更新一次语义对象。

```text
camera: 20-30 Hz
navigator: 20 Hz
obstacle scan adapter: 10-20 Hz
LingBot-Map: 2-10 Hz or streaming
CLIP: 1-5 Hz
```

导航器永远使用最新可用 `ObstacleScan`。若地图层超时，进入安全策略。

### 13.3 实时闭环模式

用于最终集成。

```text
global planner route / exploration target
    ↓
camera frame
    ↓
LingBot-Map streaming update
    ↓
CLIP semantic update
    ↓
rolling local semantic map
    ↓
Map Fusion saves incremental updates
    ↓
Planner / Exploration Planner selects route
    ↓
Route Manager selects LocalSubgoal
    ↓
ReactiveNavigator
    ↓
chassis command
```

实时闭环必须加入：

- 输入帧队列
- 推理延迟补偿
- 最新帧丢弃策略
- 地图时间戳
- 障碍数据超时急停
- CLIP 目标超时降级
- 探索地图增量保存失败报警
- snapshot 与 manifest 版本管理

## 14. 安全策略

CLIP 只用于目标选择，不用于安全判断。

必须满足：

- `qwen3-vl:4b` 大脑只能输出结构化任务决策，不能输出或执行底盘速度
- 没有几何障碍数据时，不允许前进
- CLIP 找到目标但几何方向不安全时，进入避障或边缘跟随
- CLIP 相似度高但目标 3D 位置不稳定时，不生成有效 `LocalSubgoal`
- 目标 semantic confidence 低时，进入 `LOST_TARGET` 或搜索
- LingBot-Map 输出低置信度点云时，障碍扫描按保守策略处理
- 地图层时间戳超时，导航器进入急停或停车搜索
- 探索目标位于 unknown 内部时，不直接执行，必须退到 known-free 边界附近
- 地图保存失败时允许短时继续运行，但必须报警；连续失败超过阈值则暂停探索
- 重定位失败或地图漂移超过阈值时，暂停写入长期静态地图
- 大脑输出解析失败、置信度过低或越权字段时，按 `fallback_on_error` 执行

安全优先级：

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

## 15. 配置文件

示例：

```yaml
brain:
  enabled: true
  model: qwen3-vl:4b
  role: task_brain
  runtime: ollama              # ollama | openai_compatible | custom_http
  endpoint: http://localhost:11434
  request_timeout: 8.0
  max_retries: 1
  decision_schema: BrainDecision
  allowed_intents:
    - navigate
    - explore
    - semantic_search
    - inspect
    - return_home
    - pause
    - stop
    - ask_user
  require_json_output: true
  max_context_images: 1
  map_summary_max_objects: 30
  frontier_summary_max_items: 10
  fallback_on_error: pause
  allow_direct_velocity_command: false

global_planner:
  enabled: true
  map_frame: map
  route_source: existing_planner
  corridor_width: 1.0
  replan_block_time: 3.0
  replan_on_semantic_mismatch: true

route_manager:
  lookahead_distance: 1.2
  waypoint_reached_distance: 0.35
  max_cross_track_error: 0.8
  local_subgoal_timeout: 0.5
  final_semantic_refine_distance: 3.0

exploration:
  enabled: true
  mode: frontier             # frontier | coverage | semantic_search
  allow_unknown_goal: false  # frontier 目标必须落在 known-free 安全停靠区
  max_explore_time: 1800.0
  max_explore_distance: 500.0
  min_frontier_size: 0.5
  frontier_standoff_distance: 0.6
  frontier_revisit_cooldown: 60.0
  failed_frontier_retry_limit: 2
  coverage_target_ratio: 0.90
  semantic_search_query: null
  w_gain: 0.40
  w_semantic: 0.20
  w_route: 0.20
  w_dist: 0.10
  w_risk: 0.10

map_persistence:
  enabled: true
  map_id: default_site_map
  storage_dir: ./maps/default_site_map
  metric_map_format: occupancy_grid   # occupancy_grid | tsdf | pointcloud
  semantic_db_format: sqlite          # sqlite | parquet | jsonl
  map_update_interval: 1.0
  keyframe_save_interval: 2.0
  snapshot_interval: 60.0
  atomic_write: true
  keep_last_snapshots: 10
  save_raw_keyframes: true
  pause_exploration_on_save_errors: true

semantic_map:
  enabled: true
  mode: offline_replay       # offline_replay | semi_realtime | realtime
  max_goal_distance: 6.0
  semantic_stale_time: 3.0
  object_stale_time: 10.0
  min_confirm_observations: 2

lingbot_map:
  repo_path: /path/to/lingbot-map
  model_path: /path/to/lingbot-map-long.pt
  input_mode: image_folder   # image_folder | video_path | stream
  mode: streaming            # streaming | windowed
  image_size: 518
  keyframe_interval: 2
  window_size: 128
  overlap_keyframes: 16
  use_sdpa: false
  mask_sky: true
  conf_threshold: 1.5
  downsample_factor: 10
  save_predictions: true

clip:
  model_name: ViT-B-32
  backend: open_clip         # open_clip | transformers
  device: cuda
  normalize_embeddings: true
  min_similarity: 0.24
  object_association_similarity: 0.70
  text_prompt_templates:
    - "a photo of a {}"
    - "a robot navigation target: {}"

region_proposal:
  source: detector           # detector | segmenter | manual_roi | sliding_window
  detector_model: yolov8
  min_region_area: 400
  max_regions_per_frame: 20
  center_crop_ratio: 0.6

geometry_adapter:
  scan_angle_min: -1.57
  scan_angle_max: 1.57
  scan_bins: 181
  distance_quantile: 0.20
  min_range: 0.05
  max_range: 6.0
  min_obstacle_height: 0.05
  max_obstacle_height: 0.50
  min_points_per_bin: 3
  apply_footprint_inflation: true

goal_selection:
  w_semantic: 0.55
  w_recency: 0.15
  w_distance: 0.15
  w_stability: 0.15
  w_blocked: 0.20
  approach_margin: 0.15
  min_goal_confidence: 0.55
```

## 16. 建议工程目录

```text
navigation_core/
  types.py
  reactive_navigator.py
  scan_utils.py
  transform_service.py
  config.py

brain/
  qwen3_vl_client.py
  brain_context_builder.py
  brain_decision_schema.py
  brain_orchestrator.py

semantic_map/
  lingbot_runner.py
  lingbot_prediction_reader.py
  geometry_adapter.py
  clip_encoder.py
  region_proposal.py
  semantic_memory.py
  goal_selector.py
  map_types.py

global_navigation/
  planner_client.py
  simple_planner.py
  mock_planner.py
  route_manager.py
  route_types.py
  replan_feedback.py

exploration/
  frontier_detector.py
  exploration_planner.py
  exploration_state.py
  coverage_tracker.py

map_store/
  persistent_map.py
  map_fusion.py
  snapshot_manager.py
  semantic_db.py

replay/
  run_offline_semantic_replay.py
  run_route_replay.py
  run_exploration_replay.py
  run_scan_replay.py

sim/
  sim2d_world.py
  webots_bridge.py

tests/
  test_geometry_adapter.py
  test_semantic_goal_selection.py
  test_frontier_exploration.py
  test_map_persistence.py
  test_navigation_with_semantic_map.py
  test_transform_service.py
```

## 17. 仿真方案

### 17.1 第一阶段：已有地图路径回放

目的：验证长距离路径切分和局部执行。

输入：

- `GlobalRoute`
- `LocalSubgoal`
- `ObstacleScan`

验证：

- 路径点追踪
- 路径走廊偏差
- 局部障碍绕行
- 长时间阻塞后重规划请求
- 到达最终目标附近后进入语义精修

### 17.2 第二阶段：LingBot-Map 离线地图回放

目的：验证地图适配器。

```text
录制视频
    ↓
LingBot-Map
    ↓
predictions
    ↓
geometry_adapter
    ↓
ObstacleScan
```

同时用人工 ROI 或检测框生成 CLIP 语义目标。

### 17.3 第三阶段：语义目标回放

目的：验证 CLIP 查询。

流程：

```text
文本目标 "red chair"
    ↓
CLIP text embedding
    ↓
semantic_memory search
    ↓
SemanticGoal
    ↓
Route Goal / LocalSubgoal
```

验证：

- 多个相似目标时选择正确目标
- 目标短暂消失后保持稳定
- 低置信度目标不触发移动

### 17.4 第四阶段：长距离闭环仿真

推荐 Webots 作为第一版 3D 闭环仿真：

- 非 ROS2
- 有相机、深度相机、雷达、差速底盘
- Python 控制容易
- 能直接验证 `VelocityCommand`

闭环：

```text
Existing map planner
    ↓
GlobalRoute
    ↓
Webots camera
    ↓
LingBot-Map + CLIP
    ↓
ObstacleScan + LocalSubgoal
    ↓
ReactiveNavigator
    ↓
Webots differential drive
```

### 17.5 第五阶段：探索建图闭环仿真

目的：验证边探索边保存地图。

闭环：

```text
Seed Map / Empty Local Map
    ↓
Exploration Planner
    ↓
ExploreRoute
    ↓
Webots camera / depth / lidar
    ↓
LingBot-Map + CLIP
    ↓
MapUpdate 持久化保存
    ↓
Frontier 更新
    ↓
继续探索或结束
```

验证：

- frontier 能持续生成并被访问
- 已探索区域覆盖率持续上升
- map snapshot 能中途恢复
- failed frontier 不会反复尝试
- 动态障碍不会永久写入静态地图

## 18. 开发里程碑

### M0：Qwen3-VL 大脑接口

完成：

- `qwen3-vl:4b` 本地或 HTTP 调用
- `BrainObservation` 上下文摘要构建
- `BrainDecision` JSON schema 校验
- intent 白名单和安全 fallback

验收：

- 用户说“继续探索”时输出 `intent=explore`
- 用户说“找红色椅子”时输出 `intent=semantic_search` 和 `target_query`
- 大脑输出非法字段时被拒绝，不影响安全停车

### M1：离线几何适配

完成：

- 读取 LingBot-Map prediction
- 输出 `ObstacleScan`
- 可视化 scan
- 与导航基座跑通

验收：

- 障碍在前方时 `front_distance` 正确降低
- 障碍侧向位置对应正确角度
- footprint 膨胀正确

### M2：CLIP 语义目标

完成：

- 文本 embedding
- 图像 crop embedding
- 语义对象记忆
- 文本查询到 `SemanticGoal`

验收：

- 输入 `"chair"` 能选中椅子区域
- 输入 `"box"` 能选中箱子区域
- 相似度低于阈值时不输出目标

### M3：全局路径与局部导航融合

完成：

- `GlobalRoute -> LocalSubgoal`
- `ObstacleScan + LocalSubgoal -> VelocityCommand`
- 局部阻塞反馈到全局 planner
- 路径末端接入 `SemanticGoal` 精修

验收：

- 机器人沿全局路径前进
- 局部障碍短时出现时绕行
- 长时间阻塞时请求重规划
- 进入目标附近后由 CLIP 确认最终目标

### M4：半实时演示

完成：

- 相机或视频流输入
- 地图层异步更新
- 导航器固定频率运行
- 简单 Web UI 可视化

验收：

- UI 显示当前文本目标、候选对象、scan、导航状态
- 地图层超时时，导航器停车
- 语义目标更新不会引起速度大跳变

### M5：探索建图与持久化

完成：

- Frontier 检测
- ExplorationTarget 评分
- ExploreRoute 生成
- MapUpdate 增量写入
- Snapshot / manifest 版本保存
- 从已保存地图恢复继续探索

验收：

- 探索过程中地图文件持续更新
- 程序中断后可从最近 snapshot 恢复
- 新探索区域会加入 metric map 和 semantic map
- 探索失败区域被标记，不会短时间重复尝试
- 保存失败会触发报警或暂停探索

## 19. 验收测试用例

| 编号 | 场景 | 通过条件 |
| --- | --- | --- |
| BRAIN-1 | 用户输入“继续探索并保存地图” | `qwen3-vl:4b` 输出合法 `BrainDecision(intent=explore)` |
| BRAIN-2 | 用户输入“找红色椅子” | 输出 `intent=semantic_search`，并生成 `target_query="red chair"` 或等价查询 |
| BRAIN-3 | 大脑输出非法 intent | schema 校验拒绝，系统进入 pause 或 stop fallback |
| BRAIN-4 | 大脑请求直接控制速度 | 越权字段被拒绝，不生成 `VelocityCommand` |
| SMT-1 | 已有 planner 输出一条长距离路线 | Route Manager 正确生成连续 `LocalSubgoal` |
| SMT-2 | 路径上出现短时障碍 | ReactiveNavigator 局部绕行，不立即重规划 |
| SMT-3 | 路径走廊被长时间阻塞 | 上报 blocked corridor 并请求全局重规划 |
| SMT-4 | 视频中有单个目标物体 `"chair"` | CLIP 选中正确对象并生成 `SemanticGoal` |
| SMT-5 | 有多个相似物体 | 选择语义分数、距离和稳定性综合最高的目标 |
| SMT-6 | 目标方向有障碍 | `ObstacleScan` 阻止直行，导航进入避障或边缘跟随 |
| SMT-7 | CLIP 高分但无有效 3D 点 | 不生成有效 `LocalSubgoal` |
| SMT-8 | LingBot-Map 点云低置信度 | 对应区域不作为可靠障碍或目标位置 |
| SMT-9 | 地图层 0.5 s 未更新 | 导航器按障碍数据超时策略停车或急停 |
| SMT-10 | 文本目标不存在 | 不输出目标，进入 `LOST_TARGET` 或 IDLE |
| SMT-11 | 目标短暂被遮挡 | 语义对象短时间保留，但 confidence 衰减 |
| SMT-12 | 障碍点 raw distance 0.50 m，footprint 0.25 m | 输出 effective distance 约 0.25 m |
| SMT-13 | 目标在物体中心 | 生成 approach goal，不直接撞向物体中心 |
| EXP-1 | 初始地图存在未知边界 | 生成至少一个安全 frontier `ExplorationTarget` |
| EXP-2 | 探索过程中发现新可通行区域 | `metric_map` 增量更新，frontier 向外推进 |
| EXP-3 | 探索过程中识别到新物体 | `semantic_map` 保存对应 `SemanticObject` 和 embedding |
| EXP-4 | 机器人访问 frontier 后无新增信息 | 将该 frontier 标记为 visited 或 low_gain |
| EXP-5 | 探索 route 连续失败 | frontier 标记为 failed，并在 cooldown 内不再选择 |
| EXP-6 | 程序中途退出 | 能从最近 snapshot 和 manifest 恢复地图 |
| EXP-7 | 地图保存连续失败 | 系统报警并暂停探索，不继续扩大未知区域 |
| EXP-8 | 动态障碍临时出现 | 写入 dynamic layer，不污染 static metric layer |

## 20. 关键风险

### 20.1 尺度漂移

LingBot-Map 视觉重建可能存在尺度误差。若用于真实机器人安全避障，必须用以下方式校准或兜底：

- RGB-D 相机真实深度
- 2D 雷达
- 已知相机高度和地面约束
- 已知物体尺寸
- AprilTag / 标定板

第一版真实底盘测试不建议只依赖单目重建距离。

### 20.2 语义误识别

CLIP 只输出语义相似度，不能保证目标正确。需要：

- 多帧投票
- 最小观测次数
- 相似度阈值
- 人工确认模式
- UI 显示候选目标

### 20.3 延迟

LingBot-Map 和 CLIP 都可能引入推理延迟。控制器需要：

- 时间戳检查
- 超时停车
- 只使用最新地图快照
- 必要时丢弃旧帧

### 20.4 动态障碍

视觉地图可能滞后于动态物体。真实机器人建议保留独立近距传感器：

- 2D LiDAR
- 深度相机即时 depth
- 超声 / ToF
- 碰撞条或急停按钮

### 20.5 地图一致性与保存损坏

边探索边保存时，最大风险是把错误定位、动态障碍或半写入文件固化进长期地图。必须加入：

- manifest 版本号
- atomic write
- snapshot 回滚
- 动态层和静态层分离
- 低置信地图更新延迟提交
- 重定位失败时暂停长期地图写入

## 21. 硬件与资源需求

### 21.1 开发与仿真环境（L0-L4）

```text
CPU: 8 核以上
RAM: 16 GB 以上
GPU: 可选（L0-L2 不需要 GPU）
存储: 50 GB 可用空间（地图快照、prediction 缓存、测试证据包）
```

### 21.2 语义几何回放与大脑（L3 及以上）

```text
GPU: NVIDIA GPU，VRAM >= 8 GB（推荐 RTX 3060 / RTX 4060 或更高）
  - qwen3-vl:4b（Ollama）：约 4-6 GB VRAM
  - CLIP ViT-B-32：约 0.5 GB VRAM
  - LingBot-Map 推理：约 2-4 GB VRAM
RAM: 32 GB 推荐（多模型并发时内存压力较大）
```

### 21.3 多模型并发策略

三个模型（qwen3-vl、CLIP、LingBot-Map）不建议在单 GPU 上同时加载。推荐策略：

```text
方案 A（单 GPU >= 12 GB VRAM）：
  分时复用，按需加载/卸载模型
  大脑低频调用（每次任务决策），CLIP 中频（1-5 Hz），LingBot-Map 高频（2-10 Hz）
  优先常驻 LingBot-Map 和 CLIP，大脑按需加载

方案 B（双 GPU 或 GPU + CPU）：
  GPU 0: LingBot-Map + CLIP
  GPU 1 / CPU: qwen3-vl:4b

方案 C（开发阶段）：
  L0-L2 不需要 GPU
  L3 使用离线 prediction + embedding cache，无需实时推理
  仅 L5 / 半实时演示需要全部模型在线
```

### 21.4 Webots 3D 仿真（L5）

```text
GPU: 支持 OpenGL 3.3 以上
显示器: 推荐，headless 模式可用但调试不便
Webots 版本: R2023b 或更新
```

## 22. 第一版最小可行系统

最小系统只做离线长距离与探索回放，不上底盘。（对应里程碑 M0-M2 + 部分 M3/M5，仿真层 L0-L3。）

```text
1. 准备一张初始地图或空白局部地图
2. 接入 `qwen3-vl:4b`，把用户指令转换成 `BrainDecision`
3. 准备一条已有地图 planner 生成的 GlobalRoute，或一个 Explore Request
4. 用 LingBot-Map 跑一段路线/探索视频
5. 保存 prediction
6. 根据 `BrainDecision` 生成文本查询，例如 "chair" 或目标地图点
7. 对每帧候选区域计算 CLIP embedding
8. 建立 SemanticObject 列表
9. 从 prediction 生成 ObstacleScan
10. Route Manager 从 GlobalRoute / ExploreRoute 生成 LocalSubgoal
11. Exploration Planner 生成 frontier 目标
12. Map Fusion 写入 metric_map、semantic_map、route_graph
13. 目标附近用 SemanticObject 做最后语义确认或纠偏
14. 调用 ReactiveNavigator
15. 输出每帧状态、速度、路线进度、探索进度、保存版本、目标、障碍图
```

最小交付物：

```text
brain/qwen3_vl_client.py
brain/brain_context_builder.py
brain/brain_decision_schema.py
semantic_map/geometry_adapter.py
semantic_map/clip_encoder.py
semantic_map/semantic_memory.py
semantic_map/goal_selector.py
global_navigation/route_manager.py
global_navigation/replan_feedback.py
exploration/frontier_detector.py
exploration/exploration_planner.py
map_store/persistent_map.py
map_store/snapshot_manager.py
replay/run_offline_semantic_replay.py
replay/run_route_replay.py
replay/run_exploration_replay.py
```

## 23. 结论

在长距离导航和探索建图系统中，LingBot-Map + CLIP Embedding 应作为**已有地图路径规划之上的语义几何增强层**和**探索地图更新层**，而不是完整导航系统。

最终系统分工：

```text
Qwen3-VL 4B Brain:
    使用 qwen3-vl:4b 理解任务、选择模式、生成结构化 BrainDecision

Existing Global Map + Planner:
    负责长距离路径规划、重规划和接收地图增量

LingBot-Map:
    构建局部 3D 几何，提供障碍、局部结构和目标空间位置

CLIP:
    将文字目标、地图语义和图像区域做语义匹配

Semantic Map Adapter:
    输出 ObstacleScan、SemanticGoal、路径语义确认

Exploration Planner:
    从未知边界生成探索目标，并请求 planner 生成 ExploreRoute

Persistent Map Store:
    持续保存 metric map、semantic map、route graph 和 snapshot

Route Manager:
    将 GlobalRoute / ExploreRoute 转换为 LocalSubgoal，并把阻塞反馈给 planner

ReactiveNavigator:
    基于 LocalSubgoal + ObstacleScan 做安全运动控制
```

一句话：

```text
qwen3-vl:4b 负责“用户到底想做什么”，已有 planner 负责“长距离怎么走”，探索模块负责“下一块未知区域去哪看”，LingBot-Map 负责“局部真实几何是什么”，CLIP 负责“语义目标是不是对的”，地图存储负责“把看到的保存下来”，导航基座负责“这一小段怎么安全走过去”。
```
