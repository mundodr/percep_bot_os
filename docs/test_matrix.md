# 测试矩阵

## 1. 目的

本文档汇总系统全部测试用例，作为 Test Runner Agent 的执行索引和 Kimi Acceptance Agent 的验收参照。每个测试场景有唯一编号，可在验收包中直接引用。

## 2. 阶段门禁

```text
L0 全部通过 → L1
L1 核心场景通过率 >= 95%，碰撞 0 → L2
L2 通过 → L3
L3 通过 → L4
L4 通过 → L5
L5 通过 → 允许低速真机测试
```

不允许跳层。

## 3. L0 单元级算法测试

| 编号 | 模块 | 场景 | 通过条件 | Owner Agent |
| --- | --- | --- | --- | --- |
| L0-1 | scan_utils | 扇区内有多个距离 | `distance_in_sector` 返回指定分位数 | Navigation Core |
| L0-2 | scan_utils | 扇区内无有效点 | 返回 `math.inf` | Navigation Core |
| L0-3 | footprint | raw distance 0.50 m，footprint 0.25 m | effective distance 0.25 m | Navigation Core |
| L0-4 | navigator | `front_distance < emergency_stop_distance` | 进入 `EMERGENCY_STOP` | Navigation Core |
| L0-5 | navigator | 目标在身后 | `linear_x = 0`，只转向 | Navigation Core |
| L0-6 | route_manager | 给定 GlobalRoute | 输出前方 lookahead `LocalSubgoal` | Route Manager |
| L0-7 | brain_schema | 合法 JSON | 通过 `BrainDecision` 校验 | Brain |
| L0-8 | brain_schema | 非法 intent | 拒绝并 fallback | Brain |
| L0-9 | map_store | 写入 MapUpdate | manifest 版本递增 | Map Store |
| L0-10 | map_store | 中断恢复 | 读取最近有效 snapshot | Map Store |

**通过标准**：全部通过，任一失败不得进入 L1。

## 4. L1 2D 闭环导航测试

| 编号 | 场景 | 通过条件 | Owner Agent |
| --- | --- | --- | --- |
| L1-1 | 直线到目标，无障碍 | 到达目标，路径无振荡 | Navigation Core |
| L1-2 | 前方突然出现障碍 | 200 ms 内急停 | Navigation Core |
| L1-3 | 单箱子挡住目标方向 | `TRACKING → AVOIDING → EDGE_FOLLOWING → TRACKING` | Navigation Core |
| L1-4 | 仅左侧有通道 | `bypass_side = left` 且不左右抖动 | Navigation Core |
| L1-5 | 目标短暂丢失 | 速度平滑衰减，不突变 | Navigation Core |
| L1-6 | 目标长时间丢失 | 进入 `LOST_TARGET` 或停车 | Navigation Core |
| L1-7 | U 型死胡同 | 不碰撞，超时后停车或请求重规划 | Navigation Core |
| L1-8 | 窄通道 | 不碰撞，速度自动降低 | Navigation Core |

**通过标准**：核心场景通过率 >= 95%，碰撞 0。

**必须输出**：`trajectory.csv`、`commands.csv`、`state_log.csv`、`scan_log.npz`、`summary.json`、`debug_video.mp4`。

## 5. L2 长距离路径回放测试

| 编号 | 场景 | 通过条件 | Owner Agent |
| --- | --- | --- | --- |
| L2-1 | 简单走廊长距离路线 | 连续生成 `LocalSubgoal` 并到达终点 | Route Manager |
| L2-2 | 路径中间短时动态障碍 | 局部绕行，不触发重规划 | Route Manager + Navigation Core |
| L2-3 | 路径走廊长期阻塞 | 上报 blocked corridor 并请求重规划 | Route Manager |
| L2-4 | 路线偏离过大 | 触发 route correction 或 replan | Route Manager |
| L2-5 | 到达目标附近 | 切换到语义目标确认或末端精修 | Route Manager + Semantic Map |

**通过标准**：不碰撞，route progress 单调推进或合理重规划，`LocalSubgoal` 不跳变到机器人身后远处。

## 6. L3 语义几何回放测试

| 编号 | 场景 | 通过条件 | Owner Agent |
| --- | --- | --- | --- |
| L3-1 | 视频中有单个椅子 | 查询 `"chair"` 选中正确对象 | Semantic Map |
| L3-2 | 多个相似物体 | 选择综合分数最高对象 | Semantic Map |
| L3-3 | 高 CLIP 分数但无 3D 点 | 不输出有效目标 | Semantic Map |
| L3-4 | 前方点云障碍 | 生成正确 `ObstacleScan` | Semantic Map |
| L3-5 | 低置信点云 | 降低权重或保守处理 | Semantic Map |
| L3-6 | 目标短暂遮挡 | 语义对象保留，confidence 衰减 | Semantic Map |

**通过标准**：`ObstacleScan` 角度方向正确，距离已扣除 footprint，语义目标必须有有效 3D 几何，CLIP 不允许覆盖安全避障结果。

## 7. L4 探索建图与持久化测试

| 编号 | 场景 | 通过条件 | Owner Agent |
| --- | --- | --- | --- |
| L4-1 | 初始地图有未知边界 | 生成安全 `ExplorationTarget` | Exploration |
| L4-2 | 访问 frontier 后看到新区域 | `metric_map` 扩展，frontier 更新 | Exploration + Map Store |
| L4-3 | 发现新语义物体 | `semantic_map` 写入 object 与 embedding | Semantic Map + Map Store |
| L4-4 | frontier 无信息增益 | 标记 `low_gain` 或 visited | Exploration |
| L4-5 | frontier 连续失败 | 标记 failed，cooldown 内不再选择 | Exploration |
| L4-6 | 程序中断 | 从最近 snapshot 恢复 | Map Store |
| L4-7 | 地图保存失败 | 报警并暂停探索 | Map Store |
| L4-8 | 动态障碍出现 | 写入 dynamic layer，不污染 static layer | Map Store |

**必须额外输出**：`manifest.json`、`map_updates.jsonl`、`snapshots/`、`debug_timeline.png`。

## 8. L5 3D 闭环测试（Webots）

| 编号 | 场景 | 通过条件 | Owner Agent |
| --- | --- | --- | --- |
| L5-1 | 长距离导航到房间门口 | 到达目标区域，不碰撞 | Integration + Webots |
| L5-2 | 寻找指定物体 | 找到目标并接近到安全距离 | Semantic Map + Webots |
| L5-3 | 未知区域探索 | 覆盖率达到目标值 | Exploration + Webots |
| L5-4 | 动态障碍横穿 | 急停或绕行 | Navigation Core + Webots |
| L5-5 | 路径阻塞 | 触发重规划或切换 frontier | Route Manager + Webots |
| L5-6 | 地图保存后重启 | 继续上次探索 | Map Store + Webots |

## 9. BRAIN 大脑验收测试

| 编号 | 用户指令 | 通过条件 | Owner Agent |
| --- | --- | --- | --- |
| BRAIN-1 | 继续探索并保存地图 | `intent=explore` | Brain |
| BRAIN-2 | 找红色椅子 | `intent=semantic_search`，`target_query` 正确 | Brain |
| BRAIN-3 | 去 A 区门口 | `intent=navigate`，目标可传给 planner | Brain |
| BRAIN-4 | 停下 | `intent=stop` | Brain |
| BRAIN-5 | 输出非法 JSON | schema 拒绝，fallback | Brain |
| BRAIN-6 | 请求直接设置速度 | 拒绝，不生成 `VelocityCommand` | Brain |

## 10. 故障注入测试

| 编号 | 故障 | 通过条件 | Owner Agent |
| --- | --- | --- | --- |
| F-1 | `ObstacleScan` 超时 | 停车或急停 | Navigation Core |
| F-2 | LingBot-Map prediction 缺帧 | 使用最近有效帧或停车 | Semantic Map |
| F-3 | CLIP 低相似度 | 不生成目标 | Semantic Map |
| F-4 | qwen3-vl 超时 | fallback 到 pause / stop | Brain |
| F-5 | map save 失败 | 报警，暂停探索 | Map Store |
| F-6 | planner 无路径 | 进入探索、重规划或 ask_user | Route Manager |
| F-7 | 定位漂移过大 | 暂停长期地图写入 | Semantic Map + Map Store |
| F-8 | 动态障碍误写静态层 | 测试失败 | Map Store |

## 11. 反应式导航详细测试（补充 TC 系列）

来源：`reactive_navigation_design.md` 验收用例，覆盖 L0/L1 细粒度行为。

| 编号 | 场景 | 通过条件 | 对应层级 |
| --- | --- | --- | --- |
| TC-1 | 急停：障碍距边缘 0.05 m | 200 ms 内 `linear_x = 0`，进入 `EMERGENCY_STOP` | L0/L1 |
| TC-2 | 短暂目标丢失：1 帧 confidence < threshold | 维持上次方向，速度不跳变 | L1 |
| TC-3 | 长时间目标丢失：goal 1 s 不更新 | 进入 `LOST_TARGET`，速度衰减为 0 | L1 |
| TC-4 | 单箱子绕行：1.5 m 前方 0.5 m 立方体 | 状态依次 `TRACKING → AVOIDING → EDGE_FOLLOWING → TRACKING` | L1 |
| TC-5 | 双侧通路狭窄：仅左侧够 | `bypass_side = "left"` 且不抖动 | L1 |
| TC-6 | 通信丢失：底盘 0.3 s 无 ACK | 下发 0 速度，进入 `EMERGENCY_STOP` | L1 |
| TC-7 | 数据不同步：goal 与 scan 差 0.5 s | 触发 `max_time_skew` 保护 | L0 |
| TC-8 | 目标到达：`target_dist < 0.25 m` | 进入 `GOAL_REACHED`，速度 0 | L1 |
| TC-9 | 目标在身后：`target_angle ≈ π` | `linear_x = 0`，原地转 | L0 |
| TC-10 | 急停恢复：障碍移走 0.5 s 后 | `EMERGENCY_STOP → TRACKING` | L1 |
| TC-11 | Footprint 膨胀：raw 0.50 m，footprint 0.25 m | 输出 0.25 m | L0 |
| TC-12 | 不同尺寸机器人：length 0.40 → 0.60 | 不改 safety/edge 参数行为等效 | L0 |
| TC-13 | 参数自检：emergency > safety | 启动报错拒绝运行 | L0 |

## 12. 语义地图详细测试（补充 SMT/EXP 系列）

来源：`lingbot_clip_semantic_map_design.md` 验收用例。

| 编号 | 场景 | 通过条件 | 对应层级 |
| --- | --- | --- | --- |
| SMT-1 | 已有 planner 输出长距离路线 | Route Manager 正确生成连续 `LocalSubgoal` | L2 |
| SMT-2 | 路径上出现短时障碍 | ReactiveNavigator 局部绕行，不立即重规划 | L2 |
| SMT-3 | 路径走廊长时间阻塞 | 上报 blocked corridor 并请求全局重规划 | L2 |
| SMT-4 | 视频中有单个 `"chair"` | CLIP 选中正确对象并生成 `SemanticGoal` | L3 |
| SMT-5 | 多个相似物体 | 选择综合最高目标 | L3 |
| SMT-6 | 目标方向有障碍 | `ObstacleScan` 阻止直行，进入避障 | L2/L3 |
| SMT-7 | CLIP 高分但无有效 3D 点 | 不生成有效 `LocalSubgoal` | L3 |
| SMT-8 | LingBot-Map 低置信度点云 | 不作为可靠障碍或目标位置 | L3 |
| SMT-9 | 地图层 0.5 s 未更新 | 导航器按超时策略停车 | L3 |
| SMT-10 | 文本目标不存在 | 不输出目标，进入 `LOST_TARGET` | L3 |
| SMT-11 | 目标短暂遮挡 | 语义对象保留，confidence 衰减 | L3 |
| SMT-12 | raw distance 0.50 m，footprint 0.25 m | effective distance 约 0.25 m | L0 |
| SMT-13 | 目标在物体中心 | 生成 approach goal，不撞向中心 | L3 |
| EXP-1 | 初始地图有未知边界 | 生成安全 frontier `ExplorationTarget` | L4 |
| EXP-2 | 探索发现新可通行区域 | `metric_map` 增量更新，frontier 推进 | L4 |
| EXP-3 | 探索中识别新物体 | `semantic_map` 保存 `SemanticObject` 和 embedding | L4 |
| EXP-4 | 访问 frontier 后无新增信息 | 标记 visited 或 low_gain | L4 |
| EXP-5 | 探索 route 连续失败 | frontier 标记 failed，cooldown 内不再选择 | L4 |
| EXP-6 | 程序中途退出 | 从最近 snapshot 和 manifest 恢复 | L4 |
| EXP-7 | 地图保存连续失败 | 报警并暂停探索 | L4 |
| EXP-8 | 动态障碍临时出现 | 写入 dynamic layer，不污染 static layer | L4 |

## 13. 测试用例统计

| 系列 | 数量 | 层级 |
| --- | --- | --- |
| L0 | 10 | 单元 |
| L1 | 8 | 2D 闭环 |
| L2 | 5 | 长距离路径 |
| L3 | 6 | 语义几何 |
| L4 | 8 | 探索建图 |
| L5 | 6 | 3D 闭环 |
| BRAIN | 6 | 大脑 |
| F | 8 | 故障注入 |
| TC | 13 | 反应式导航细节 |
| SMT | 13 | 语义地图细节 |
| EXP | 8 | 探索细节 |
| **合计** | **91** | |

## 14. 证据包要求

每个测试 run 至少输出：

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

探索场景额外：`manifest.json`、`map_updates.jsonl`、`snapshots/`、`debug_timeline.png`

语义和大脑场景额外：`brain_decisions.jsonl`、`semantic_objects.jsonl`、`keyframes/`
