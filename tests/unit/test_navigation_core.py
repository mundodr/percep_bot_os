"""ReactiveNavigator 单元测试。"""

from __future__ import annotations

import math
import time

import pytest

from navigation_core.obstacle_utils import (
    clearance_left,
    clearance_right,
    is_path_blocked,
    min_distance_ahead,
)
from navigation_core.reactive_navigator import ReactiveNavigator
from percep_bot_os.contracts.data_types import (
    LocalGoal,
    ObstacleScan,
)

# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------


def _make_scan(
    front: float = 5.0,
    left: float = 5.0,
    right: float = 5.0,
    n_rays: int = 60,
) -> ObstacleScan:
    """生成简化的扫描数据。

    将 [-π, π] 均匀分成 n_rays 条射线，
    前方 ±0.3 rad 设为 front，左侧设为 left，右侧设为 right。
    """
    angles = [
        -math.pi + i * 2 * math.pi / n_rays for i in range(n_rays)
    ]
    distances: list[float] = []
    for a in angles:
        if -0.3 <= a <= 0.3:
            distances.append(front)
        elif a > 0.3:
            distances.append(left)
        else:
            distances.append(right)
    return ObstacleScan(angles=angles, distances=distances, timestamp=time.time())


def _make_goal(x: float = 1.0, y: float = 0.0) -> LocalGoal:
    return LocalGoal(x=x, y=y, confidence=1.0, timestamp=time.time())


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------


class TestObstacleUtils:
    def test_min_distance_ahead_clear(self) -> None:
        scan = _make_scan(front=3.0)
        assert min_distance_ahead(scan) == pytest.approx(3.0)

    def test_min_distance_ahead_close(self) -> None:
        scan = _make_scan(front=0.05)
        assert min_distance_ahead(scan) == pytest.approx(0.05)

    def test_clearance_left(self) -> None:
        scan = _make_scan(left=1.5)
        assert clearance_left(scan) == pytest.approx(1.5)

    def test_clearance_right(self) -> None:
        scan = _make_scan(right=0.8)
        assert clearance_right(scan) == pytest.approx(0.8)

    def test_path_blocked(self) -> None:
        scan = _make_scan(front=0.2)
        assert is_path_blocked(scan, safety_distance=0.3) is True

    def test_path_clear(self) -> None:
        scan = _make_scan(front=1.0)
        assert is_path_blocked(scan, safety_distance=0.3) is False


class TestReactiveNavigator:
    def test_idle_no_goal(self) -> None:
        """无目标时输出零速度，状态为 IDLE。"""
        nav = ReactiveNavigator()
        scan = _make_scan()
        cmd = nav.compute_command(None, scan, time.time())
        assert cmd.linear_x == 0.0
        assert cmd.angular_z == 0.0
        assert nav.state == "IDLE"

    def test_tracking_straight(self) -> None:
        """正前方目标，直行（正线速度，小角速度）。"""
        nav = ReactiveNavigator()
        scan = _make_scan(front=5.0)
        goal = _make_goal(x=2.0, y=0.0)
        cmd = nav.compute_command(goal, scan, time.time())
        assert cmd.linear_x > 0.0
        assert abs(cmd.angular_z) < 0.1
        assert nav.state == "TRACKING"

    def test_tracking_turn(self) -> None:
        """侧前方目标，应有明显转向。"""
        nav = ReactiveNavigator()
        scan = _make_scan(front=5.0, left=5.0)
        goal = _make_goal(x=1.0, y=1.5)
        cmd = nav.compute_command(goal, scan, time.time())
        assert cmd.angular_z > 0.2
        assert cmd.linear_x > 0.0

    def test_emergency_stop(self) -> None:
        """前方极近障碍物，立即急停。"""
        nav = ReactiveNavigator()
        scan = _make_scan(front=0.05)
        goal = _make_goal(x=2.0, y=0.0)
        cmd = nav.compute_command(goal, scan, time.time())
        assert cmd.linear_x == 0.0
        assert cmd.angular_z == 0.0
        assert nav.state == "EMERGENCY_STOP"

    def test_speed_limit(self) -> None:
        """任何输出速度不超过限幅值。"""
        nav = ReactiveNavigator({"max_linear_speed": 0.2, "max_angular_speed": 0.5})
        scan = _make_scan(front=5.0)
        goal = _make_goal(x=10.0, y=5.0)
        cmd = nav.compute_command(goal, scan, time.time())
        assert abs(cmd.linear_x) <= 0.2 + 1e-9
        assert abs(cmd.angular_z) <= 0.5 + 1e-9

    def test_safety_slowdown(self) -> None:
        """接近障碍物时减速，速度低于最大值。"""
        nav = ReactiveNavigator()
        scan_far = _make_scan(front=5.0)
        scan_near = _make_scan(front=0.4)
        goal = _make_goal(x=2.0, y=0.0)
        now = time.time()
        cmd_far = nav.compute_command(goal, scan_far, now)

        nav2 = ReactiveNavigator()
        cmd_near = nav2.compute_command(goal, scan_near, now)
        assert cmd_near.linear_x < cmd_far.linear_x

    def test_goal_reached(self) -> None:
        """到达目标容差内，切回 IDLE。"""
        nav = ReactiveNavigator({"goal_tolerance": 0.5})
        scan = _make_scan()
        goal = _make_goal(x=0.1, y=0.1)
        cmd = nav.compute_command(goal, scan, time.time())
        assert cmd.linear_x == 0.0
        assert cmd.angular_z == 0.0
        assert nav.state == "IDLE"

    def test_edge_follow_trigger(self) -> None:
        """前方阻塞时触发边缘跟随。"""
        nav = ReactiveNavigator()
        scan = _make_scan(front=0.2, left=2.0, right=1.0)
        goal = _make_goal(x=2.0, y=0.0)
        nav.compute_command(goal, scan, time.time())
        assert nav.state == "EDGE_FOLLOW"
        assert nav.nav_state.edge_follow.active is True

    def test_edge_follow_timeout(self) -> None:
        """边缘跟随超时后进入恢复模式。"""
        nav = ReactiveNavigator({"edge_follow_timeout": 1.0})
        scan = _make_scan(front=0.2, left=2.0, right=1.0)
        goal = _make_goal(x=2.0, y=0.0)
        now = 100.0
        nav.compute_command(goal, scan, now)
        assert nav.state == "EDGE_FOLLOW"

        # 超时后再调用
        nav.compute_command(goal, scan, now + 2.0)
        assert nav.state == "RECOVERY"

    def test_recovery_rotation(self) -> None:
        """恢复模式下原地旋转（线速度=0，角速度≠0）。"""
        nav = ReactiveNavigator()
        nav.nav_state.state = "RECOVERY"
        scan = _make_scan(front=0.5, left=2.0, right=1.0)
        cmd = nav.compute_command(None, scan, time.time())
        assert cmd.linear_x == 0.0
        assert cmd.angular_z != 0.0

    def test_emergency_stop_overrides_tracking(self) -> None:
        """即使处于 TRACKING 状态，急停也不可被绕过。"""
        nav = ReactiveNavigator()
        scan_ok = _make_scan(front=5.0)
        goal = _make_goal(x=2.0, y=0.0)
        nav.compute_command(goal, scan_ok, time.time())
        assert nav.state == "TRACKING"

        scan_danger = _make_scan(front=0.05)
        cmd = nav.compute_command(goal, scan_danger, time.time())
        assert cmd.linear_x == 0.0
        assert cmd.angular_z == 0.0
        assert nav.state == "EMERGENCY_STOP"

    def test_emergency_stop_to_recovery(self) -> None:
        """急停后，前方重新安全时转入恢复模式。"""
        nav = ReactiveNavigator()
        scan_danger = _make_scan(front=0.05)
        nav.compute_command(None, scan_danger, 1.0)
        assert nav.state == "EMERGENCY_STOP"

        scan_safe = _make_scan(front=1.0)
        cmd = nav.compute_command(None, scan_safe, 2.0)
        assert nav.state == "RECOVERY"
        assert cmd.angular_z != 0.0
