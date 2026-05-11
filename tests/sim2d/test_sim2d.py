"""2D 仿真器单元测试。"""

from __future__ import annotations

import math

import pytest

from percep_bot_os.contracts.data_types import VelocityCommand
from sim.scenarios import (
    create_corridor,
    create_empty_room,
    create_l_shaped_room,
    create_single_obstacle,
)
from sim.sim2d_robot import Sim2DRobot
from sim.sim2d_sensor import Sim2DLidar
from sim.sim2d_world import Sim2DWorld

# -----------------------------------------------------------------------
# 世界
# -----------------------------------------------------------------------


def test_world_creation():
    """创建世界不报错，栅格大小正确。"""
    world = Sim2DWorld(10.0, 8.0, resolution=0.05)
    assert world.cols == math.ceil(10.0 / 0.05)
    assert world.rows == math.ceil(8.0 / 0.05)
    assert world.time == 0.0


# -----------------------------------------------------------------------
# 机器人运动学
# -----------------------------------------------------------------------


def test_robot_move_forward():
    """机器人直行位移正确。"""
    robot = Sim2DRobot(x=0.0, y=0.0, theta=0.0)
    cmd = VelocityCommand(linear_x=1.0, angular_z=0.0)
    robot.apply_command(cmd, dt=1.0)
    x, y, theta = robot.get_pose()
    assert abs(x - 1.0) < 1e-6
    assert abs(y) < 1e-6
    assert abs(theta) < 1e-6


def test_robot_turn():
    """机器人转向角度正确。"""
    robot = Sim2DRobot(x=0.0, y=0.0, theta=0.0)
    cmd = VelocityCommand(linear_x=0.0, angular_z=math.pi / 2)
    robot.apply_command(cmd, dt=1.0)
    _, _, theta = robot.get_pose()
    assert abs(theta - math.pi / 2) < 1e-6


# -----------------------------------------------------------------------
# 激光雷达
# -----------------------------------------------------------------------


def test_lidar_empty_room():
    """大空房间中激光雷达无命中 → 所有距离为 inf。"""
    world = Sim2DWorld(30.0, 30.0, resolution=0.05)
    robot = Sim2DRobot(x=15.0, y=15.0, theta=0.0)
    lidar = Sim2DLidar(num_rays=72, max_range=5.0)
    scan = lidar.scan(world, robot)
    assert len(scan.angles) == 72
    assert len(scan.distances) == 72
    for d in scan.distances:
        assert d == math.inf


def test_lidar_detect_obstacle():
    """检测到障碍物距离正确（±10% 容差）。"""
    world, robot = create_single_obstacle(obstacle_x=3.0, obstacle_y=0.0, radius=0.5)
    lidar = Sim2DLidar(num_rays=360, max_range=5.0)
    scan = lidar.scan(world, robot)

    # 障碍中心 3m 处，半径 0.5m → 表面在 2.5m
    # 扣除 footprint 0.15m → 期望 ~2.35m
    expected = 3.0 - 0.5 - robot.footprint_radius
    forward_idx = _angle_index(scan.angles, 0.0)
    measured = scan.distances[forward_idx]
    assert measured != math.inf, "前方应检测到障碍"
    assert abs(measured - expected) / expected < 0.10, (
        f"期望 {expected:.2f}m, 实测 {measured:.2f}m"
    )


def test_lidar_detect_wall():
    """检测到墙壁。"""
    world, robot = create_empty_room(10.0, 10.0)
    lidar = Sim2DLidar(num_rays=360, max_range=6.0)
    scan = lidar.scan(world, robot)

    # 机器人在 (5,5)，右墙在 x=10 → 距离 5m → 扣除 footprint ≈ 4.85m
    forward_idx = _angle_index(scan.angles, 0.0)
    measured = scan.distances[forward_idx]
    expected = 5.0 - robot.footprint_radius
    assert measured != math.inf, "前方应检测到墙壁"
    assert abs(measured - expected) / expected < 0.10, (
        f"期望 {expected:.2f}m, 实测 {measured:.2f}m"
    )


# -----------------------------------------------------------------------
# 场景
# -----------------------------------------------------------------------


def test_scenario_empty_room():
    """空房间场景创建正确。"""
    world, robot = create_empty_room()
    assert world.width == 10.0
    assert world.height == 10.0
    assert robot.x == pytest.approx(5.0)
    assert robot.y == pytest.approx(5.0)


def test_scenario_l_shaped_room():
    """L 形房间场景创建正确，内墙存在。"""
    world, robot = create_l_shaped_room()
    assert world.width == 10.0
    assert world.height == 10.0
    # 内墙拐角点 (5, 5) 附近应被占用
    assert world.is_occupied_world(5.0, 5.0)


def test_scenario_corridor():
    """走廊场景激光在两侧检测到墙。"""
    world, robot = create_corridor(width=1.5, length=10.0)
    lidar = Sim2DLidar(num_rays=360, max_range=5.0)
    scan = lidar.scan(world, robot)

    # 左侧（+90°）墙距离 ≈ width/2 - footprint = 0.75 - 0.15 = 0.6m
    left_idx = _angle_index(scan.angles, math.pi / 2)
    right_idx = _angle_index(scan.angles, -math.pi / 2)
    expected_side = 0.75 - robot.footprint_radius

    left_dist = scan.distances[left_idx]
    right_dist = scan.distances[right_idx]
    assert left_dist != math.inf, "左侧应检测到墙"
    assert right_dist != math.inf, "右侧应检测到墙"
    assert abs(left_dist - expected_side) / expected_side < 0.15, (
        f"左墙期望 {expected_side:.2f}m, 实测 {left_dist:.2f}m"
    )
    assert abs(right_dist - expected_side) / expected_side < 0.15, (
        f"右墙期望 {expected_side:.2f}m, 实测 {right_dist:.2f}m"
    )


# -----------------------------------------------------------------------
# 辅助
# -----------------------------------------------------------------------


def _angle_index(angles: list[float] | tuple[float, ...], target: float) -> int:
    """找到最接近 target 的角度索引。"""
    best_idx = 0
    best_diff = abs(angles[0] - target)
    for i, a in enumerate(angles):
        diff = abs(a - target)
        if diff < best_diff:
            best_diff = diff
            best_idx = i
    return best_idx
