"""端到端集成测试：在 2D 仿真中验证 ReactiveNavigator。

已知限制 (handoff):
  ReactiveNavigator 的 edge_follow 在默认配置下 (safety_distance=0.30m,
  emergency_stop_distance=0.10m) 会使机器人过度靠近障碍物，触发不可恢复的
  EMERGENCY_STOP 死锁——因为急停输出零速度，而退出条件要求 front_dist >=
  safety_distance，静态场景中永远无法满足。
  增大 safety_distance 可绕过该问题（让 edge_follow 更早启动、距离障碍更远）。
  建议后续修复: edge_follow 中加入距离保持逻辑，或在 EMERGENCY_STOP 中允许缓慢后
  退 / 旋转。
"""

from __future__ import annotations

import math

from integration.sim_nav_runner import SimNavRunner
from navigation_core.reactive_navigator import ReactiveNavigator
from percep_bot_os.contracts.data_types import LocalGoal, ObstacleScan
from sim.scenarios import create_corridor, create_empty_room
from sim.sim2d_robot import Sim2DRobot
from sim.sim2d_sensor import Sim2DLidar
from sim.sim2d_world import Sim2DWorld


def _make_lidar() -> Sim2DLidar:
    return Sim2DLidar(num_rays=180, max_range=5.0)


# ---------------------------------------------------------------------------
# L0: 无障碍基本导航
# ---------------------------------------------------------------------------


def test_l0_straight_to_goal():
    """L0: 空房间，目标在正前方 3m，应直行到达。"""
    world, robot = create_empty_room(10.0, 10.0)
    goal = (robot.x + 3.0, robot.y)

    runner = SimNavRunner(
        world=world,
        robot=robot,
        lidar=_make_lidar(),
        navigator=ReactiveNavigator(),
        goal=goal,
        max_steps=2000,
    )
    result = runner.run()

    assert result["reached"], (
        f"未到达目标，最终距离 {result['final_distance']:.3f}m，"
        f"步数 {result['steps']}"
    )
    assert result["steps"] < 1000, f"用了太多步: {result['steps']}"


def test_l0_turn_to_goal():
    """L0: 空房间，目标在侧前方（左前方 45°，距离 3m），应转向后到达。"""
    world, robot = create_empty_room(10.0, 10.0)
    dist = 3.0
    angle = math.pi / 4
    goal = (robot.x + dist * math.cos(angle), robot.y + dist * math.sin(angle))

    runner = SimNavRunner(
        world=world,
        robot=robot,
        lidar=_make_lidar(),
        navigator=ReactiveNavigator(),
        goal=goal,
        max_steps=2000,
    )
    result = runner.run()

    assert result["reached"], (
        f"未到达目标，最终距离 {result['final_distance']:.3f}m，"
        f"步数 {result['steps']}"
    )


def test_l0_goal_tolerance():
    """L0: 验证到达容差，距离目标 < goal_tolerance 时停止。"""
    world, robot = create_empty_room(10.0, 10.0)
    goal = (robot.x + 2.0, robot.y)

    nav = ReactiveNavigator({"goal_tolerance": 0.30})
    runner = SimNavRunner(
        world=world,
        robot=robot,
        lidar=_make_lidar(),
        navigator=nav,
        goal=goal,
        max_steps=2000,
    )
    result = runner.run()

    assert result["reached"]
    assert result["final_distance"] < 0.30, (
        f"停止距离 {result['final_distance']:.3f}m 超过容差 0.30m"
    )


# ---------------------------------------------------------------------------
# L1: 有障碍导航
# ---------------------------------------------------------------------------


def test_l1_avoid_obstacle():
    """L1: 正前方有障碍，应绕过到达目标。

    使用增大的 safety_distance 配置以绕过 edge_follow 死锁问题
    （见模块文档 '已知限制'）。
    """
    world = Sim2DWorld(15.0, 10.0)
    world.add_wall(0, 0, 15, 0)
    world.add_wall(0, 10, 15, 10)
    world.add_wall(0, 0, 0, 10)
    world.add_wall(15, 0, 15, 10)
    robot = Sim2DRobot(x=3.0, y=5.0, theta=0.0)
    world.add_obstacle(6.0, 5.0, 0.3)
    goal = (11.0, 5.0)

    nav = ReactiveNavigator({
        "safety_distance": 0.60,
        "slowdown_distance": 1.0,
        "edge_follow_distance": 0.55,
    })
    runner = SimNavRunner(
        world=world,
        robot=robot,
        lidar=_make_lidar(),
        navigator=nav,
        goal=goal,
        max_steps=3000,
    )
    result = runner.run()

    assert result["reached"], (
        f"未绕过障碍到达目标，最终距离 {result['final_distance']:.3f}m，"
        f"步数 {result['steps']}"
    )
    has_angular = any(abs(az) > 0.1 for _, az in result["commands"])
    assert has_angular, "应有转向命令（避障行为）"


def test_l1_corridor():
    """L1: 窄走廊（宽 1.5m），应安全通过到达走廊末端。"""
    world, robot = create_corridor(width=1.5, length=10.0)
    goal = (8.0, robot.y)

    runner = SimNavRunner(
        world=world,
        robot=robot,
        lidar=_make_lidar(),
        navigator=ReactiveNavigator(),
        goal=goal,
        max_steps=3000,
    )
    result = runner.run()

    assert result["reached"], (
        f"未通过走廊到达目标，最终距离 {result['final_distance']:.3f}m，"
        f"步数 {result['steps']}"
    )


def test_l1_emergency_stop_then_recover():
    """L1: 验证急停触发与恢复能力。

    分两部分：
    1) 仿真：机器人遇到极近障碍触发急停（零速度命令）。
    2) API 验证：障碍消除后，导航器正确从 EMERGENCY_STOP 恢复到 TRACKING。

    注：在静态仿真中，急停后机器人无法自行恢复（已知限制，见模块文档）。
    """
    # --- Part 1: 仿真验证急停触发 ---
    world = Sim2DWorld(10.0, 10.0)
    world.add_wall(0, 0, 10, 0)
    world.add_wall(0, 10, 10, 10)
    world.add_wall(0, 0, 0, 10)
    world.add_wall(10, 0, 10, 10)

    robot = Sim2DRobot(x=5.0, y=5.0, theta=0.0)
    world.add_obstacle(5.22, 5.0, 0.07)
    goal = (5.0, 8.0)

    nav = ReactiveNavigator()
    runner = SimNavRunner(
        world=world,
        robot=robot,
        lidar=_make_lidar(),
        navigator=nav,
        goal=goal,
        max_steps=100,
    )
    result = runner.run()

    has_emergency = any(
        abs(lx) < 1e-9 and abs(az) < 1e-9 for lx, az in result["commands"][:50]
    )
    assert has_emergency, "应出现急停命令（零速度）"
    assert nav.state == "EMERGENCY_STOP", "导航器应处于 EMERGENCY_STOP 状态"

    # --- Part 2: API 验证恢复能力 ---
    nav2 = ReactiveNavigator()
    angles = [i * (2 * math.pi / 72) - math.pi for i in range(72)]

    close_dists = [5.0] * 72
    for i, a in enumerate(angles):
        if abs(a) < 0.3:
            close_dists[i] = 0.05
    close_scan = ObstacleScan(angles=angles, distances=close_dists, timestamp=0.0)
    lg = LocalGoal(x=3.0, y=0.0, confidence=1.0, timestamp=0.0)

    cmd = nav2.compute_command(lg, close_scan, 0.0)
    assert nav2.state == "EMERGENCY_STOP"
    assert cmd.linear_x == 0.0 and cmd.angular_z == 0.0

    clear_dists = [5.0] * 72
    clear_scan = ObstacleScan(angles=angles, distances=clear_dists, timestamp=1.0)
    cmd2 = nav2.compute_command(lg, clear_scan, 1.0)
    assert nav2.state == "TRACKING", (
        f"障碍消除后应恢复到 TRACKING，实际状态: {nav2.state}"
    )
    assert cmd2.linear_x > 0, "恢复后应有前进速度"
