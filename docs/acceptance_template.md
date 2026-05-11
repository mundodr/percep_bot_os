# Kimi 验收模板

## 1. 目的

本文档定义 Kimi Acceptance Agent 的标准验收流程。所有送入 Kimi 验收的任务必须使用本模板格式，确保验收输入完整、输出结构化、返工可追踪。

## 2. 验收前置条件

送入 Kimi 之前必须满足：

- [ ] 相关自动测试已执行
- [ ] 证据包目录存在且文件完整
- [ ] `summary.json` 存在
- [ ] `assertions.json` 存在
- [ ] 变更摘要存在
- [ ] 已知失败项已列出

缺少任何一项不得送 Kimi 验收。

## 3. 验收输入包目录结构

```text
acceptance_packages/
  <task_id>/
    requirement.md
    change_summary.md
    interface_contracts.md (或相关章节摘录)
    test_summary.md
    summary.json
    assertions.json
    evidence_index.md
    screenshots/
    logs_excerpt/
```

## 4. requirement.md 模板

```markdown
# 需求摘要

任务编号: <task_id>
标题: <标题>
Owner Agent: <agent_name>
Phase: <phase>
对应测试层级: <L0/L1/L2/L3/L4/L5>

## 需求描述

<1-3 段描述该任务要实现什么>

## 验收范围

<本次验收包含哪些测试编号>

## 接口依赖

输入:
  - <数据结构名>

输出:
  - <数据结构名>

## 约束

- <安全约束>
- <不得修改的文件>
- <接口兼容性要求>
```

## 5. change_summary.md 模板

```markdown
# 变更摘要

任务编号: <task_id>
Agent: <agent_name>
日期: <date>

## 新增文件

- <文件路径>: <一句话说明>

## 修改文件

- <文件路径>: <修改了什么>

## 删除文件

- <无 / 文件路径>

## 关键实现说明

<2-5 句说明核心实现思路>

## 已知限制

- <限制 1>
- <限制 2>
```

## 6. evidence_index.md 模板

```markdown
# 证据索引

任务编号: <task_id>

## 测试运行

| 测试编号 | 结果 | summary 路径 | assertions 路径 |
| --- | --- | --- | --- |
| L1-3 | PASS | logs/test_runs/.../summary.json | logs/test_runs/.../assertions.json |
| L1-4 | PASS | logs/test_runs/.../summary.json | logs/test_runs/.../assertions.json |

## 可视化证据

| 文件 | 路径 | 说明 |
| --- | --- | --- |
| debug_video.mp4 | logs/test_runs/.../debug_video.mp4 | 机器人绕行全过程 |
| debug_topdown.png | logs/test_runs/.../debug_topdown.png | 俯视轨迹 |
| debug_timeline.png | logs/test_runs/.../debug_timeline.png | 状态时间轴 |

## 地图证据（探索场景）

| 文件 | 路径 |
| --- | --- |
| manifest.json | maps/test_site/manifest.json |
| snapshot | maps/test_site/snapshots/v5/ |

## 复现方式

```bash
pytest tests/sim2d/test_<scenario>.py --seed=42
```

## 哪些测试通过

- <列表>

## 哪些测试失败

- <列表，含失败原因>
```

## 7. Kimi 验收输出模板

Kimi 必须按以下格式输出验收意见：

```markdown
# Kimi Acceptance Review

## 结论

PASS / FAIL

## 验收范围

- 任务编号: <task_id>
- 测试层级: <L0/L1/...>
- 测试编号: <编号列表>

## 通过项

- <编号>: <一句话说明>

## 阻塞问题

| 编号 | 问题 | 证据 | 必须修改 |
| --- | --- | --- | --- |
| KIMI-BLOCK-1 | <问题描述> | <在哪个文件/截图中发现> | 是 |

## 非阻塞建议

- <建议 1>
- <建议 2>

## 需要补充的证据

- <缺少什么>

## 返工分派建议

- Agent: <owner_agent>
- 文件: <需要修改的文件>
- 测试: <需要重新跑的测试编号>

## 复验范围

- <只需复验的测试编号>
```

## 8. 返工任务模板

Kimi 判定 FAIL 后，Main Agent 使用此模板创建返工任务：

```yaml
parent_task_id: <原任务编号>
rework_id: REWORK-<序号>
source: Kimi Acceptance Review
blocking_issue: KIMI-BLOCK-<编号>
owner_agent: <agent_name>
required_fix: <一句话说明要修什么>
must_rerun:
  - <测试编号>
  - <测试编号>
evidence_required:
  - <需要重新生成的证据文件>
deadline_phase: <当前 Phase>
```

## 9. 验收判定规则

### PASS 条件

- 所有 `assertions.json` 中的断言全部通过
- `debug_video.mp4` 或关键帧序列存在且内容与 summary 一致
- 不存在 severity=blocking 的问题
- 变更不违反接口契约

### FAIL 条件（任一触发）

- 存在至少一个 severity=blocking 的问题
- 缺少必要证据文件
- assertions 有失败项且未在 known_failures 中列出
- 变更违反接口契约或安全优先级
- `debug_video.mp4` 与 `summary.json` 结果不一致

### Kimi 不验收的情况

- 无 `summary.json` → 拒绝验收
- 无 `assertions.json` → 拒绝验收
- 无任何可视化证据 → 拒绝验收
- 证据包结构不符合本模板 → 退回要求补充

## 10. 验收闭环流程

```text
1. Owner Agent 完成实现
2. Test Runner Agent 执行测试并生成证据包
3. Main Agent 组装验收输入包
4. Kimi Acceptance Agent 按本模板验收
5. PASS → 任务关闭，进入下一阶段
6. FAIL → Main Agent 创建返工任务
7. Owner Agent 修复
8. Test Runner Agent 重跑失败范围
9. Kimi 只复验失败范围和相关回归项
10. 循环直到 PASS
```

Main Agent 不得直接修复 blocking issue，不得跳过 FAIL 进入下一 Phase。
