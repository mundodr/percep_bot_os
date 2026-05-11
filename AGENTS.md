# AGENTS.md — percep_bot_os 多 Agent 协同规范

## 项目概述

percep_bot_os 是一个**非 ROS2 的轻量机器人感知导航操作系统**。采用 Python 单进程多线程模块化架构，内置 Web UI 管理界面，支持反应式局部导航、全局路径规划、语义地图、探索建图、大脑决策等子系统。

核心理念：
- 一条命令启动全部模块：`python -m percep_bot_os`
- 浏览器打开即可监控和管理所有模块
- 框架代码 ~1000 行，保持极简

## Agent 角色与 File Ownership

### Main Orchestrator Agent
- 职责：任务拆分、分派、流程控制、PR 流水线管理
- 禁止：不直接写大段实现代码、不直推 main

### Architecture Agent
- Ownership: `docs/interface_contracts.md`, `docs/architecture_*.md`
- 职责：维护架构文档、接口契约

### Navigation Core Agent
- Ownership: `navigation_core/`, `tests/unit/test_navigation_*.py`
- 禁止修改: `semantic_map/`, `brain/`, `map_store/`

### Route Manager Agent
- Ownership: `global_navigation/`, `tests/unit/test_route_*.py`, `tests/unit/test_planner_*.py`

### Semantic Map Agent
- Ownership: `semantic_map/`, `navigation_core/transform_service.py`, `tests/unit/test_semantic_*.py`, `tests/unit/test_transform_*.py`, `tests/replay/test_lingbot_*.py`

### Brain Agent
- Ownership: `brain/`, `tests/unit/test_brain_*.py`
- 禁止：不允许输出 VelocityCommand

### Exploration Agent
- Ownership: `exploration/`, `tests/exploration/`

### Map Store Agent
- Ownership: `map_store/`, `tests/unit/test_map_store_*.py`

### Simulation Agent
- Ownership: `sim/`, `tests/sim2d/`, `tests/replay/`, `web_ui/`

### Webots Agent
- Ownership: `webots/`, `sim/worlds/`, `sim/controllers/`

### Integration Agent
- Ownership: `integration/`, `tests/integration/`, `config/`

### Test Runner Agent
- Ownership: `tests/conftest.py`, `tests/test_runner/`, `logs/test_runs/`

### Codex Review Agent（自动化）
- 角色：ChatGPT Codex Connector GitHub App，每个 PR 自动触发 review

### Kimi Acceptance Agent
- 职责：Phase 级别独立验收，只看证据不参与实现

## Pipeline Rules（硬性纪律）

以下纪律所有 Agent 必须遵守，违反即停：

1. **不直推 main**。一律 feature branch + PR + auto-merge。
2. **不跳过 verify.sh**。CI 失败先修代码，禁止改 verify.sh 让它放水。
3. **不替用户点 GitHub 网页设置**。把待办清单写好让用户自己操作。
4. **不 git push --force** 到任何被引用的远端分支。
5. **不把 secret 入仓库**。.env / token / API key 全在 .gitignore。
6. **不批量重构无关代码**。聚焦原则，一发 PR 一件事。
7. **不跨 ownership 大改**。发现他人模块问题只能写 issue，不能直接动手。
8. **不让 Kimi 等空证据包**。没有证据包不得送 Kimi 验收。
9. **每完成一阶段必须汇报** + 等用户确认。
10. **不让 PR 秒合**。确保 CI 流程 > 90 秒，给 Codex 反应时间。
11. **每 5 分钟写进度快照**到 `logs/progress/`。
12. **每次 Kimi 审核必须写记录**到 `logs/kimi_reviews/`。
13. **不删改已有日志**。日志只追加不改。
14. **不打断用户**。遇到问题自行决策 + 记录理由。

## Codex Review Guidelines

### P0 规则（命中必须 BLOCK，PR 不可合并）

- 控制循环 / 实时 loop 里出现没有 timeout 的阻塞 IO
- VelocityCommand 发布前没有限幅（机器人失控风险）
- ObstacleScan 未扣除 footprint 直接用于安全判断
- 急停逻辑被移除或绕过
- secret / API key 写进代码或入 git
- 接口数据结构字段变更但下游未同步
- 类型标注与运行时实际类型不一致

### P1 规则（flag 但不阻塞）

- 修改接口契约（向后不兼容）
- 修改默认配置参数
- 测试覆盖率明显下降
- 新增依赖但没有说明理由
- 修改状态机转移逻辑

### P2/P3（不 flag）

- 文档 typo、代码风格、import 顺序、注释措辞（让 lint 工具处理）

## 关键约定

- **verify.sh 是唯一真相源**：所有本地验证和 CI 都通过同一个 `scripts/verify.sh`
- **不直推 main**：所有变更走 feature branch → PR → CI + Codex review → merge
- **每 5 分钟进度快照**：写入 `logs/progress/`，连续 3 次无进展触发 Main Agent 介入
- **合并三重门禁**：CI verify PASS + Codex 👍 reaction + branch up to date

## PR 流程（11 步）

1. 从 main 新建 feature branch（命名: `<type>/<scope>-<brief>`）
2. 实现代码 + 本地单元测试
3. 执行 `bash scripts/verify.sh`，必须 ALL OK
4. git add 必要文件
5. git commit（格式: `<type>(<scope>): <description>`）
6. git push -u origin `<branch>`
7. 通过 REST API 创建 PR
8. 等待 CI 通过
9. 等待 Codex 👍 reaction → auto-merge
10. PR merged
11. 确认 main 更新 → 汇报完成
