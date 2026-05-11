"""percep_bot_os 接口契约数据结构。

完全按照 docs/interface_contracts.md 定义，所有模块共享这些数据类型。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

# ---------------------------------------------------------------------------
# 3.1 导航基座
# ---------------------------------------------------------------------------


@dataclass
class LocalGoal:
    """纯局部导航的最小目标接口。"""

    x: float
    y: float
    confidence: float
    timestamp: float


@dataclass
class LocalSubgoal:
    """长距离导航和探索模式使用的扩展目标。

    ReactiveNavigator 只读取 x, y, confidence, timestamp 四个字段，
    其余字段用于路径管理和调试追踪。
    """

    x: float
    y: float
    confidence: float
    route_id: str
    waypoint_id: str
    timestamp: float
    source: str = "global_route"  # global_route | semantic_goal | exploration | recovery


@dataclass
class ObstacleScan:
    """角度-距离数组，距离已扣除 footprint。"""

    angles: Sequence[float]  # rad，单调递增
    distances: Sequence[float]  # m，无效值为 math.inf
    timestamp: float


@dataclass
class VelocityCommand:
    linear_x: float  # m/s
    angular_z: float  # rad/s


@dataclass
class RobotFootprint:
    shape: str = "rectangle"
    length: float = 0.40
    width: float = 0.30
    height: float = 0.50
    radius: float = 0.0

    @property
    def inscribed_radius(self) -> float:
        if self.shape == "circle":
            return self.radius
        return min(self.length, self.width) / 2.0

    @property
    def circumscribed_radius(self) -> float:
        if self.shape == "circle":
            return self.radius
        return math.hypot(self.length / 2.0, self.width / 2.0)


@dataclass
class EdgeFollowContext:
    active: bool = False
    bypass_side: str = "left"
    obstacle_side: str = "right"
    start_time: float = 0.0
    last_seen_obstacle_distance: float = math.inf
    last_progress_time: float = 0.0


@dataclass
class NavigatorState:
    state: str = "IDLE"
    last_goal_seen_time: float = 0.0
    last_emergency_stop_time: float = 0.0
    last_command: VelocityCommand = field(
        default_factory=lambda: VelocityCommand(0.0, 0.0)
    )
    edge_follow: EdgeFollowContext = field(default_factory=EdgeFollowContext)


# ---------------------------------------------------------------------------
# 3.2 大脑
# ---------------------------------------------------------------------------


@dataclass
class BrainObservation:
    timestamp: float
    user_command: str
    image_ref: str | None
    map_summary: dict
    semantic_summary: dict
    navigation_state: dict
    exploration_state: dict
    safety_state: dict


@dataclass
class BrainDecision:
    intent: str  # 必须在 BRAIN_INTENT_WHITELIST 内
    target_query: str | None
    map_goal_id: str | None
    mode: str
    constraints: dict
    requires_confirmation: bool
    confidence: float
    explanation: str
    timestamp: float


# ---------------------------------------------------------------------------
# 3.3 全局导航
# ---------------------------------------------------------------------------


@dataclass
class GlobalNavigationGoal:
    query: str | None
    map_goal_id: str | None
    map_position: tuple[float, float, float] | None
    timestamp: float
    mode: str = "navigate"  # navigate | explore | inspect


@dataclass
class RouteWaypoint:
    waypoint_id: str
    position_map: tuple[float, float, float]
    heading: float | None = None
    semantic_hint: str | None = None


@dataclass
class GlobalRoute:
    route_id: str
    waypoints: list[RouteWaypoint]
    corridor_width: float
    timestamp: float


@dataclass
class ExploreRoute:
    route_id: str
    exploration_target_id: str
    waypoints: list[RouteWaypoint]
    corridor_width: float
    expected_information_gain: float
    timestamp: float


# ---------------------------------------------------------------------------
# 3.4 探索
# ---------------------------------------------------------------------------


@dataclass
class ExplorationTarget:
    target_id: str
    position_map: tuple[float, float, float]
    yaw_hint: float | None
    score: float
    target_type: str = "frontier"  # frontier | semantic_unknown | coverage_gap | inspection
    timestamp: float = 0.0


@dataclass
class ExplorationState:
    active: bool = False
    mode: str = "frontier"  # frontier | coverage | semantic_search
    current_target_id: str | None = None
    visited_target_ids: list[str] = field(default_factory=list)
    last_saved_map_time: float = 0.0
    last_progress_time: float = 0.0


# ---------------------------------------------------------------------------
# 3.5 语义地图
# ---------------------------------------------------------------------------


@dataclass
class MapFrame:
    frame_id: int
    timestamp: float
    image_path: str | None
    intrinsic: object
    camera_to_map: object
    depth: object | None = None
    world_points: object | None = None
    confidence: object | None = None


@dataclass
class SemanticRegion:
    frame_id: int
    bbox_xyxy: tuple[float, float, float, float]
    mask: object | None
    label_hint: str | None
    image_embedding: object
    clip_confidence: float
    timestamp: float


@dataclass
class SemanticObject:
    object_id: int
    position_map: tuple[float, float, float]
    position_robot: tuple[float, float, float]
    embedding: object
    score: float
    observations: int
    first_seen_time: float
    last_seen_time: float
    radius: float = 0.25
    label: str | None = None
    status: str = "active"  # active | stale | rejected


@dataclass
class SemanticGoal:
    object_id: int
    x: float
    y: float
    z: float
    semantic_score: float
    geometric_confidence: float
    confidence: float
    timestamp: float
    text_query: str


# ---------------------------------------------------------------------------
# 3.6 地图持久化
# ---------------------------------------------------------------------------


@dataclass
class MapUpdate:
    update_id: str
    timestamp: float
    robot_pose_map: tuple[float, float, float]
    occupied_points: object
    free_space_rays: object
    semantic_objects: list[int]
    changed_area_bounds: tuple[float, float, float, float]


@dataclass
class SavedMapManifest:
    map_id: str
    version: int
    created_time: float
    updated_time: float
    metric_map_path: str
    semantic_db_path: str
    route_graph_path: str
    snapshot_dir: str


# ---------------------------------------------------------------------------
# 7. 辅助函数
# ---------------------------------------------------------------------------


def distance_in_sector(
    scan: ObstacleScan,
    a_min: float,
    a_max: float,
    quantile: float = 0.2,
) -> float:
    """返回扇区 [a_min, a_max] 内的代表距离（默认 20% 分位数）。

    若扇区内无有效采样，返回 math.inf。
    """
    vals: list[float] = []
    for angle, dist in zip(scan.angles, scan.distances):
        if a_min <= angle <= a_max and dist < math.inf:
            vals.append(dist)
    if not vals:
        return math.inf
    vals.sort()
    idx = max(0, min(int(len(vals) * quantile), len(vals) - 1))
    return vals[idx]


def distance_at_angle(
    scan: ObstacleScan,
    angle: float,
    tolerance: float = 0.05,
) -> float:
    """返回最接近 angle 的采样点距离。"""
    best_dist = math.inf
    best_diff = math.inf
    for a, d in zip(scan.angles, scan.distances):
        diff = abs(a - angle)
        if diff <= tolerance and diff < best_diff:
            best_diff = diff
            best_dist = d
    return best_dist
