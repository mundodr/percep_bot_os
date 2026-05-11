# 机器人导航仿真测试与验收方案

## 1. 目标

本文档用于验证以下系统能否组合成一个可落地的机器人导航方案：

- 非 ROS2 反应式局部导航基座
- 已有地图与长距离路径规划
- LingBot-Map 局部 3D 几何建图
- CLIP Embedding 语义地图
- `qwen3-vl:4b` 高层任务大脑
- 探索模式与边探索边保存地图

仿真验收目标不是证明真实机器人一定安全，而是在上真机前证明：

```text
任务理解 -> 路径规划 / 探索 -> 局部几何感知 -> 语义目标确认
        -> LocalSubgoal + ObstacleScan
        -> ReactiveNavigator
        -> VelocityCommand
        -> 地图增量保存
```

这条链路在可控环境中稳定、可复现、可调试。

## 2. 验收范围

### 2.1 必须验收

- `qwen3-vl:4b` 能把自然语言任务转换为结构化 `BrainDecision`
- 全局路径或探索目标能转换为 `LocalSubgoal`
- LingBot-Map 输出能转换为 `ObstacleScan`
- CLIP 能把文本目标和语义对象关联
- ReactiveNavigator 能在仿真中完成目标跟踪、避障、急停、边缘跟随
- 探索模式能生成 frontier 目标
- 地图能持续保存 `metric_map`、`semantic_map`、`route_graph` 和 snapshot
- 异常情况下系统进入停车、暂停或重规划，而不是继续盲目前进

### 2.2 暂不验收

- 真实底盘通信可靠性
- 真实传感器噪声全覆盖
- 户外强光、反光、透明物体等复杂视觉问题
- 大规模多楼层地图管理
- 多机器人协同建图

## 3. 仿真分层

采用五层递进验收，不允许跳层。

```text
L0: 单元级算法仿真
L1: 2D 闭环导航仿真
L2: 长距离路径回放仿真
L3: LingBot-Map + CLIP 离线语义几何回放
L4: 探索建图与地图持久化仿真
L5: 3D 闭环仿真
```

每一层通过后，才能进入下一层。

## 4. 测试环境

### 4.1 推荐目录

```text
tests/
  unit/
  sim2d/
  replay/
  exploration/
  integration/

sim/
  worlds/
  fixtures/
  outputs/

maps/
  test_site/
    snapshots/
    metric_map.*
    semantic_db.*
    route_graph.*
    manifest.json

logs/
  test_runs/
```

### 4.2 仿真工具选型

本项目采用“两级仿真 + 离线回放”的工具组合：

```text
主算法仿真：Python 2D custom simulator
主 3D 闭环仿真：Webots
视觉地图回放：LingBot-Map batch prediction replay
语义回放：CLIP embedding replay
大脑回放：qwen3-vl:4b service / mock brain
自动化测试：pytest
可视化：Matplotlib / OpenCV / Web UI
```

#### 4.2.1 Python 2D Custom Simulator

用途：

- L0 单元测试
- L1 2D 闭环导航
- L2 长距离路径回放
- L4 探索建图逻辑验证

需要实现：

```text
2D world:
  静态障碍、多边形障碍、动态障碍、目标点、未知区域

robot model:
  差速底盘简化模型

sensor model:
  2D raycast lidar -> ObstacleScan
  fake camera target -> SemanticObject / LocalSubgoal

map model:
  occupancy grid
  frontier layer
  semantic object layer
```

选择理由：

- 实现最快
- 可完全控制场景和随机种子
- 便于自动化跑大量 case
- 不依赖 GPU
- 适合先验证 `ReactiveNavigator`、`Route Manager`、`Exploration Planner`

#### 4.2.2 Webots 3D Simulator

用途：

- L5 3D 闭环仿真
- 接近真实机器人的相机、深度、雷达、底盘闭环
- 验证从感知到控制的完整链路

需要使用：

```text
Webots world:
  室内走廊、房间、门、桌椅、箱子、动态行人/障碍

Webots robot:
  differential drive
  RGB camera
  depth camera 或 2D lidar
  wheel encoder 可选

Webots controller:
  Python controller
  输出 VelocityCommand
  记录 sensor frames 和 robot pose
```

选择理由：

- 非 ROS2 也能直接控制
- 自带 camera / depth / lidar / differential drive
- Python 接入简单
- 比 PyBullet 更适合移动机器人传感器闭环
- 比 Isaac Sim 更轻，适合第一版验收

#### 4.2.3 LingBot-Map Offline Replay

用途：

- L3 语义几何回放
- 将视频或 Webots 导出的图像序列转换为 3D prediction
- 验证 `prediction -> ObstacleScan`

输入：

```text
video.mp4
image_folder/
Webots camera frames
```

输出：

```text
LingBot-Map predictions
depth / world_points / camera pose / confidence
```

第一版不要求 LingBot-Map 实时运行。先采用离线 batch replay，避免 GPU 延迟影响控制器验收。

#### 4.2.4 CLIP Embedding Replay

用途：

- 文本目标与图像区域匹配
- 生成或回放 `SemanticObject`
- 验证语义目标不会绕过几何安全

第一版推荐：

```text
open_clip 或 transformers CLIP
object-level crop embedding
embedding cache
```

#### 4.2.5 Qwen3-VL 4B Brain

用途：

- 自然语言任务解析
- 选择 `navigate`、`explore`、`semantic_search`、`inspect` 等 intent
- 生成结构化 `BrainDecision`

运行方式：

```text
推荐：Ollama qwen3-vl:4b
备选：OpenAI-compatible HTTP service
测试：mock brain JSON replay
```

仿真验收中必须同时支持真实 `qwen3-vl:4b` 调用和 mock brain。自动化回归优先使用 mock，端到端演示使用真实模型。

#### 4.2.6 工具与测试层级对应表

| 层级 | 主要工具 | 目的 |
| --- | --- | --- |
| L0 | pytest + Python unit tests | 核心函数和 schema |
| L1 | Python 2D simulator | 局部避障闭环 |
| L2 | Python 2D simulator + route replay | 长距离路径执行 |
| L3 | LingBot-Map offline replay + CLIP replay | 语义几何输入 |
| L4 | Python 2D simulator + map store | 探索建图与保存 |
| L5 | Webots + Python controller | 3D 感知控制闭环 |

#### 4.2.7 不作为第一版主工具

| 工具 | 暂不作为主工具的原因 |
| --- | --- |
| Gazebo / Ignition | 更偏 ROS 生态，当前方案明确非 ROS2 |
| Isaac Sim | 功能强但重，硬件和工程成本高 |
| PyBullet | 动力学方便，但相机/深度/移动机器人场景搭建不如 Webots 顺手 |
| CARLA | 偏自动驾驶道路场景，不适合室内服务机器人第一版 |

### 4.3 固定随机性

所有测试必须支持固定随机种子：

```yaml
test:
  random_seed: 42
  deterministic_replay: true
```

随机障碍、随机目标、噪声注入都必须记录 seed。

## 5. 通用验收指标

### 5.1 导航指标

| 指标 | 通过标准 |
| --- | --- |
| 任务成功率 | 核心场景 >= 95% |
| 碰撞次数 | 0 |
| 急停响应 | 200 ms 内 `linear_x = 0` |
| 目标到达误差 | <= `goal_tolerance` |
| 最大横向偏离 | <= `max_cross_track_error` |
| 速度突变 | 不超过配置加速度限幅 |
| 数据超时处理 | 必须停车或暂停 |

### 5.2 地图指标

| 指标 | 通过标准 |
| --- | --- |
| MapUpdate 写入周期 | 不超过配置值 1.5 倍 |
| snapshot 恢复 | 能恢复最近一次有效地图 |
| 动态障碍污染静态图 | 不允许 |
| 语义对象重复率 | 可接受，且后续能合并 |
| frontier 访问记录 | visited / failed / low_gain 状态正确 |

### 5.3 语义指标

| 指标 | 通过标准 |
| --- | --- |
| 文本目标解析 | 输出合法 `BrainDecision` |
| CLIP 目标选择 | 简单场景准确率 >= 90% |
| 低置信目标 | 不生成有效 `LocalSubgoal` |
| 目标短暂遮挡 | confidence 衰减但不立即抖动 |

## 6. L0 单元级算法仿真

### 6.1 目的

验证核心算法函数在无闭环环境下正确。

### 6.2 测试项

| 编号 | 模块 | 场景 | 通过条件 |
| --- | --- | --- | --- |
| L0-1 | scan utils | 扇区内有多个距离 | `distance_in_sector` 返回指定分位数 |
| L0-2 | scan utils | 扇区内无有效点 | 返回 `math.inf` |
| L0-3 | footprint | raw distance 0.50 m，footprint 0.25 m | effective distance 0.25 m |
| L0-4 | navigator | `front_distance < emergency_stop_distance` | 进入 `EMERGENCY_STOP` |
| L0-5 | navigator | 目标在身后 | `linear_x = 0`，只转向 |
| L0-6 | route manager | 给定 GlobalRoute | 输出前方 lookahead `LocalSubgoal` |
| L0-7 | brain schema | 合法 JSON | 通过 `BrainDecision` 校验 |
| L0-8 | brain schema | 非法 intent | 拒绝并 fallback |
| L0-9 | map store | 写入 MapUpdate | manifest 版本递增 |
| L0-10 | map store | 中断恢复 | 读取最近有效 snapshot |

### 6.3 通过标准

- 单元测试全部通过
- 覆盖急停、目标丢失、footprint、schema 校验、地图保存
- 任一失败不得进入 L1

## 7. L1 2D 闭环导航仿真

### 7.1 目的

在无 LingBot-Map、无 CLIP、无大模型的条件下，验证局部导航基座。

仿真器内部可以知道世界坐标，但导航器只能接收：

```text
LocalSubgoal + ObstacleScan
```

### 7.2 场景

| 编号 | 场景 | 通过条件 |
| --- | --- | --- |
| L1-1 | 直线到目标，无障碍 | 到达目标，路径无振荡 |
| L1-2 | 前方突然出现障碍 | 200 ms 内急停 |
| L1-3 | 单箱子挡住目标方向 | `TRACKING -> AVOIDING -> EDGE_FOLLOWING -> TRACKING` |
| L1-4 | 仅左侧有通道 | `bypass_side = left` 且不左右抖动 |
| L1-5 | 目标短暂丢失 | 速度平滑衰减，不突变 |
| L1-6 | 目标长时间丢失 | 进入 `LOST_TARGET` 或停车 |
| L1-7 | U 型死胡同 | 不碰撞，超时后停车或请求重规划 |
| L1-8 | 窄通道 | 不碰撞，速度自动降低 |

### 7.3 输出物

每个测试必须保存：

```text
trajectory.csv
commands.csv
state_log.csv
scan_log.npz
summary.json
debug_video.mp4 或 debug_plot.png
```

## 8. L2 长距离路径回放仿真

### 8.1 目的

验证已有地图 planner、Route Manager 和 ReactiveNavigator 的组合。

### 8.2 输入

```text
GlobalRoute
static obstacles
dynamic obstacles
robot initial pose
```

### 8.3 场景

| 编号 | 场景 | 通过条件 |
| --- | --- | --- |
| L2-1 | 简单走廊长距离路线 | 连续生成 `LocalSubgoal` 并到达终点 |
| L2-2 | 路径中间短时动态障碍 | 局部绕行，不触发重规划 |
| L2-3 | 路径走廊长期阻塞 | 上报 blocked corridor 并请求重规划 |
| L2-4 | 路线偏离过大 | 触发 route correction 或 replan |
| L2-5 | 到达目标附近 | 切换到语义目标确认或末端精修 |

### 8.4 通过标准

- 不碰撞
- route progress 单调推进或合理重规划
- `LocalSubgoal` 不跳变到机器人身后远处
- 长时间阻塞必须产生 replan feedback

## 9. L3 语义几何回放仿真

### 9.1 目的

验证 LingBot-Map + CLIP 到导航输入的转换链路。

```text
video / image sequence
    ↓
LingBot-Map predictions
    ↓
Geometry Adapter
    ↓
ObstacleScan

image regions
    ↓
CLIP embeddings
    ↓
SemanticObject
    ↓
SemanticGoal / LocalSubgoal correction
```

### 9.2 场景

| 编号 | 场景 | 通过条件 |
| --- | --- | --- |
| L3-1 | 视频中有单个椅子 | 查询 `"chair"` 选中正确对象 |
| L3-2 | 多个相似物体 | 选择综合分数最高对象 |
| L3-3 | 高 CLIP 分数但无 3D 点 | 不输出有效目标 |
| L3-4 | 前方点云障碍 | 生成正确 `ObstacleScan` |
| L3-5 | 低置信点云 | 降低权重或保守处理 |
| L3-6 | 目标短暂遮挡 | 语义对象保留，confidence 衰减 |

### 9.3 通过标准

- `ObstacleScan` 角度方向正确
- 所有距离已扣除 footprint
- 语义目标必须有有效 3D 几何
- CLIP 不允许覆盖安全避障结果

## 10. L4 探索建图与持久化仿真

### 10.1 目的

验证“边探索边保存地图”。

### 10.2 输入

```text
seed map / empty local map
unknown areas
frontier candidates
simulated observations
semantic objects
```

### 10.3 场景

| 编号 | 场景 | 通过条件 |
| --- | --- | --- |
| L4-1 | 初始地图有未知边界 | 生成安全 `ExplorationTarget` |
| L4-2 | 访问 frontier 后看到新区域 | `metric_map` 扩展，frontier 更新 |
| L4-3 | 发现新语义物体 | `semantic_map` 写入 object 与 embedding |
| L4-4 | frontier 无信息增益 | 标记 `low_gain` 或 visited |
| L4-5 | frontier 连续失败 | 标记 failed，cooldown 内不再选择 |
| L4-6 | 程序中断 | 从最近 snapshot 恢复 |
| L4-7 | 地图保存失败 | 报警并暂停探索 |
| L4-8 | 动态障碍出现 | 写入 dynamic layer，不污染 static layer |

### 10.4 地图保存验收

每个探索 run 必须生成：

```text
manifest.json
metric_map.*
semantic_db.*
route_graph.*
snapshots/
keyframes/
run_summary.json
```

`manifest.json` 必须包含：

```json
{
  "map_id": "test_site",
  "version": 1,
  "created_time": 0.0,
  "updated_time": 0.0,
  "metric_map_path": "...",
  "semantic_db_path": "...",
  "route_graph_path": "...",
  "snapshot_dir": "..."
}
```

## 11. L5 3D 闭环仿真

### 11.1 目的

在更接近真实机器人的环境中验证完整闭环。

推荐使用 Webots：

- 差速底盘
- RGB camera
- depth camera 或 lidar
- 室内场景
- 动态障碍
- 可导出图像序列

### 11.2 闭环链路

```text
qwen3-vl:4b BrainDecision
    ↓
Global Planner / Exploration Planner
    ↓
Route Manager
    ↓
Webots camera / depth / lidar
    ↓
LingBot-Map + CLIP
    ↓
ObstacleScan + LocalSubgoal
    ↓
ReactiveNavigator
    ↓
Webots robot velocity
    ↓
MapUpdate 保存
```

### 11.3 场景

| 编号 | 场景 | 通过条件 |
| --- | --- | --- |
| L5-1 | 长距离导航到房间门口 | 到达目标区域，不碰撞 |
| L5-2 | 寻找指定物体 | 找到目标并接近到安全距离 |
| L5-3 | 未知区域探索 | 覆盖率达到目标值 |
| L5-4 | 动态障碍横穿 | 急停或绕行 |
| L5-5 | 路径阻塞 | 触发重规划或切换 frontier |
| L5-6 | 地图保存后重启 | 继续上次探索 |

## 12. Qwen3-VL 大脑验收

### 12.1 输入

```text
用户指令
当前关键帧
地图摘要
语义对象摘要
frontier 摘要
导航状态
安全状态
```

### 12.2 输出

必须输出合法 `BrainDecision`：

```json
{
  "intent": "explore",
  "target_query": "red chair",
  "map_goal_id": null,
  "mode": "semantic_search",
  "constraints": {
    "max_explore_time": 600
  },
  "requires_confirmation": false,
  "confidence": 0.82,
  "explanation": "Search unexplored areas for a red chair.",
  "timestamp": 0.0
}
```

### 12.3 测试项

| 编号 | 指令 | 通过条件 |
| --- | --- | --- |
| BRAIN-1 | 继续探索并保存地图 | `intent=explore` |
| BRAIN-2 | 找红色椅子 | `intent=semantic_search`，`target_query` 正确 |
| BRAIN-3 | 去 A 区门口 | `intent=navigate`，目标可传给 planner |
| BRAIN-4 | 停下 | `intent=stop` |
| BRAIN-5 | 输出非法 JSON | schema 拒绝，fallback |
| BRAIN-6 | 请求直接设置速度 | 拒绝，不生成 `VelocityCommand` |

## 13. 故障注入测试

必须主动注入故障。

| 编号 | 故障 | 通过条件 |
| --- | --- | --- |
| F-1 | `ObstacleScan` 超时 | 停车或急停 |
| F-2 | LingBot-Map prediction 缺帧 | 使用最近有效帧或停车 |
| F-3 | CLIP 低相似度 | 不生成目标 |
| F-4 | qwen3-vl 超时 | fallback 到 pause / stop |
| F-5 | map save 失败 | 报警，暂停探索 |
| F-6 | planner 无路径 | 进入探索、重规划或 ask_user |
| F-7 | 定位漂移过大 | 暂停长期地图写入 |
| F-8 | 动态障碍误写静态层 | 测试失败 |

## 14. 验收流程

### 14.1 单次测试流程

```text
1. 加载测试配置
2. 初始化地图 / 场景 / 随机种子
3. 启动 brain / planner / navigator / map store
4. 执行仿真
5. 记录所有状态、命令、地图更新和事件
6. 自动计算指标
7. 生成 summary.json 和测试报告
8. 失败时保存复现数据
```

### 14.2 阶段门禁

```text
L0 全部通过
    ↓
L1 核心场景通过率 >= 95%，碰撞 0
    ↓
L2 长距离路径场景通过
    ↓
L3 语义几何回放通过
    ↓
L4 探索保存通过
    ↓
L5 3D 闭环通过
    ↓
允许进入低速真机测试
```

## 15. 测试报告格式

每次测试输出：

```json
{
  "run_id": "2026-05-11T12-00-00",
  "scenario": "L4-2-frontier-expansion",
  "seed": 42,
  "result": "pass",
  "duration_s": 120.0,
  "collision_count": 0,
  "emergency_stop_count": 1,
  "goal_reached": true,
  "coverage_ratio": 0.72,
  "map_version": 5,
  "failed_assertions": [],
  "artifacts": {
    "trajectory": "trajectory.csv",
    "commands": "commands.csv",
    "map_manifest": "manifest.json",
    "debug_video": "debug_video.mp4"
  }
}
```

## 16. 仿真输出物与查看方式

仿真验收不能只输出 `pass/fail`。每次仿真必须生成一个完整的**证据包**，用于证明系统确实跑过仿真、跑了什么场景、机器人怎么动、传感器看到了什么、地图如何变化、为什么判定通过或失败。

### 16.1 单次运行输出目录

每次 run 输出一个独立目录：

```text
logs/test_runs/
  2026-05-11_120000_L4-2-frontier-expansion_seed42/
    run_config.yaml
    summary.json
    events.jsonl
    assertions.json
    trajectory.csv
    commands.csv
    state_log.csv
    scan_log.npz
    brain_decisions.jsonl
    semantic_objects.jsonl
    map_updates.jsonl
    manifest.json
    debug_video.mp4
    debug_topdown.png
    debug_timeline.png
    snapshots/
    keyframes/
```

### 16.2 必须输出的文件

| 文件 | 用途 | 怎么看 |
| --- | --- | --- |
| `summary.json` | 总结是否通过、关键指标、失败原因 | 首先打开它 |
| `run_config.yaml` | 本次仿真的参数、seed、场景 | 用于复现 |
| `debug_video.mp4` | 最直观证明机器人真的跑了 | 直接播放 |
| `debug_topdown.png` | 俯视图：地图、轨迹、障碍、目标 | 看路径是否合理 |
| `debug_timeline.png` | 时间轴：状态、速度、急停、重规划 | 看状态机是否正确 |
| `trajectory.csv` | 机器人每帧位置 | 可画轨迹 |
| `commands.csv` | 每帧速度命令 | 看是否限速、急停 |
| `state_log.csv` | 导航状态机记录 | 看 TRACKING/AVOIDING/EDGE_FOLLOWING |
| `scan_log.npz` | 每帧 `ObstacleScan` | 回放传感器输入 |
| `brain_decisions.jsonl` | qwen3-vl 或 mock brain 输出 | 看任务意图是否正确 |
| `semantic_objects.jsonl` | CLIP 语义对象 | 看目标识别和置信度 |
| `map_updates.jsonl` | 每次地图增量 | 看是否边探索边保存 |
| `manifest.json` | 当前保存地图版本 | 看 snapshot 是否有效 |
| `assertions.json` | 每条验收断言结果 | 看为什么 pass/fail |
| `events.jsonl` | 急停、重规划、探索目标切换等事件 | 调试异常 |

### 16.3 `summary.json` 示例

```json
{
  "run_id": "2026-05-11_120000_L4-2-frontier-expansion_seed42",
  "scenario": "L4-2-frontier-expansion",
  "simulator": "python_2d",
  "seed": 42,
  "result": "pass",
  "duration_s": 120.0,
  "simulated_time_s": 120.0,
  "collision_count": 0,
  "emergency_stop_count": 1,
  "goal_reached": false,
  "coverage_start": 0.31,
  "coverage_end": 0.58,
  "frontiers_visited": 4,
  "map_version_start": 2,
  "map_version_end": 8,
  "brain_decision_count": 3,
  "map_update_count": 120,
  "assertions_passed": 18,
  "assertions_failed": 0,
  "artifacts": {
    "debug_video": "debug_video.mp4",
    "debug_topdown": "debug_topdown.png",
    "debug_timeline": "debug_timeline.png",
    "map_manifest": "manifest.json"
  }
}
```

看到这个文件只能证明自动判定结果，不能单独作为最终证据。必须配合视频、轨迹、日志和地图版本一起看。

### 16.4 `debug_video.mp4` 必须包含什么

2D 仿真视频至少要叠加：

```text
机器人 footprint
机器人轨迹
当前 LocalSubgoal
GlobalRoute / ExploreRoute
障碍物
ObstacleScan 射线或扇区
frontier 候选点
当前状态机 state
linear_x / angular_z
coverage ratio
map version
collision / emergency stop 标记
```

3D Webots 视频至少要保存：

```text
第三人称视角视频
机器人第一视角 RGB
深度图或 lidar 可视化
俯视轨迹图
状态字幕叠加
```

如果没有 `debug_video.mp4` 或关键帧序列，本次仿真不能算完整验收。

### 16.5 `debug_topdown.png` 必须包含什么

俯视图用于一眼判断轨迹是否真实合理：

```text
灰色：未知区域
白色：已知可通行区域
黑色：静态障碍
橙色：动态障碍轨迹
蓝线：机器人真实轨迹
绿线：GlobalRoute / ExploreRoute
红点：急停位置
紫点：语义目标
黄色点：frontier
机器人 footprint：按时间间隔绘制
```

### 16.6 `debug_timeline.png` 必须包含什么

时间轴用于判断系统状态：

```text
state
linear_x
angular_z
front_distance
target_distance
target_angle
collision flag
emergency flag
map_version
coverage_ratio
brain intent
planner / replan events
```

看时间轴可以确认：

- 急停是否在 200 ms 内生效
- 速度是否平滑
- 是否频繁状态抖动
- 探索 coverage 是否增长
- 地图是否持续保存

### 16.7 怎么人工判断“真的做了仿真”

人工验收按这个顺序看：

```text
1. 打开 summary.json
   看 result、scenario、simulator、seed、collision_count、assertions_failed

2. 播放 debug_video.mp4
   看机器人是否真的移动、避障、探索、停车、重规划

3. 打开 debug_topdown.png
   看轨迹是否对应视频，是否穿墙、是否撞障碍

4. 打开 debug_timeline.png
   看状态机和速度变化是否符合预期

5. 检查 manifest.json
   看 map version 是否增加，snapshot 是否存在

6. 检查 map_updates.jsonl
   看探索过程中是否持续写入地图

7. 检查 assertions.json
   看每条验收规则是否逐条通过

8. 用 run_config.yaml + seed 重新跑一次
   结果应能复现
```

### 16.8 自动判定断言

每个测试必须生成 `assertions.json`：

```json
{
  "scenario": "L1-2-sudden-obstacle",
  "assertions": [
    {
      "name": "no_collision",
      "passed": true,
      "value": 0,
      "expected": "collision_count == 0"
    },
    {
      "name": "emergency_stop_under_200ms",
      "passed": true,
      "value_ms": 120,
      "expected": "<= 200"
    },
    {
      "name": "linear_velocity_zero_after_stop",
      "passed": true,
      "value": 0.0,
      "expected": "linear_x == 0"
    }
  ]
}
```

`summary.json` 的 `result` 必须由 `assertions.json` 自动汇总，不能人工手写。

### 16.9 复现要求

一次有效仿真必须能用下面信息复现：

```text
git commit 或文件版本
scenario id
run_config.yaml
random seed
simulator version
model/mock 配置
输入地图和输入视频/prediction
```

若不能复现，最多只能算演示，不能算验收。

### 16.10 最小可接受证据包

任何验收场景至少要有：

```text
summary.json
assertions.json
run_config.yaml
debug_video.mp4 或关键帧序列
debug_topdown.png
trajectory.csv
commands.csv
state_log.csv
```

探索建图场景还必须额外有：

```text
manifest.json
map_updates.jsonl
snapshots/
debug_timeline.png
```

语义和大脑场景还必须额外有：

```text
brain_decisions.jsonl
semantic_objects.jsonl
keyframes/
```

## 17. 最终验收标准

系统仿真验收通过需要同时满足：

- L0-L5 全部通过
- 所有核心场景碰撞次数为 0
- 急停响应满足 200 ms
- 长距离路径能重规划或安全失败
- 探索地图能持续保存并恢复
- 语义目标不会绕过几何安全
- `qwen3-vl:4b` 不会直接控制速度
- 所有失败场景都有明确 fallback

## 18. 上真机前检查

仿真通过后，上真机前仍必须完成：

- 低速模式
- 物理急停按钮
- 底盘通信 watchdog
- 独立近距避障传感器
- 人工遥控接管
- 空旷场地单项测试
- 逐步增加速度和复杂度

## 19. 结论

仿真验收的核心原则是：

```text
先验证每层正确，再验证闭环稳定；
先证明能安全失败，再追求任务成功率；
先保存可复现数据，再调复杂参数。
```

通过本方案后，系统可以进入低速真机联调阶段，但不能直接进入无人值守运行。
