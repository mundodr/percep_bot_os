# 非 ROS2 反应式视觉导航与避障系统设计文档

## 1. 目标

设计一个不依赖 ROS2、Nav2、TF、Odom、全局地图的独立导航系统。

系统职责：

- 视觉持续更新目标相对位置
- 雷达或深度相机感知局部障碍
- 导航控制器实时计算速度
- 底盘执行速度指令
- 机器人朝可见目标移动并避障

系统不关心：

- 机器人在世界坐标中的位置
- 机器人历史轨迹
- 全局路径
- 地图定位
- 里程计

只关心：

- 目标现在相对机器人在哪里
- 障碍现在相对机器人在哪里
- 当前应该往哪个方向走

## 2. 总体架构

```text
RGB-D Camera / RGB Camera / Target Detector
        ↓
Vision Target Module
        ↓
LocalGoal(x, y, confidence, timestamp)

LiDAR / Depth Camera
        ↓
Obstacle Perception Module
        ↓
ObstacleScan(angles, distances, timestamp)

        ↓
ReactiveNavigator
        ↓
VelocityCommand(linear_x, angular_z)
        ↓
Chassis Driver
Serial / CAN / TCP / Vendor SDK
```

系统由四个核心模块组成：

- **Vision Target Module**：目标检测与相对位置估计
- **Obstacle Perception**：局部障碍距离感知
- **ReactiveNavigator**：避障与速度控制
- **Chassis Driver**：底盘通信与速度下发

## 3. 坐标约定

系统使用机器人自身**局部坐标**，不使用全局坐标。约定为右手系：

- `x` 轴：机器人正前方
- `y` 轴：机器人左侧
- `z` 轴：向上（导航控制忽略）
- `angular_z` 正方向：从上方看为逆时针，即"左转为正"

目标点表示：

- `goal.x`：目标前方距离，单位 m
- `goal.y`：目标左右偏移，**左正右负**，单位 m

示例：`goal.x = 2.0, goal.y = -0.3` 表示目标在机器人前方 2 米、右侧 0.3 米。

### 3.1 机器人尺寸与传感器外参

`base_link` 位于机器人**几何中心**（俯视投影矩形或圆的中心），所有传感器读数和速度命令都以此为参考点。

机器人 footprint 表示：

- 矩形机器人：`length` × `width`（x 方向 × y 方向）
- 圆形机器人：`radius`
- **内接圆半径** `inscribed_radius = min(length, width) / 2`
- **外接圆半径** `circumscribed_radius = sqrt((length/2)^2 + (width/2)^2)`（圆形机器人即 `radius`）
- **footprint 膨胀半径** `footprint_radius`：用于把传感器原始距离换算为"边缘到障碍"的有效距离，第一版推荐取 `circumscribed_radius`（保守、各向同性）

**核心约定**：本文档第 7、8 节中所有以"距离"出现的安全/控制阈值（`safety_distance`、`emergency_stop_distance`、`slowdown_distance`、`edge.follow_distance` 等），度量的都是**机器人边缘到障碍**的"有效距离"，而非传感器读数。Obstacle Perception 模块负责在输出 `ObstacleScan` 之前做膨胀（见第 6 节）：

```text
effective_distance(angle) = max(0, raw_distance(angle) - footprint_radius)
```

如此一来，配置参数和实际安全裕度直接对应，调参不再依赖机器人尺寸。

传感器外参：

- 雷达 / 深度相机的安装位置和朝向都相对 `base_link` 标定
- 若传感器有平移偏移 `(dx, dy)`，Obstacle Perception 应先把扫描点从传感器系变换到 `base_link` 系再输出
- 若偏移很小（< 5 cm）可忽略，但必须在文档/代码中明示

## 4. 核心数据结构

```python
import math
from dataclasses import dataclass, field
from typing import Sequence

@dataclass
class LocalGoal:
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
    angles: Sequence[float]      # 单位 rad，单调递增
    distances: Sequence[float]   # 单位 m，无效值统一为 math.inf
    timestamp: float

@dataclass
class VelocityCommand:
    linear_x: float    # m/s
    angular_z: float   # rad/s

@dataclass
class RobotFootprint:
    shape: str = "rectangle"            # "rectangle" | "circle"
    length: float = 0.40                # x 方向长度 (m)
    width: float = 0.30                 # y 方向宽度 (m)
    height: float = 0.50                # z 方向高度 (m)
    radius: float = 0.0                 # 圆形机器人半径 (m)，rectangle 时填 0

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
class SensorExtrinsics:
    lidar_offset_x: float = 0.0         # 雷达相对 base_link 的前后偏移 (m)
    lidar_offset_y: float = 0.0
    lidar_offset_yaw: float = 0.0       # rad
    camera_offset_x: float = 0.0
    camera_offset_y: float = 0.0
    camera_offset_z: float = 0.0
    camera_R_cam_to_robot: tuple = ()   # 3x3 旋转矩阵，空表示默认水平正前方

@dataclass
class EdgeFollowContext:
    active: bool = False
    bypass_side: str = "left"            # 机器人绕行方向 "left" | "right"
    obstacle_side: str = "right"         # 障碍所在侧，与 bypass_side 相反
    start_time: float = 0.0
    last_seen_obstacle_distance: float = math.inf
    last_progress_time: float = 0.0      # 上次 target_angle 有改善的时间

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

`LocalGoal` 与 `LocalSubgoal` 的关系：

- `LocalGoal` 是纯局部导航的最小目标接口，适用于无全局路径的简单场景
- `LocalSubgoal` 是长距离导航和探索模式下的扩展目标，包含路径和来源追踪信息
- `ReactiveNavigator` 只依赖 `x, y, confidence, timestamp` 四个字段，因此同时兼容两种输入
- 当系统接入全局路径规划或探索模块后，统一使用 `LocalSubgoal` 作为导航器输入

`ObstacleScan` 约束：

- `len(angles) == len(distances)`
- `angles` 单调递增
- 无效或超量程的距离统一记为 `math.inf`，禁止混用 `0` / `nan`

约定的辅助函数（实现细节由 ObstacleScan 持有或独立工具函数）：

```python
def distance_in_sector(scan: ObstacleScan, a_min: float, a_max: float,
                       quantile: float = 0.2) -> float:
    """返回扇区 [a_min, a_max] 内的代表距离（默认 20% 分位数）。
    若扇区内无有效采样，返回 math.inf。"""
```

`bypass_side` 与 `obstacle_side` 永远相反——`bypass_side="left"` 表示机器人**从障碍左侧绕过**，此时障碍位于机器人**右侧**。

## 5. Vision Target Module

视觉模块负责检测目标，并估计目标相对机器人位置。

使用 RGB-D 相机时：

1. 获取 RGB 图像和深度图
2. 通过检测模型获得目标框
3. 在目标框中心区域（建议中心 30% × 30%）读取深度，取中位数
4. 使用相机内参 `(fx, fy, cx, cy)` 将像素反投影到相机坐标
5. 通过相机外参 `(R_cam→robot, t_cam→robot)` 转换到机器人坐标
6. 输出 `LocalGoal`

像素到相机坐标（OpenCV 标准约定：`x_cam` 右、`y_cam` 下、`z_cam` 前）：

```text
X_cam = (u - cx) * Z / fx
Y_cam = (v - cy) * Z / fy
Z_cam = depth
```

相机坐标到机器人坐标：

```text
[robot.x, robot.y, robot.z]^T = R_cam_to_robot * [X_cam, Y_cam, Z_cam]^T
                                + t_cam_to_robot
```

水平正前方安装、相机光轴与机器人 x 轴重合时，简化为：

```text
robot.x =  Z_cam
robot.y = -X_cam
robot.z = -Y_cam   # 导航忽略

goal.x = robot.x
goal.y = robot.y
```

如相机有俯仰、横滚、偏航或位置偏移，必须使用完整的 `R, t` 标定值，不能直接套用上述简化式。

如果只使用普通 RGB 相机，可通过以下方式估距：

- 已知目标实际尺寸 + bbox 像素尺寸
- AprilTag / ArUco
- 双目相机
- 外部测距传感器（超声、ToF 等）

多目标选择策略（按优先级）：

1. 与上一帧同 ID 的跟踪目标优先（保持稳定）
2. 否则取置信度最高的目标
3. 同等置信度下取 `target_dist` 最小者

视觉模块输出要求：

- 更新频率：10–30 Hz
- `confidence > confidence_threshold` 才认为目标有效
- `timestamp` 用于判断目标是否过期

## 6. Obstacle Perception Module

障碍感知模块负责输出局部"角度→距离"数组。

使用 2D 雷达：

1. 读取每个角度的原始距离
2. 过滤无效值、过近值（< `min_range`）、过远值（> `max_range`），无效值统一替换为 `math.inf`
3. 应用传感器外参：把扫描点从雷达系平移 / 旋转到 `base_link` 系
4. **应用 footprint 膨胀**：`distance = max(0, distance - footprint_radius)`
5. 输出 `ObstacleScan`

使用深度相机：

1. 读取深度图
2. 选取图像中间高度区域（建议范围：从地面起 `0.1 m` 到 `robot.height`，对应的像素带）
3. 按水平视角划分 N 个扇区
4. 每个扇区取较近深度（建议 20% 分位数，鲁棒于稀疏点云）
5. 应用相机外参变换到 `base_link` 系
6. 应用 footprint 膨胀
7. 转换为 `angle → distance`
8. 输出 `ObstacleScan`

输出要求：

- 更新频率：10–20 Hz
- 角度范围：建议覆盖前方 ±90°，雷达可全 360°
- 距离单位：m
- **语义**：所有 `distance[i]` 表示"机器人边缘到障碍的有效距离"，已扣除 footprint。下游导航器无需再考虑机器人尺寸。

## 7. ReactiveNavigator 算法

推荐算法组合：**Follow-the-Gap + 边缘跟随 + 目标方向偏好**。

输入：`LocalGoal`、`ObstacleScan`、`NavigatorState`
输出：`VelocityCommand`、更新后的 `NavigatorState`

### 7.1 关键量

> **距离语义**：`scan` 中的距离已由 Obstacle Perception 扣除 footprint（见 3.1 / 6 节），表示"机器人边缘到障碍的有效距离"。因此第 7、8 节里所有距离阈值均为**纯安全裕度**，与机器人尺寸解耦。

```text
target_angle = atan2(goal.y, goal.x)
target_dist  = sqrt(goal.x^2 + goal.y^2)

front_distance  = distance_in_sector(scan, -front_half_fov, +front_half_fov)
target_dir_dist = distance_at_angle(scan, target_angle)
target_dir_safe = target_dir_dist > safety_distance
```

参数语义：

- `safety_distance`：方向安全的最小裕度（典型 0.30 m）
- `emergency_stop_distance`：触发急停的最小裕度（典型 0.10 m，必须 < `safety_distance`）
- `slowdown_distance`：开始降速的距离（典型 0.60 m）
- `goal_tolerance`：目标到达判定，应 ≥ `inscribed_radius` + 0.05，否则机器人会"撞到"目标

### 7.2 主流程

```text
1. 数据时效检查（goal/scan 是否超时、时间戳偏差是否过大）
2. target_dist < goal_tolerance              -> GOAL_REACHED
3. front_distance < emergency_stop_distance  -> EMERGENCY_STOP
4. goal 已超时或 confidence < threshold      -> LOST_TARGET
5. 当前在 EDGE_FOLLOWING 中：检查退出/失败条件（见 8.4 / 8.5）
6. 否则若 target_dir_safe                    -> TRACKING
7. 否则                                      -> AVOIDING -> EDGE_FOLLOWING
8. 根据当前状态计算 steering_angle 和原始速度
9. 应用速度 / 加速度限幅与平滑（7.5）
10. 输出 VelocityCommand
```

`AVOIDING` 是**单帧瞬态**：仅用于确定 `bypass_side`（见 8.1），完成后同帧立即转入 `EDGE_FOLLOWING`。

### 7.3 选择方向

- **TRACKING**：`steering_angle = target_angle`
- **EDGE_FOLLOWING**：见 8 节
- **EDGE_FOLLOWING 失败**：根据 `edge.fallback` 配置：
  - `stop`（推荐第一版）：停车 + 朝更空一侧低速转向
  - `gap`：退回 Follow-the-Gap，选择最接近 `target_angle` 的安全 gap 中心
- **没有任何安全 gap 且不在边缘跟随**：停车或原地转向

### 7.4 速度控制

角速度：

```text
angular_z = k_turn * steering_angle
angular_z = clamp(angular_z, -max_angular_speed, +max_angular_speed)
```

线速度：

```text
if abs(steering_angle) > π/2:
    linear_x = 0.0      # 目标在身后或大角度侧后方，原地转向
else:
    angle_slowdown    = max(0.2, cos(abs(steering_angle)))
    obstacle_slowdown = clamp(front_distance / slowdown_distance, 0.0, 1.0)
    confidence_factor = clamp(goal.confidence / confidence_threshold, 0.0, 1.0)
    linear_x = max_linear_speed * angle_slowdown
                                * obstacle_slowdown
                                * confidence_factor
    linear_x = clamp(linear_x, min_linear_speed, max_linear_speed)
```

急停输出：

```text
linear_x  = 0
angular_z = sign(更空一侧) * search_angular_speed
```

### 7.5 平滑与限幅

为避免状态切换或 gap 抖动导致速度跳变，对输出做加速度限幅：

```text
dt = now - last_command.timestamp
dv = clamp(target_v - last_v, -max_linear_acc * dt,  +max_linear_acc * dt)
dω = clamp(target_ω - last_ω, -max_angular_acc * dt, +max_angular_acc * dt)

linear_x  = last_v + dv
angular_z = last_ω + dω
```

差速底盘还需做轮速约束（见第 11 节），运动学约束**优先于**这里的限幅。

## 8. 边缘跟随设计

边缘跟随用于"目标方向被障碍挡住，但障碍旁边有通路"的场景。

核心思想：

```text
目标方向被挡住
        ↓
选择从左侧或右侧绕行（bypass_side）
        ↓
保持与障碍边缘的目标距离
        ↓
沿障碍边界向前移动
        ↓
当目标方向重新变安全时，退出边缘跟随
```

**重要约定**（与第 4 节一致）：

- `bypass_side = "left"`  → 机器人从障碍左侧绕过 → 障碍在**右侧** → 监测**右侧**距离
- `bypass_side = "right"` → 机器人从障碍右侧绕过 → 障碍在**左侧** → 监测**左侧**距离

### 8.1 绕行方向选择

进入边缘跟随时固定绕行方向，避免每帧重选导致左右摇摆。

策略（按优先级）：

1. **目标侧偏好**：`goal.y > 0` → 优先左绕；`goal.y < 0` → 优先右绕
2. 若该侧 clearance 不足，则换另一侧
3. 两侧 clearance 都不足 → 直接进入 `EMERGENCY_STOP`

clearance 定义：

```text
left_clearance  = distance_in_sector(scan, +π/4, +π/2)
right_clearance = distance_in_sector(scan, -π/2, -π/4)
```

绕行方向一旦选定，必须保持至少 `edge.min_time`（默认 1.0 s）。

### 8.2 边缘距离控制

让机器人**边缘**和障碍保持稳定距离（已扣除 footprint），推荐 `edge.follow_distance = 0.30 m`，即机器人边缘到障碍 30 cm。

> 老版本文档曾把它写成 0.55 m——那是**含**机器人 footprint 的"中心到障碍"距离。现在所有距离都已扣除 footprint，请使用纯裕度值。

监测的是**障碍所在侧**的距离（与 `bypass_side` 相反）：

```text
if bypass_side == "left":   # 障碍在右
    obstacle_side_distance = distance_in_sector(scan, -π/2, -π/4)
else:                        # 障碍在左
    obstacle_side_distance = distance_in_sector(scan, +π/4, +π/2)

distance_error = edge.follow_distance - obstacle_side_distance
```

转向：

```text
if bypass_side == "left":
    angular_z = +base_edge_turn + k_edge * distance_error
else:
    angular_z = -base_edge_turn - k_edge * distance_error
```

直觉：

- 离障碍**太近**（`obstacle_side_distance` 小，`distance_error` 正）→ 朝**远离障碍**方向转
- 离障碍**太远**（`distance_error` 负）→ 朝**靠近障碍**方向转
- 前方**太近** → 加大转向幅度，降低线速度

### 8.3 扇区参数（统一弧度）

```text
front_half_fov     = π/9   ≈ 0.349 rad   (±20°)
side_inner_angle   = π/4   ≈ 0.785 rad   (±45°)
side_outer_angle   = π/2   ≈ 1.571 rad   (±90°)
```

提取距离：

```text
front_distance      = distance_in_sector(scan, -π/9, +π/9)
left_side_distance  = distance_in_sector(scan, +π/4, +π/2)
right_side_distance = distance_in_sector(scan, -π/2, -π/4)
```

`distance_in_sector` 内部使用分位数（默认 20%）以降低噪声敏感度。

### 8.4 退出边缘跟随

任一条件成立即退出：

- `target_dir_safe == True` **且** 已持续边缘跟随超过 `edge.min_time`
- `target_angle` 与当前行进方向夹角 `< edge.target_reacquire_angle`（默认 0.35 rad）

退出后：`EDGE_FOLLOWING -> TRACKING`。

### 8.5 边缘跟随失败

任一条件触发失败：

- 障碍侧距持续 `> edge.lost_distance`（边缘消失太久）
- 前方距离持续 `< emergency_stop_distance`
- 绕行总时长 `> edge.max_time`
- 在 `edge.progress_window` 时间内 `target_angle` 没有改善（依据 `last_progress_time`）

失败处理由 `edge.fallback` 决定：

- `stop`（默认/保守）：`EDGE_FOLLOWING -> EMERGENCY_STOP -> 朝更空一侧低速转向`
- `gap`：退回 Follow-the-Gap

### 8.6 边缘跟随伪代码

```python
import math

def compute_edge_follow_command(goal, scan, ctx, params):
    front = distance_in_sector(scan, -params.front_half_fov, +params.front_half_fov)

    if ctx.bypass_side == "left":      # 障碍在右
        obstacle_side = distance_in_sector(scan, -math.pi/2, -math.pi/4)
        distance_error = params.edge_follow_distance - obstacle_side
        steering = +params.base_edge_turn + params.k_edge * distance_error
    else:                              # 障碍在左
        obstacle_side = distance_in_sector(scan, +math.pi/4, +math.pi/2)
        distance_error = params.edge_follow_distance - obstacle_side
        steering = -params.base_edge_turn - params.k_edge * distance_error

    if front < params.front_slowdown_distance:
        steering *= 1.5
        linear = params.edge_follow_speed * 0.5
    else:
        linear = params.edge_follow_speed

    ctx.last_seen_obstacle_distance = obstacle_side
    return VelocityCommand(
        linear_x=clamp(linear, 0.0, params.max_linear_speed),
        angular_z=clamp(steering, -params.max_angular_speed, params.max_angular_speed),
    )
```

注意：左右扇区数值依赖第 3 节的坐标约定（左 = `+y`，角度正）。如传感器自身角度定义不同，必须先做角度变换再调用 `distance_in_sector`。

## 9. 状态机设计

```text
IDLE
TRACKING
AVOIDING            (单帧瞬态)
EDGE_FOLLOWING
EMERGENCY_STOP
GOAL_REACHED
LOST_TARGET
```

状态语义：

- **IDLE**：无目标或系统未启动，输出 0 速度
- **TRACKING**：目标有效且方向安全，朝目标移动
- **AVOIDING**：单帧瞬态，确定 `bypass_side` 后立即进入 `EDGE_FOLLOWING`
- **EDGE_FOLLOWING**：沿障碍边缘保持距离绕行
- **EMERGENCY_STOP**：障碍过近或边缘跟随失败，立即停车 + 朝更空一侧缓慢转向
- **GOAL_REACHED**：`target_dist < goal_tolerance`，停车
- **LOST_TARGET**：目标过期或置信度过低
  - 短暂丢失（`elapsed < goal_timeout_short`）：维持上次方向，线速度按时间衰减
  - 长时间丢失：停车或以 `search_angular_speed` 原地搜索

状态转移：

```text
IDLE -> TRACKING:
  收到有效目标
TRACKING -> AVOIDING:
  目标方向被障碍阻挡
AVOIDING -> EDGE_FOLLOWING:
  bypass_side 已确定（同帧立即转移）
EDGE_FOLLOWING -> TRACKING:
  退出条件成立（见 8.4）
EDGE_FOLLOWING -> EMERGENCY_STOP:
  失败条件成立（见 8.5）
EMERGENCY_STOP -> TRACKING:
  front_distance > emergency_clear_distance
  持续 emergency_clear_time 且目标有效
EMERGENCY_STOP -> IDLE:
  累计停车超过 emergency_max_time
LOST_TARGET -> TRACKING:
  连续 N 帧（推荐 3）收到 confidence > threshold 的目标
LOST_TARGET -> IDLE:
  丢失超过 goal_timeout_stop
GOAL_REACHED -> TRACKING:
  收到新的、距离 > goal_tolerance + goal_tolerance_hysteresis 的目标
任何状态 -> EMERGENCY_STOP:
  front_distance < emergency_stop_distance
任何状态（GOAL_REACHED 除外）-> LOST_TARGET:
  目标超时或置信度过低
```

## 10. 主循环

控制频率推荐 20 Hz：

```python
import time

while running:
    now  = time.monotonic()
    goal = vision.get_latest_goal()
    scan = obstacle.get_latest_scan()

    if goal and now - goal.timestamp > params.goal_timeout_stop:
        goal = None
    if scan and now - scan.timestamp > params.obstacle_timeout:
        scan = None     # 障碍数据失效 → 视为前方阻塞 → EMERGENCY_STOP
    if goal and scan and abs(goal.timestamp - scan.timestamp) > params.max_time_skew:
        # 视觉/障碍时间戳偏差过大，按保守策略降速或视为数据失效
        ...

    cmd = navigator.compute_command(goal, scan, now)
    chassis.send_velocity(cmd.linear_x, cmd.angular_z)

    sleep_until_next_tick(params.control_rate)
```

建议多线程结构：

- 视觉线程：读取相机并更新 `latest_goal`
- 障碍线程：读取雷达 / 深度并更新 `latest_scan`
- 控制线程：固定频率读取最新数据、计算并下发速度
- 数据共享使用带时间戳的"snapshot + lock"，或无锁原子指针

## 11. 底盘接口

底盘只需支持速度控制接口：

- `linear_x`：m/s
- `angular_z`：rad/s

通信方式：Serial / CAN / TCP / UDP / 厂商 SDK。

文本协议示例：

```text
VEL 0.20 -0.35\n
```

二进制协议示例：

```text
Header + linear_x + angular_z + checksum
```

差速底盘必须做轮速约束（在 7.5 平滑后再执行）：

```text
v_left  = linear_x - (wheel_base / 2) * angular_z
v_right = linear_x + (wheel_base / 2) * angular_z

scale = max(1.0, max(|v_left|, |v_right|) / wheel_max_speed)
v_left  /= scale
v_right /= scale

# 反推回 (linear_x, angular_z) 后下发
linear_x  = (v_left + v_right) / 2
angular_z = (v_right - v_left) / wheel_base
```

底盘驱动需处理：

- 速度限幅
- 通信超时停车
- 急停指令
- 心跳检测（建议 ≥ 5 Hz）

## 12. 配置文件

参数命名规约（用前缀分组）：

- `robot.*`：机器人尺寸 / footprint
- `sensors.*`：传感器外参（相对 base_link）
- `nav.*`：导航通用
- `safety.*`：安全 / 急停
- `edge.*`：边缘跟随
- `vision.*` / `obstacle.*` / `chassis.*`：各模块独占

> **重要**：`safety.`* 和 `edge.*` 中的所有距离阈值都是"机器人边缘到障碍"的纯安全裕度（已扣除 footprint）。修改 `robot.*` 的尺寸**不需要**重新调整这些阈值。

示例 `config.yaml`：

```yaml
control_rate: 20.0
max_time_skew: 0.2           # 视觉/障碍时间戳最大偏差 (s)

robot:
  shape: rectangle           # rectangle | circle
  length: 0.40               # x 方向长度 (m)
  width: 0.30                # y 方向宽度 (m)
  height: 0.50               # z 方向高度 (m)，用于深度相机扫描带选取
  radius: 0.0                # 圆形机器人半径 (m)，rectangle 时填 0
  footprint_radius: 0.25     # 用于 obstacle 膨胀，建议 = circumscribed_radius
                             # rectangle 默认 ≈ sqrt(0.20^2 + 0.15^2) ≈ 0.25

sensors:
  lidar_offset_x: 0.10       # 雷达相对 base_link 前后偏移 (m)
  lidar_offset_y: 0.0
  lidar_offset_yaw: 0.0      # rad
  camera_offset_x: 0.05
  camera_offset_y: 0.0
  camera_offset_z: 0.30      # 相机距地面高度 (m)

vision:
  confidence_threshold: 0.6
  goal_timeout_short: 0.5    # 短暂丢失，惯性前进
  goal_timeout_stop: 1.0     # 长时间丢失，进入搜索/停车
  multi_target_policy: highest_confidence

obstacle:
  source: lidar              # lidar | depth_camera
  fov_min_angle: -1.57       # rad
  fov_max_angle: +1.57       # rad
  max_range: 5.0
  min_range: 0.05
  obstacle_timeout: 0.5      # 障碍数据时效 (s)
  apply_footprint_inflation: true   # 输出前减去 robot.footprint_radius

nav:
  max_linear_speed: 0.35
  min_linear_speed: 0.05
  max_angular_speed: 1.2
  max_linear_acc: 0.5        # m/s^2，速度平滑
  max_angular_acc: 2.0       # rad/s^2

  k_turn: 1.8
  goal_tolerance: 0.25       # 应 ≥ inscribed_radius + 0.05
  goal_tolerance_hysteresis: 0.1

  front_half_fov: 0.349      # rad，"前方"扇区半角 ≈ 20°

  search_angular_speed: 0.25

# ↓↓↓ 下列所有 *_distance 都是"机器人边缘到障碍"的纯安全裕度 ↓↓↓
safety:
  safety_distance: 0.30           # 方向安全的最小裕度
  emergency_stop_distance: 0.10   # 触发急停的最小裕度（必须 < safety_distance）
  slowdown_distance: 0.60         # 开始降速的距离
  emergency_clear_distance: 0.40  # 急停恢复阈值
  emergency_clear_time: 0.5       # 持续多久才算恢复 (s)
  emergency_max_time: 5.0         # 连续急停超过该值进入 IDLE (s)

edge:
  enabled: true
  fallback: stop             # stop | gap
  follow_distance: 0.30      # 机器人边缘到障碍的目标距离
  follow_speed: 0.18
  min_time: 1.0
  max_time: 8.0
  lost_distance: 1.2         # 障碍侧距 > 该值视为边缘消失
  lost_timeout: 0.6
  base_turn: 0.25
  k_edge: 1.2
  front_slowdown_distance: 0.40
  target_reacquire_angle: 0.35
  progress_window: 2.0       # target_angle 改善判定窗口 (s)

chassis:
  type: serial               # serial | can | tcp | udp | vendor
  port: /dev/ttyUSB0
  baudrate: 115200
  send_timeout: 0.05         # 单次发送 IO 超时 (s)
  ack_timeout: 0.3           # 收不到 ACK / 心跳的容忍时长 (s)
  wheel_base: 0.28           # 仅差速底盘需要 (m)，一般 ≈ robot.width - 轮宽
  wheel_max_speed: 0.6       # 单轮最大线速度 (m/s)
```

参数自检（启动时建议检查）：

```text
assert safety.emergency_stop_distance < safety.safety_distance
assert safety.safety_distance < safety.slowdown_distance
assert safety.emergency_clear_distance > safety.emergency_stop_distance
assert nav.goal_tolerance >= robot.inscribed_radius + 0.05
assert chassis.wheel_base <= robot.width
assert robot.footprint_radius >= robot.inscribed_radius
```

## 13. 日志与调试

建议每帧记录：

- `current_state`、`previous_state`
- `goal.x`、`goal.y`、`goal.confidence`
- `target_angle`、`target_dist`
- `front_distance`、`left_side_distance`、`right_side_distance`
- `selected_gap`（使用 Follow-the-Gap 时）
- `edge.active`、`edge.bypass_side`
- `obstacle_side_distance`、`distance_error`
- `steering_angle`
- `linear_x`、`angular_z`（限幅前 / 后各一份）
- 时间戳：`goal.timestamp`、`scan.timestamp`、控制循环 `now`

可选可视化：

- 简单 Web UI（实时状态 + 极坐标障碍图）
- OpenCV 图像叠加（目标框 + 距离）
- Matplotlib 极坐标障碍图
- 边缘跟随侧向距离曲线
- 终端实时状态

## 14. 安全策略

必须包含的保护：

- 目标超时停车
- 障碍数据超时停车
- 底盘通信超时停车
- 前方急停
- 边缘跟随超时停车
- 侧边距离异常停车或退回 Follow-the-Gap
- 速度 / 加速度限幅
- 启动默认 0 速度
- 程序退出前发送停车指令（信号处理 + `atexit`）

推荐超时（与 yaml 一致）：

- 目标超时：1.0 s
- 障碍数据超时：0.5 s
- 底盘通信（ACK）超时：0.3 s
- 边缘丢失超时：0.6 s

## 15. 系统限制

不使用里程计和全局定位，因此：

- 不能知道自己走过的距离
- 不能规划不可见区域
- 只能进行短期局部绕障
- 不能保证处理复杂迷宫或死胡同
- 目标丢失后只能搜索或停车

加入边缘跟随后，可稳定绕过：

- 单个箱子
- 柱子
- 局部挡路的人或物体
- 目标方向被部分遮挡但两侧有通路的障碍

仍不能保证解决：

- U 型障碍
- 封闭死胡同
- 必须先远离目标才能到达的复杂路径
- 传感器视野外才有出口的场景

系统成立的关键前提：

- 视觉模块持续更新目标相对位置
- 障碍感知覆盖机器人前进方向
- 底盘能可靠执行速度指令

## 16. 开发阶段建议

**第一阶段：仿真或离线验证**

- 实现 `LocalGoal + ObstacleScan -> VelocityCommand`
- 用录制数据测试 Follow-the-Gap
- 用录制数据测试边缘跟随
- 验证状态机和急停

**第二阶段：接入真实传感器**

- 接入雷达或深度相机
- 接入视觉目标检测
- 输出调试可视化

**第三阶段：接入底盘**

- 低速测试
- 测试急停
- 测试目标丢失
- 测试绕过简单障碍
- 测试沿箱子、墙角、柱子边缘绕行

**第四阶段：优化**

- 速度平滑参数调优
- 目标丢失搜索策略
- 深度相机 → 伪 2D scan 的精度提升
- 复杂障碍绕行策略
- 边缘跟随参数自动调优

## 17. 验收测试用例


| 编号    | 场景                                                                   | 通过条件                                                             |
| ----- | -------------------------------------------------------------------- | ---------------------------------------------------------------- |
| TC-1  | 急停：障碍突然出现在距机器人**边缘** 0.05 m                                          | 200 ms 内 `linear_x` 降为 0，状态进入 `EMERGENCY_STOP`                   |
| TC-2  | 短暂目标丢失：1 帧 confidence < threshold                                    | 维持上次方向，速度不跳变                                                     |
| TC-3  | 长时间目标丢失：goal 1 s 不更新                                                 | 进入 `LOST_TARGET`，速度衰减为 0                                         |
| TC-4  | 单箱子绕行：1.5 m 前方放置 0.5 m 立方体                                           | 状态依次 `TRACKING -> AVOIDING -> EDGE_FOLLOWING -> TRACKING`，最终到达目标 |
| TC-5  | 双侧通路狭窄：仅左侧 clearance 足够                                              | `bypass_side = "left"` 且不抖动                                      |
| TC-6  | 通信丢失：底盘 0.3 s 无 ACK                                                  | 主动下发 0 速度，进入 `EMERGENCY_STOP`                                    |
| TC-7  | 数据不同步：goal 与 scan 时间戳差 0.5 s                                         | 触发 `max_time_skew` 保护，按保守策略降速                                    |
| TC-8  | 目标到达：`target_dist < 0.25 m`                                          | 进入 `GOAL_REACHED`，速度 0                                           |
| TC-9  | 目标在身后：`target_angle ≈ π`                                             | `linear_x = 0`，原地朝目标方向转                                          |
| TC-10 | 急停恢复：障碍移走 0.5 s 后                                                    | 状态从 `EMERGENCY_STOP` 回到 `TRACKING`                               |
| TC-11 | Footprint 膨胀：raw scan 距离 0.50 m，`footprint_radius=0.25`              | `ObstacleScan` 中输出距离 ≈ 0.25 m                                    |
| TC-12 | 不同尺寸机器人：把 `robot.length` 从 0.40 改成 0.60                              | 不修改 safety/edge 参数，行为应保持等效安全裕度                                   |
| TC-13 | 参数自检：把 `safety.emergency_stop_distance` 设大于 `safety.safety_distance` | 启动时报错并拒绝运行                                                       |


## 18. 结论

该系统是一个独立的**局部反应式**导航系统，核心公式：

```text
LocalGoal + ObstacleScan -> VelocityCommand
```

它不依赖 ROS2、Nav2、TF、Odom，也不需要全局地图。

加入边缘跟随后，目标方向被障碍挡住时，机器人能沿障碍边缘保持距离绕行，而不仅仅是临时挑选一个安全空隙。

只要目标和障碍都能在机器人局部坐标下被实时感知，机器人就能完成"看到目标，避障绕过去"的行为。