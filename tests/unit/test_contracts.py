"""接口契约数据结构测试。"""

from __future__ import annotations

import math

from percep_bot_os.contracts.data_types import (
    BrainDecision,
    LocalGoal,
    ObstacleScan,
    RobotFootprint,
    VelocityCommand,
    distance_at_angle,
    distance_in_sector,
)


def test_local_goal_creation() -> None:
    g = LocalGoal(x=1.0, y=2.0, confidence=0.9, timestamp=100.0)
    assert g.x == 1.0
    assert g.y == 2.0
    assert g.confidence == 0.9
    assert g.timestamp == 100.0


def test_obstacle_scan_creation() -> None:
    scan = ObstacleScan(
        angles=[0.0, 0.5, 1.0],
        distances=[1.0, 2.0, math.inf],
        timestamp=50.0,
    )
    assert len(scan.angles) == 3
    assert scan.distances[2] == math.inf


def test_velocity_command_creation() -> None:
    cmd = VelocityCommand(linear_x=0.3, angular_z=0.1)
    assert cmd.linear_x == 0.3
    assert cmd.angular_z == 0.1


def test_brain_decision_creation() -> None:
    d = BrainDecision(
        intent="navigate",
        target_query="kitchen",
        map_goal_id=None,
        mode="navigate",
        constraints={},
        requires_confirmation=False,
        confidence=0.8,
        explanation="go to kitchen",
        timestamp=1.0,
    )
    assert d.intent == "navigate"
    assert d.confidence == 0.8


def test_distance_in_sector() -> None:
    scan = ObstacleScan(
        angles=[0.0, 0.1, 0.2, 0.3, 0.4],
        distances=[3.0, 1.0, 2.0, 1.5, 4.0],
        timestamp=0.0,
    )
    result = distance_in_sector(scan, 0.0, 0.4, quantile=0.2)
    assert result == 1.5  # sorted=[1.0,1.5,2.0,3.0,4.0], idx=int(5*0.2)=1

    empty = distance_in_sector(scan, 5.0, 6.0)
    assert empty == math.inf


def test_distance_at_angle() -> None:
    scan = ObstacleScan(
        angles=[0.0, 0.1, 0.2, 0.3],
        distances=[5.0, 3.0, 2.0, 1.0],
        timestamp=0.0,
    )
    assert distance_at_angle(scan, 0.1) == 3.0
    assert distance_at_angle(scan, 0.15, tolerance=0.06) == 2.0 or \
           distance_at_angle(scan, 0.15, tolerance=0.06) == 3.0
    assert distance_at_angle(scan, 9.0) == math.inf


def test_footprint_radii() -> None:
    fp = RobotFootprint(shape="rectangle", length=0.40, width=0.30)
    assert fp.inscribed_radius == 0.15
    assert abs(fp.circumscribed_radius - math.hypot(0.20, 0.15)) < 1e-9

    fp_circle = RobotFootprint(shape="circle", radius=0.2)
    assert fp_circle.inscribed_radius == 0.2
    assert fp_circle.circumscribed_radius == 0.2
