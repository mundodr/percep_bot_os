# 多 Agent 协同开发与验收工作流设计文档

## 1. 目标

本文档定义机器人导航系统的多 Agent 协同开发流程。

系统目标是把以下能力逐步实现成可仿真、可验收、可迭代的工程：

- 反应式局部导航
- 长距离路径规划与局部执行
- LingBot-Map 语义几何地图
- CLIP 语义目标匹配
- `qwen3-vl:4b` 大脑任务理解
- 探索建图与地图持久化
- Python 2D 仿真
- Webots 3D 仿真
- 自动化测试与验收证据包

多 Agent 协作原则：

```text
主 Agent 只做协调，不直接承担大量实现细节
各专业 Agent 只处理自己负责的子系统
Kimi Agent 只做验收和评审，不参与实现
验收不通过时，主 Agent 分派返工任务
所有 Agent 通过文档、接口、测试、证据包交接
避免把所有上下文塞进同一个 Agent，防止上下文污染
```

## 2. 总体流程

### 2.1 开发管线（PR 驱动）

每一个代码变更都走统一的 PR 流水线，禁止直推 main：

```text
用户需求 / 任务卡
  ↓
Main Orchestrator Agent 拆分 + 分派
  ↓
专业实现 Agent 在 feature branch 工作
  ↓
本地 verify.sh 通过
  ↓
git push → 开 PR (via REST API)
  ↓
CI 执行 verify.sh（lint + test + 仿真）
  ↓
Codex Cloud 自动 review
  ↓
Codex 给出 👍 reaction？（auto-merge.yml 轮询最多 30 min）
  ├─ 是：自动启用 auto-merge (squash + delete branch)
  │       等 CI 绿 + branch protection 满足 → 真正合并
  └─ 否（超时/有 P0）：人工介入或修复后重新触发
  ↓
集成 Agent 确认集成
  ↓
Test Runner Agent 生成证据包
  ↓
Kimi Acceptance Agent 验收
  ↓
通过？
  ├─ 是：生成验收报告，进入下一阶段
  └─ 否：输出验收意见，Main Agent 分派返工，开新 PR 循环
```

**合并门禁（三重条件同时满足才能合并）**：

```text
1. CI verify job 通过（branch protection required check）
2. Codex Cloud (chatgpt-codex-connector[bot]) 对 PR 给出 👍 reaction
3. Branch up to date with main
```

### 2.2 核心闭环

```text
Plan -> Branch -> Implement -> Verify -> PR -> CI + Codex Review -> Merge -> Integrate -> Simulate -> Evidence -> Kimi Review -> Fix -> Re-review
```

### 2.3 双层 Review 机制

| 层级 | 角色 | 时机 | 重点 |
| --- | --- | --- | --- |
| L1: 自动 | Codex GitHub App | 每个 PR 自动触发 | 代码安全、P0/P1 规则、接口兼容 |
| L2: 验收 | Kimi Acceptance Agent | Phase 验收节点 | 功能完整性、证据包、集成回归 |

Codex 关注**单 PR 级别**的代码质量；Kimi 关注**Phase 级别**的系统行为。

## 3. Agent 角色划分

### 3.1 Main Orchestrator Agent

职责：

- 接收用户目标
- 拆分长程任务
- 选择需要启动的专业 Agent
- 控制上下文边界
- 分配文件 ownership
- 维护任务状态看板
- 汇总各 Agent 输出
- **管理 PR 流水线**：确保每个变更走 branch → verify → PR → merge 流程
- **协调 Codex review 结果**：P0 阻塞必须修复后才能合并
- 决定何时进入 Kimi 验收
- 根据 Kimi 验收意见分派返工
- **输出人工待办清单**：需要用户在 GitHub 网页操作的设置（branch protection / auto-merge / Codex 配置）

禁止：

- 不直接写大段实现代码
- 不把所有子系统上下文混在一起
- 不替 Kimi 做最终验收
- 不跳过失败项进入下一阶段
- **不直推 main 分支**
- **不跳过 verify.sh**
- **不替用户做 GitHub 网页设置**

主 Agent 只保留高层状态：

```text
当前阶段
任务列表
接口契约
文件 ownership
PR 状态（open / merged / blocked）
CI 结论（pass / fail）
Codex review 结论（P0 / P1 / clean）
测试结果摘要
Kimi 验收结论
返工项
```

### 3.2 Architecture Agent

职责：

- 维护总体架构文档
- 定义模块边界
- 定义数据结构和接口契约
- 检查方案是否偏离非 ROS2 / 安全优先原则

输入：

- 需求摘要
- 现有设计文档
- 关键约束

输出：

```text
architecture_decision_record.md
interface_contracts.md
open_questions.md
```

### 3.3 Navigation Core Agent

职责：

- 实现 `ReactiveNavigator`
- 实现 `ObstacleScan` 工具函数
- 实现边缘跟随、急停、速度限幅
- 编写局部导航单元测试

文件 ownership：

```text
navigation_core/
tests/unit/test_navigation_*.py
```

不得修改：

```text
semantic_map/
brain/
map_store/
webots/
```

### 3.4 Route Manager Agent

职责：

- 实现简单全局路径规划器（A* / Dijkstra on occupancy grid），作为系统默认 planner
- 实现 planner 抽象接口 `PlannerClient`，支持替换为外部 planner
- 实现 mock planner，用于 L0-L2 测试（输出预定义 `GlobalRoute`）
- 实现 `GlobalRoute -> LocalSubgoal`
- 实现路径进度跟踪
- 实现 blocked corridor feedback
- 实现重规划请求接口

文件 ownership：

```text
global_navigation/
tests/unit/test_route_*.py
tests/unit/test_planner_*.py
```

### 3.5 Semantic Map Agent

职责：

- 实现 LingBot-Map prediction reader
- 实现 `prediction -> ObstacleScan`
- 实现 CLIP embedding cache
- 实现 `SemanticObject` 和 `SemanticGoal`
- 实现坐标变换服务（`map <-> base_link`、`map <-> camera`），作为 ROS TF 的轻量替代

文件 ownership：

```text
semantic_map/
navigation_core/transform_service.py
tests/unit/test_semantic_*.py
tests/unit/test_transform_*.py
tests/replay/test_lingbot_*.py
```

注意：

- CLIP 不允许参与安全距离判断
- 语义目标必须绑定有效 3D 几何

### 3.6 Brain Agent

职责：

- 接入 `qwen3-vl:4b`
- 构建 `BrainObservation`
- 校验 `BrainDecision`
- 实现 intent 白名单
- 实现 fallback 策略

文件 ownership：

```text
brain/
tests/unit/test_brain_*.py
```

禁止：

- 不允许输出或执行 `VelocityCommand`
- 不允许绕过 planner 和 navigator

### 3.7 Exploration Agent

职责：

- 实现 frontier 检测
- 实现 exploration target 评分
- 实现 coverage tracker
- 实现 failed / visited / low_gain frontier 状态

文件 ownership：

```text
exploration/
tests/exploration/
```

### 3.8 Map Store Agent

职责：

- 实现 `MapUpdate`
- 实现地图增量写入
- 实现 snapshot
- 实现 manifest
- 实现中断恢复
- 分离 static layer 和 dynamic layer

文件 ownership：

```text
map_store/
tests/unit/test_map_store_*.py
```

验收重点：

- atomic write
- versioned manifest
- snapshot rollback
- 动态障碍不能污染静态地图

### 3.9 Simulation Agent

职责：

- 实现 Python 2D simulator（世界模型、传感器模型、机器人模型）
- 实现测试场景定义（障碍布局、目标点、动态物体轨迹）
- 实现可视化渲染器（生成 `debug_video.mp4`、`debug_topdown.png`、`debug_timeline.png`）
- 实现 Web UI（Phase 5 半实时阶段）

不负责：

- 不负责自动化测试执行和报告生成（由 Test Runner Agent 负责）
- 不负责集成多模块 pipeline（由 Integration Agent 负责）
- 不直接修改 navigation_core / semantic_map / brain 的核心逻辑

文件 ownership：

```text
sim/
tests/sim2d/
tests/replay/
web_ui/
```

### 3.10 Webots Agent

职责：

- 搭建 Webots world
- 实现 Webots Python controller
- 导出 RGB / depth / lidar / pose
- 接入 `VelocityCommand`

文件 ownership：

```text
webots/
sim/worlds/
sim/controllers/
```

### 3.11 Integration Agent

职责：

- 编写集成层 glue code（模块间数据适配、配置加载、管线编排）
- 编写异步管线（帧队列、模型调度、延迟补偿 pipeline）
- 解决接口不匹配（类型转换、字段映射、坐标系对齐）
- 编写端到端集成测试用例

不负责：

- 不实现仿真器或可视化（由 Simulation Agent 负责）
- 不执行自动化测试或生成报告（由 Test Runner Agent 负责）
- 不直接重写专业 Agent 的核心逻辑
- 若发现模块 bug，提交返工任务给对应 Agent

文件 ownership：

```text
integration/
tests/integration/
config/
```

### 3.12 Test Runner Agent

职责：

- 执行 pytest（单元测试、集成测试、仿真测试）
- 驱动 Simulation Agent 实现的仿真器执行 L0-L5 场景
- 收集证据包（调用仿真器已生成的视频、截图、日志）
- 汇总 `summary.json` 和 `assertions.json`
- 确保每次 run 输出完整证据包

不负责：

- 不实现仿真器本身（由 Simulation Agent 负责）
- 不实现可视化渲染（由 Simulation Agent 负责）
- 不编写集成 glue code（由 Integration Agent 负责）
- 不直接修复测试中发现的 bug（提交返工任务给对应 Agent）

文件 ownership：

```text
tests/conftest.py
tests/test_runner/
logs/test_runs/
```

输出：

```text
logs/test_runs/<run_id>/
  summary.json
  assertions.json
  debug_video.mp4
  debug_topdown.png
  debug_timeline.png
  trajectory.csv
  commands.csv
  state_log.csv
  map_updates.jsonl
```

### 3.13 Codex Review Agent（自动化）

角色性质：**ChatGPT Codex Connector GitHub App**，非人工 Agent，PR 级自动触发。

职责：

- 每个 PR 自动触发 code review
- 按 P0/P1/P2/P3 严重程度分级
- P0 命中时在 PR 评论中标注 BLOCK
- P1 flag 但不阻塞合并
- P2/P3 不 flag

P0 规则（任何一项命中必须 BLOCK）：

```text
- 控制循环 / 实时 loop 里出现没有 timeout 的阻塞 IO
- VelocityCommand 发布前没有限幅（机器人失控风险）
- ObstacleScan 未扣除 footprint 直接用于安全判断
- 急停逻辑被移除或绕过
- secret / API key 写进代码或入 git
- 接口数据结构字段变更但下游未同步
- 类型标注与运行时实际类型不一致
```

P1 规则（flag 但不阻塞）：

```text
- 修改接口契约（向后不兼容）
- 修改默认配置参数
- 测试覆盖率明显下降
- 新增依赖但没有说明理由
- 修改状态机转移逻辑
```

P2/P3 不 flag：

```text
- 文档 typo
- 代码风格（让 lint 工具处理）
- import 顺序
- 注释措辞
```

Codex 反应语义：

| 反应 | 含义 | auto-merge 影响 |
| --- | --- | --- |
| 👍 (+1 reaction) | 看完没问题 | **触发 auto-merge.yml 启用自动合并** |
| 👀 (eyes reaction) | 开始 review，稍后贴评论 | 中间态，继续等待 |
| COMMENTED review | 发现问题，看 body 里的 P0/P1 列表 | 不给 👍 = 阻塞合并 |
| 无反应（30 min 超时） | Codex 未触发或配置问题 | auto-merge.yml 输出 notice，需人工介入 |

**关键**：`auto-merge.yml` 只在检测到 Codex 的 👍 后才执行 `gh pr merge --auto --squash --delete-branch`。没有 👍 = PR 不会被自动合并，即使 CI 全绿。

### 3.14 Kimi Acceptance Agent

职责：

- 独立验收（Phase 级别，非单 PR 级别）
- 阅读设计文档、测试报告和证据包
- 输出验收意见
- 判定通过 / 不通过
- 给出必须修改项

Kimi 只看证据，不参与实现。

输入：

```text
需求摘要
相关设计文档
接口契约
summary.json
assertions.json
debug 截图或视频摘要
测试日志摘要
本轮变更摘要
```

输出：

```text
kimi_acceptance_review.md
```

Kimi 输出格式：

```text
结论：PASS / FAIL

阻塞问题：
- ...

非阻塞建议：
- ...

必须补充的证据：
- ...

建议返工 Agent：
- Navigation Core Agent
- Simulation Agent

复验范围：
- L1-2
- L4-6
```

## 4. Ship 流水线（每个 PR 必须遵循）

### 4.1 统一开发流程（11 步）

每个 Agent 提交代码变更时，严格走以下流程：

```text
Step 1:  从 main 新建 feature branch
         命名: <type>/<scope>-<brief>
         示例: feat/nav-edge-follow, fix/obstacle-inflation, test/l1-sim

Step 2:  实现代码 + 本地单元测试

Step 3:  执行 bash scripts/verify.sh
         必须 ALL OK 才能继续

Step 4:  git add 必要文件（排除 secret / log / __pycache__）

Step 5:  git commit
         格式: <type>(<scope>): <description>
         示例: feat(nav): implement edge follow controller

Step 6:  git push -u origin <branch>

Step 7:  通过 REST API 创建 PR
         （避免 GraphQL 索引延迟导致 "No commits between..." 错误）

Step 8:  等待 CI 跑完
         - 若失败：本地修复 → 再 push → CI 重跑
         - 若成功：继续

Step 9:  等待 Codex Cloud review + 👍 reaction
         auto-merge.yml 自动轮询（30s 间隔，最多 30 min）
         - Codex 给 👍：auto-merge.yml 自动执行 gh pr merge --auto --squash --delete-branch
         - Codex 给 COMMENTED review 有 P0：必须修复 → 新 commit → push → 等重审
         - 超时无反应：手动触发 workflow_dispatch 重试，或检查 Codex 配置

Step 10: PR merged（CI 绿 + Codex 👍 + branch up to date 三重条件满足后自动合并）

Step 11: 确认 main 更新 → 汇报完成
```

### 4.2 verify.sh — 唯一验证真相源

所有本地验证和 CI 都通过同一个 `scripts/verify.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== verify.sh @ $REPO_ROOT ==="

echo ">>> [1/4] 依赖安装"
pip install -e ".[dev]" -q

echo ">>> [2/4] lint (ruff)"
ruff check .

echo ">>> [3/4] 类型检查 (mypy, 非阻塞)"
mypy --ignore-missing-imports navigation_core/ || true

echo ">>> [4/4] 测试 (pytest)"
pytest tests/ -q --maxfail=10

echo "================================================================"
echo " verify.sh: ALL OK"
echo "================================================================"
```

规则：
- CI 失败时**修代码**，禁止修改 verify.sh "放水"
- 新模块加入后必须同步更新 verify.sh 的检查范围
- verify.sh 是 CI workflow 的唯一调用入口

### 4.3 CI/CD 配置

本项目使用两个 GitHub Actions workflow 协同工作：

**Workflow 1: `.github/workflows/ci.yml`（验证）**

```yaml
name: ci

on:
  pull_request:
  push:
    branches: [main]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run unified verify
        run: bash ./scripts/verify.sh
```

**Workflow 2: `.github/workflows/auto-merge.yml`（Codex 门禁 + 自动合并）**

核心逻辑（详见 `docs/auto-merge.yml`）：

```text
触发时机：PR opened/synchronize/reopened、review submitted、comment created、手动 dispatch
    ↓
解析 PR 号 + 获取 PR metadata
    ↓
轮询 Codex Cloud (chatgpt-codex-connector[bot]) 的 👍 reaction
  - 检查范围：PR description reactions + issue comments reactions + review comments reactions
  - 轮询策略：30s 间隔，最多 60 次 = 30 min
    ↓
发现 👍 → gh pr merge --auto --squash --delete-branch
超时无 👍 → 输出 notice，等人工介入或手动 re-run
```

关键设计点：
- GitHub Actions 没有 reaction 事件，所以 auto-merge.yml 在每次 PR 事件触发时轮询
- `chatgpt-codex-connector[bot]` 的 👍 可以出现在 PR description、评论、或 review comment 的 reaction 上
- 支持 `workflow_dispatch` 手动重跑（输入 PR number）
- concurrency group 保证同一 PR 只有一个轮询实例

**Branch protection 要求：**

```text
- 必须 PR（禁止直推 main）
- 必须 CI 绿（required check: "verify"）
- Require branches to be up to date before merging
- Do not allow bypassing（admin 也走流程）
- Allow auto-merge + Automatically delete head branches
```

**合并三重门禁（缺一不合）：**

```text
1. CI verify job PASS        ← branch protection 强制
2. Codex Cloud 👍 reaction   ← auto-merge.yml 检测后才启用 auto-merge
3. Branch up to date         ← branch protection 强制
```

### 4.4 PR 模板

`.github/PULL_REQUEST_TEMPLATE.md`：

```markdown
## 变更说明

<!-- 简述本 PR 做了什么 -->

## 关联任务

<!-- 任务 ID，如 NAV-L1-EDGE-FOLLOW-001 -->

## 测试

- [ ] `bash scripts/verify.sh` 本地通过
- [ ] 相关单元测试已添加/更新
- [ ] 无新增 P0 级安全隐患

## 证据

<!-- 贴截图、日志摘要或指向 logs/ 下的文件 -->
```

### 4.5 已知坑速查表

| # | 症状 | 修法 |
| --- | --- | --- |
| 1 | `gh pr create` 报 "No commits between..." | 改用 REST API: `gh api repos/.../pulls -X POST` |
| 2 | PR 秒合，Codex 来不及 review | 有 auto-merge.yml 后不会发生（必须等 👍）；若绕过了检查 branch protection 是否生效 |
| 3 | branch protection contexts 空集 | 必须在设置页搜索框真把 job name 加进去 |
| 4 | enforce_admins=false，owner 绕过保护 | 勾 "Do not allow bypassing" |
| 5 | pre-commit 首次大量 auto-format | baseline 时先跑一次 format 全量提交 |
| 6 | verify.sh CI 容器依赖安装慢 | 用 pip cache 或 setup-python cache |
| 7 | auto-merge.yml 30 min 超时无 👍 | 检查 Codex 后台是否对本仓库开启了 review；手动 `workflow_dispatch` 重跑 |
| 8 | auto-merge.yml 同一 PR 多次触发 | 正常行为（concurrency group 保证只有一个实例在跑） |
| 9 | Codex 给了 COMMENTED review 但没给 👍 | 说明有 P0/P1 问题，必须修复后等 Codex 重审并给 👍 |

## 5. 上下文隔离策略

### 5.1 每个 Agent 只拿最小上下文

Main Agent 给子 Agent 的输入必须裁剪。

示例：

```text
Navigation Core Agent 只需要：
  reactive_navigation_design.md 相关章节
  navigation_core 接口契约
  L0/L1 测试要求

不需要：
  qwen3-vl prompt
  CLIP embedding 细节
  Webots world 细节
```

### 5.2 用接口契约代替全文上下文

不同 Agent 通过稳定接口协作：

```text
BrainDecision
GlobalRoute
ExploreRoute
LocalSubgoal
ObstacleScan
VelocityCommand
MapUpdate
SemanticObject
SavedMapManifest
```

任何 Agent 修改接口，必须提交：

```text
interface_change_request.md
```

由 Main Agent 协调所有受影响 Agent。

### 5.3 文件 Ownership

每个文件只能有一个 owner Agent。

非 owner Agent 发现问题时，只能：

```text
1. 写 issue
2. 写建议 patch
3. 请求 owner Agent 修改
```

不得直接跨边界大改。

### 5.4 Handoff Brief

每个 Agent 交付时必须写简短交接说明：

```text
handoff/<agent_name>_<task_id>.md
```

内容：

```text
完成了什么
修改了哪些文件
如何运行测试
已知限制
需要下游 Agent 注意什么
```

## 6. 长程任务状态机

每个任务都有状态：

```text
BACKLOG
READY
ASSIGNED
IN_PROGRESS
BLOCKED
IMPLEMENTED
INTEGRATING
TESTING
KIMI_REVIEW
FAILED_REVIEW
REVISING
ACCEPTED
DONE
```

状态流转：

```text
READY
  ↓
ASSIGNED
  ↓
IN_PROGRESS
  ↓
IMPLEMENTED
  ↓
TESTING
  ↓
KIMI_REVIEW
  ↓
PASS -> ACCEPTED -> DONE
  ↓
FAIL -> FAILED_REVIEW -> REVISING -> TESTING
```

## 7. 任务分解模板

Main Agent 创建任务时使用：

```yaml
task_id: NAV-L1-EDGE-FOLLOW-001
title: 实现边缘跟随 L1 场景
owner_agent: Navigation Core Agent
review_agent: Kimi Acceptance Agent
priority: high
scope:
  files:
    - navigation_core/reactive_navigator.py
    - tests/unit/test_edge_follow.py
context:
  required_docs:
    - reactive_navigation_design.md
    - simulation_acceptance_test_plan.md
interfaces:
  input:
    - LocalSubgoal
    - ObstacleScan
  output:
    - VelocityCommand
acceptance:
  tests:
    - L0-4
    - L1-3
    - L1-4
  evidence:
    - assertions.json
    - debug_video.mp4
    - state_log.csv
constraints:
  - 不修改 semantic_map/
  - 不绕过速度限幅
  - 不移除急停逻辑
```

## 8. Kimi 验收流程

### 8.1 进入 Kimi 验收前置条件

必须满足：

- 相关自动测试已经执行
- 证据包存在
- `summary.json` 存在
- `assertions.json` 存在
- 变更摘要存在
- 已知失败项已列出

没有证据包不得送 Kimi 验收。

### 8.2 Kimi 验收输入包

目录：

```text
acceptance_packages/
  <task_id>/
    requirement.md
    change_summary.md
    interface_contracts.md
    test_summary.md
    summary.json
    assertions.json
    evidence_index.md
    screenshots/
    logs_excerpt/
```

`evidence_index.md` 必须说明：

```text
debug_video.mp4 在哪里
debug_topdown.png 在哪里
地图 snapshot 在哪里
如何复现
哪些测试通过
哪些测试失败
```

### 8.3 Kimi 验收意见模板

```markdown
# Kimi Acceptance Review

## 结论

PASS / FAIL

## 验收范围

- ...

## 通过项

- ...

## 阻塞问题

| 编号 | 问题 | 证据 | 必须修改 |
| --- | --- | --- | --- |
| KIMI-BLOCK-1 | ... | ... | ... |

## 非阻塞建议

- ...

## 需要补充的证据

- ...

## 返工分派建议

- Agent:
- 文件:
- 测试:

## 复验范围

- ...
```

### 8.4 不通过时的返工规则

Kimi 判定 `FAIL` 后：

```text
1. Main Agent 不直接修
2. Main Agent 把阻塞问题拆成返工任务
3. 分派给对应 owner Agent
4. owner Agent 修改
5. Test Runner Agent 重新跑相关测试
6. Kimi 只复验失败范围和相关回归项
```

返工任务模板：

```yaml
parent_task_id: NAV-L1-EDGE-FOLLOW-001
rework_id: REWORK-001
source: Kimi Acceptance Review
blocking_issue: KIMI-BLOCK-1
owner_agent: Simulation Agent
required_fix: debug_video 缺少 ObstacleScan 可视化
must_rerun:
  - L1-3
  - L1-4
evidence_required:
  - debug_video.mp4
  - debug_topdown.png
  - assertions.json
```

## 9. 防止上下文污染的具体规则

### 9.1 不共享完整聊天历史

子 Agent 不继承完整上下文，只接收：

```text
任务卡
相关接口
相关文件
相关测试
必要设计摘录
```

### 9.2 不让实现 Agent 看 Kimi 内部推理

实现 Agent 只看 Kimi 的结论和阻塞项，不看无关讨论。

### 9.3 不把探索、语义、大脑、底盘混成一个任务

错误任务：

```text
实现完整机器人导航系统
```

正确拆分：

```text
实现 ObstacleScan 生成
实现 BrainDecision schema
实现 frontier detector
实现 L1-3 场景
实现 MapUpdate 持久化
```

### 9.4 子 Agent 输出必须结构化

每个 Agent 输出：

```text
files_changed
tests_run
evidence
open_issues
handoff_notes
```

不得只输出“已完成”。

## 10. Agent 间通信协议

### 10.1 Issue 格式

```yaml
issue_id: ISSUE-SEMANTIC-003
reported_by: Integration Agent
owner_agent: Semantic Map Agent
severity: blocking
summary: SemanticObject 缺少 position_robot
evidence:
  - tests/integration/test_semantic_route.py failed
expected:
  - SemanticObject 必须提供 map 和 robot 两种坐标
```

### 10.2 Handoff 格式

```yaml
task_id: MAP-L4-PERSIST-001
agent: Map Store Agent
status: implemented
files_changed:
  - map_store/persistent_map.py
  - tests/unit/test_map_store.py
tests_run:
  - pytest tests/unit/test_map_store.py
evidence:
  - logs/test_runs/L4-6/summary.json
known_limits:
  - 当前只支持 occupancy_grid
next_agent_notes:
  - Simulation Agent 可调用 save_update(update)
```

### 10.3 验收包索引

```markdown
# Evidence Index

Task: MAP-L4-PERSIST-001

## Test Runs

- L4-6 snapshot recovery:
  - summary: logs/test_runs/.../summary.json
  - assertions: logs/test_runs/.../assertions.json
  - video: logs/test_runs/.../debug_video.mp4

## Map Artifacts

- manifest: maps/test_site/manifest.json
- snapshot: maps/test_site/snapshots/v5/

## Reproduce

```bash
pytest tests/exploration/test_snapshot_recovery.py
```
```

## 11. 进度汇报与审核记录

### 11.1 每 5 分钟进度汇报

所有 Agent（含 Main Orchestrator）在执行任务期间，**每 5 分钟写一次进度快照**到 `logs/progress/` 目录：

文件命名：

```text
logs/progress/<date>_<time>_<agent_name>.md
示例: logs/progress/20260511_1735_navigation_core.md
```

进度文件内容模板：

```markdown
# 进度汇报

- 时间: 2026-05-11 17:35:00
- Agent: Navigation Core Agent
- 任务: NAV-L1-EDGE-FOLLOW-001
- 状态: IN_PROGRESS

## 当前进展

- [x] 边缘跟随方向选择逻辑
- [x] 距离误差 PD 控制
- [ ] 退出条件判断（进行中）
- [ ] 失败检测

## 本轮完成项

- 实现了 compute_edge_follow_command()
- 通过了 test_bypass_side_selection 3 个用例

## 阻塞 / 风险

- 无

## 下一步（未来 5 分钟）

- 实现 edge follow 退出条件
- 编写 test_edge_exit 用例

## 文件变更

- navigation_core/reactive_navigator.py (modified)
- tests/unit/test_edge_follow.py (new)
```

规则：

```text
1. 每 5 分钟必须写一次，即使进展为零也要汇报（写"无进展，原因：xxx"）
2. 文件追加写入 logs/progress/，不删除历史记录
3. Main Agent 每 5 分钟汇总所有子 Agent 最新进度，输出一份汇总
4. 用户可随时 ls logs/progress/ 查看各 Agent 当前状态
5. 连续 3 次"无进展"触发 Main Agent 介入检查是否卡住
```

汇总文件（Main Agent 写）：

```text
logs/progress/<date>_<time>_summary.md
```

汇总模板：

```markdown
# 全局进度汇总

- 时间: 2026-05-11 17:35:00
- Phase: 1 (L0/L1 仿真)

| Agent | 任务 | 状态 | 最近更新 | 阻塞 |
| --- | --- | --- | --- | --- |
| Navigation Core | NAV-L1-001 | IN_PROGRESS | 17:35 | 无 |
| Simulation | SIM-L1-001 | IN_PROGRESS | 17:30 | 等 nav 接口 |
| Test Runner | TEST-L1-001 | READY | — | 等实现完成 |

## PR 状态

| PR | 分支 | CI | Codex | 合并 |
| --- | --- | --- | --- | --- |
| #3 | feat/nav-edge-follow | ✅ pass | 👍 | ✅ merged |
| #4 | feat/sim-world | 🔄 running | ⏳ | ⏳ pending |

## 风险项

- Simulation Agent 等待 navigation_core 接口稳定
```

### 11.2 Kimi 审核记录

每次 Kimi 验收（不论 PASS 或 FAIL）都必须**持久化记录**到 `logs/kimi_reviews/` 目录：

文件命名：

```text
logs/kimi_reviews/<task_id>_<date>_<sequence>.md
示例: logs/kimi_reviews/NAV-L1-001_20260511_01.md
      logs/kimi_reviews/NAV-L1-001_20260511_02.md  (同任务第二次复审)
```

记录内容（完整保留 Kimi 输出 + 元数据）：

```markdown
# Kimi 审核记录

## 元数据

- 任务: NAV-L1-EDGE-FOLLOW-001
- 审核时间: 2026-05-11 18:00:00
- 审核轮次: 第 1 轮
- 触发者: Main Orchestrator Agent
- 输入证据包: acceptance_packages/NAV-L1-001/

## Kimi 原始输出

结论：FAIL

### 阻塞问题

| 编号 | 问题 | 证据 | 必须修改 |
| --- | --- | --- | --- |
| KIMI-BLOCK-1 | 边缘跟随退出条件未实现 | assertions.json L1-3 FAIL | 是 |

### 非阻塞建议

- debug_video 建议加入 obstacle_side_distance 实时数值叠加

### 需要补充的证据

- L1-4 场景的 state_log.csv

### 返工分派

- Agent: Navigation Core Agent
- 文件: navigation_core/reactive_navigator.py
- 测试: L1-3, L1-4

### 复验范围

- L1-3, L1-4

## 后续动作

- [x] Main Agent 已分派返工任务 REWORK-001
- [ ] Navigation Core Agent 修复中
- [ ] 待复审
```

规则：

```text
1. 每次送审必须记录，即使是快速 PASS 也要有记录
2. 同一任务多次审核用序号区分（_01, _02, _03...）
3. 记录不可修改，只能追加新文件
4. Main Agent 在分派返工前必须先写完审核记录
5. 复审时 Kimi 可以引用上一轮记录的编号（如 "KIMI-BLOCK-1 已修复"）
```

### 11.3 日志目录结构

```text
logs/
├── progress/                          # 每 5 分钟进度快照
│   ├── 20260511_1730_navigation_core.md
│   ├── 20260511_1730_simulation.md
│   ├── 20260511_1730_summary.md
│   ├── 20260511_1735_navigation_core.md
│   └── ...
├── kimi_reviews/                      # Kimi 审核记录（不可变）
│   ├── NAV-L1-001_20260511_01.md
│   ├── NAV-L1-001_20260511_02.md
│   └── ...
└── test_runs/                         # 测试运行证据包（已有）
    └── <run_id>/
        ├── summary.json
        ├── assertions.json
        └── ...
```

## 12. 长程任务执行节奏

推荐节奏：

```text
Phase 0: 文档与接口冻结
Phase 1: L0 单元测试 + L1 2D 局部导航
Phase 2: L2 长距离路径回放
Phase 3: L3 语义几何回放
Phase 4: L4 探索建图持久化
Phase 5: 半实时集成（异步管线 + Web UI + 延迟补偿）
Phase 6: L5 Webots 3D 闭环
Phase 7: 低速真机准备
```

每个 Phase 的规则：

```text
1. Main Agent 创建 Phase plan
2. 分派给专业 Agent
3. 专业 Agent 完成实现和本地测试
4. Integration Agent 集成
5. Test Runner Agent 生成证据包
6. Kimi Acceptance Agent 验收
7. 不通过则返工
8. 通过后进入下一 Phase
```

### 12.1 用户持续沟通机制

开发过程中用户**随时可以介入**，不需要等到 Phase 结束。沟通方式：

```text
┌─────────────────────────────────────────────────────────────┐
│  用户在任何时刻都可以：                                        │
│                                                             │
│  1. 直接对话    → Agent 立即响应，暂停当前任务处理用户指令       │
│  2. 修改需求    → Main Agent 重新评估任务拆分，通知受影响 Agent  │
│  3. 调整优先级  → 重排任务队列，变更当前 focus                  │
│  4. 质疑方向    → Agent 暂停实现，切入 Plan 模式讨论             │
│  5. 紧急叫停    → 所有 Agent 停止当前工作，保存进度快照          │
│  6. 查看进度    → 直接读 logs/progress/ 最新文件                │
│  7. 插入临时任务 → Main Agent 评估是否打断当前工作或排队等待     │
└─────────────────────────────────────────────────────────────┘
```

**响应优先级**（用户消息 > 计划内任务）：

| 用户动作 | Agent 响应 | 时间要求 |
| --- | --- | --- |
| 直接提问 / 对话 | 立即回答，当前任务暂停 | 即时 |
| 修改需求 | 评估影响范围，提出调整方案 | 1 轮对话内 |
| 紧急叫停 | 停止所有工作，写进度快照，等待指示 | 即时 |
| 方向质疑 | 暂停实现，列出当前方案 vs 替代方案 | 即时 |
| 插入临时任务 | 评估紧急度，建议"立即做"或"排队" | 即时 |

**沟通记录**：

用户与 Agent 之间的关键决策对话也记录到 `logs/progress/`，使用特殊前缀：

```text
logs/progress/<date>_<time>_user_decision.md
```

内容：

```markdown
# 用户决策记录

- 时间: 2026-05-11 17:45:00
- 上下文: 用户对边缘跟随方向提出新想法

## 用户原话

"绕行方向优先选目标同侧，不要用 clearance 比较"

## Agent 理解

修改 8.1 节绕行方向选择策略，从 clearance 比较优先改为目标侧偏好优先

## 决策

- [x] 用户确认理解正确
- 影响范围: navigation_core/reactive_navigator.py
- 需要重跑测试: L1-3, L1-4, L1-5

## 后续动作

- Navigation Core Agent 修改 bypass_side 选择逻辑
- 开新 PR: fix/nav-bypass-side-priority
```

**核心原则**：

```text
- Agent 不是黑盒。用户随时可以打断、提问、改方向。
- 用户的即时反馈 > 计划内的下一个任务。
- 每次用户改变方向，记录决策理由，避免后续"为什么这样做"的困惑。
- Agent 不需要用户许可才能汇报——主动汇报（每 5 分钟进度 + 关键节点即时通知）。
- 用户不在线时，Agent 按既定计划推进；用户回来时，先看 logs/progress/ 最新汇总再继续。
```

### 12.2 不打断用户原则

**Agent 执行期间禁止反向询问用户。** 遇到问题自行决策并记录：

```text
┌─────────────────────────────────────────────────────────────┐
│  禁止：                                                      │
│  - "请问您想用方案 A 还是方案 B？"                             │
│  - "这个参数应该设多少？"                                     │
│  - "需要我先做 X 还是先做 Y？"                                │
│  - 任何形式的阻塞式提问等待用户回复                            │
│                                                             │
│  正确做法：                                                   │
│  - 自行判断 → 选择最合理方案 → 执行 → 记录决策理由             │
│  - 遇到无法自行决策的重大分歧 → 记录到日志 → 按保守方案继续    │
│  - 用户有意见会主动来说                                       │
└─────────────────────────────────────────────────────────────┘
```

**遇到问题的处理流程**：

```text
问题出现
  ↓
能自己解决？
  ├─ 是：直接解决 → 记录到进度快照的"本轮解决的问题"
  └─ 否：
       ↓
     是否阻塞当前任务？
       ├─ 否：记录到 open_issues → 继续其他工作
       └─ 是：
            ↓
          选择保守/安全方案先推进
          记录到 logs/progress/ 中标注 ⚠️ 待确认
          用户看到后会主动沟通
```

**决策记录格式**（写在进度快照中）：

```markdown
## ⚠️ 自主决策（待用户确认）

- 问题: 边缘跟随 lost_distance 阈值不确定，文档说 1.2m 但实测似乎偏大
- 决策: 先用文档值 1.2m，后续可调
- 理由: 保守方案，不影响安全性
- 如需修改: 用户告知即可，改动成本低（单参数）
```

**硬性规定**：

```text
1. 不问。有问题自己判断，记录理由。
2. 不等。不因为"不确定"停下来等用户回复。
3. 不猜用户想法。按文档 + 设计原则 + 安全优先做决策。
4. 用户有意见会主动来说。收到用户反馈后立即调整。
5. 重大决策（影响架构/接口/安全）写入日志并标注 ⚠️，方便用户事后审阅。
```

## 13. 第一阶段 Agent 分派建议

### Phase 0：接口冻结

| 任务 | Agent | 输出 |
| --- | --- | --- |
| 整理数据结构 | Architecture Agent | `interface_contracts.md` |
| 定义 BrainDecision schema 与 intent 白名单 | Brain Agent | `brain_decision_schema.py` |
| 统一 LocalGoal / LocalSubgoal 接口 | Architecture Agent | `interface_contracts.md` 更新 |
| 定义坐标变换服务接口 | Architecture Agent | `interface_contracts.md` 更新 |
| 整理验收场景 | Test Runner Agent | `test_matrix.md` |
| 整理 Kimi 验收模板 | Main Agent | `acceptance_template.md` |

### Phase 1：L0/L1 仿真

| 任务 | Agent | 输出 |
| --- | --- | --- |
| 实现 navigation core | Navigation Core Agent | `reactive_navigator.py` |
| 实现 BrainDecision schema 校验与 mock brain | Brain Agent | `brain_decision_schema.py` / `tests/unit/test_brain_schema.py` |
| 实现 2D simulator | Simulation Agent | `sim2d_world.py` |
| 实现测试报告生成 | Test Runner Agent | `summary.json` / `assertions.json` |
| 验收 L0/L1 | Kimi Acceptance Agent | `kimi_acceptance_review.md` |

### Phase 2：长距离路径

| 任务 | Agent | 输出 |
| --- | --- | --- |
| 实现 Route Manager | Route Manager Agent | `route_manager.py` |
| 实现 route replay | Simulation Agent | `run_route_replay.py` |
| 集成导航与 route | Integration Agent | integration test |
| 验收 L2 | Kimi Acceptance Agent | review |

### Phase 3：语义几何

| 任务 | Agent | 输出 |
| --- | --- | --- |
| LingBot prediction reader | Semantic Map Agent | `lingbot_prediction_reader.py` |
| CLIP encoder | Semantic Map Agent | `clip_encoder.py` |
| qwen3-vl BrainDecision | Brain Agent | `brain_orchestrator.py` |
| 验收 L3 / Brain | Kimi Acceptance Agent | review |

### Phase 4：探索保存

| 任务 | Agent | 输出 |
| --- | --- | --- |
| Frontier detector | Exploration Agent | `frontier_detector.py` |
| Map persistence | Map Store Agent | `persistent_map.py` |
| Exploration replay | Simulation Agent | `run_exploration_replay.py` |
| 验收 L4 | Kimi Acceptance Agent | review |

### Phase 5：半实时集成

| 任务 | Agent | 输出 |
| --- | --- | --- |
| 异步管线与帧队列 | Integration Agent | `async_pipeline.py` |
| 推理延迟补偿与最新帧丢弃 | Semantic Map Agent | `frame_queue.py` |
| 简单 Web UI 可视化 | Simulation Agent | `web_ui/` |
| 地图层超时停车验证 | Test Runner Agent | `summary.json` / `assertions.json` |
| 验收半实时 | Kimi Acceptance Agent | review |

## 14. 通过标准

多 Agent 流程本身通过需要满足：

- 每个任务有明确 owner
- **每个代码变更通过独立 PR 合入 main**
- **每个 PR 经过 CI 绿 + Codex review 无 P0**
- 每个任务有测试和证据包
- Kimi 验收意见被记录
- Kimi 不通过时有返工任务
- 返工后重新生成证据包
- 主 Agent 没有直接吞掉失败项
- 子 Agent 没有跨 ownership 大改
- **没有任何直推 main 的 commit**
- **verify.sh 未被修改为放水**
- 长程任务状态可追踪

## 15. Agent 硬性纪律（违反即停）

所有 Agent（含 Main Orchestrator）必须遵守以下纪律，任何一条违反立即停止当前操作：

```text
1. 不直推 main。一律 feature branch + PR + auto-merge。
2. 不跳过 verify.sh。CI 失败先修代码，禁止改 verify.sh 让它放水。
3. 不替用户点 GitHub 网页设置。把待办清单写好让用户自己操作。
4. 不 git push --force 到任何被引用的远端分支。
5. 不把 secret 入仓库。.env / token / API key 全在 .gitignore。
6. 不批量重构无关代码。聚焦原则，一发 PR 一件事。
7. 不跨 ownership 大改。发现他人模块问题只能写 issue，不能直接动手。
8. 不让 Kimi 等空证据包。没有证据包不得送 Kimi 验收。
9. 每完成一阶段必须汇报 + 等用户确认。不得一口气跑完多个 Phase 无人监督。
10. 不让 PR 秒合。确保 CI 流程 > 90 秒，给 Codex 反应时间。
11. 每 5 分钟必须写进度快照到 logs/progress/。连续无进展必须说明原因。
12. 每次 Kimi 审核（含 PASS）必须写记录到 logs/kimi_reviews/，不可事后补。
13. 不删除、不修改已有的进度快照和审核记录文件。日志只追加不改。
14. 不打断用户。遇到问题自行决策 + 记录理由，不得阻塞等待用户回复。
```

违反处理：

```text
- Main Agent 发现子 Agent 违纪 → 驳回 PR + 记录违规
- 用户发现 Main Agent 违纪 → 停止当前 Phase，回退到上一个稳定状态
- 连续 2 次违纪 → 该 Agent 任务降级为手动监督模式
```

## 16. 完成定义（Definition of Done）

整个流水线配通的标志（所有条件同时满足）：

```text
- [ ] scripts/verify.sh 本地 ALL OK
- [ ] .github/workflows/ci.yml 调用 verify.sh 作为唯一验证入口
- [ ] .github/workflows/auto-merge.yml 就位（轮询 Codex 👍 → 启用 auto-merge）
- [ ] Branch protection 已设：required check = "verify"，enforce_admins = true
- [ ] GitHub 仓库设置：Allow auto-merge 已勾选 + Automatically delete head branches 已勾选
- [ ] Codex Cloud (chatgpt-codex-connector) 已对本仓库开启自动 review
- [ ] .github/PULL_REQUEST_TEMPLATE.md 就位
- [ ] 至少跑通 1 个完整 demo PR：
      branch → verify → push → PR → CI 绿 → Codex 👍 → auto-merge.yml 启用合并 → squash merged
- [ ] demo PR 上能看到 chatgpt-codex-connector[bot] 的 👍 reaction 或 COMMENTED review
- [ ] Kimi 验收模板和证据包目录结构已定义
- [ ] 所有 Agent 的 file ownership 已分配
- [ ] AGENTS.md 末尾追加了 Pipeline rules + Codex review guidelines
```

## 17. 结论

该多 Agent 协作方式的核心是：

```text
Main Agent 管流程，不塞满上下文；
专业 Agent 管实现，不越界；
每次改动走 PR 流水线，不直推 main；
CI + verify.sh 是唯一验证真相源；
Codex 管单 PR 级代码安全（自动、快速）；
Test Runner 管证据，不口头通过；
Kimi 管 Phase 级系统验收（全面、深入）；
不通过就返工，直到证据包和验收意见都通过。
```

双层 Review 保障：

```text
L1 (Codex): 每个 PR → 自动触发 → P0/P1 拦截 → 30-90s 内反应
L2 (Kimi):  每个 Phase → 手动送审 → 功能完整性 + 回归验证 → 结构化意见
```

这样可以把长程机器人导航开发拆成可控的小闭环，每次代码变更都有 CI 保护和自动 review，每个阶段都有可复现的验收依据，减少上下文污染的同时保证代码质量持续可控。
