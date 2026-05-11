"""障碍物扫描辅助函数。

基于 ObstacleScan 数据提供前方距离、左右通行空间等几何查询。
"""

from __future__ import annotations

import math

from percep_bot_os.contracts.data_types import ObstacleScan


def min_distance_ahead(scan: ObstacleScan, half_angle: float = 0.3) -> float:
    """前方扇区 [-half_angle, +half_angle] 内的最小障碍距离。

    half_angle 单位 rad，默认 ±0.3 rad ≈ ±17°。
    若扇区内无有效采样，返回 math.inf。
    """
    min_dist = math.inf
    for angle, dist in zip(scan.angles, scan.distances):
        if -half_angle <= angle <= half_angle and dist < min_dist:
            min_dist = dist
    return min_dist


def clearance_left(scan: ObstacleScan) -> float:
    """左侧（角度 [0.3, π/2]）的最小障碍距离。"""
    min_dist = math.inf
    for angle, dist in zip(scan.angles, scan.distances):
        if 0.3 <= angle <= math.pi / 2 and dist < min_dist:
            min_dist = dist
    return min_dist


def clearance_right(scan: ObstacleScan) -> float:
    """右侧（角度 [-π/2, -0.3]）的最小障碍距离。"""
    min_dist = math.inf
    for angle, dist in zip(scan.angles, scan.distances):
        if -math.pi / 2 <= angle <= -0.3 and dist < min_dist:
            min_dist = dist
    return min_dist


def is_path_blocked(scan: ObstacleScan, safety_distance: float) -> bool:
    """前方是否被阻：前方扇区最小距离 < safety_distance。"""
    return min_distance_ahead(scan) < safety_distance
