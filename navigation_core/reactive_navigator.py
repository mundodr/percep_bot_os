"""ReactiveNavigator — 反应式局部导航控制器。

状态机: IDLE → TRACKING → EDGE_FOLLOW → EMERGENCY_STOP → RECOVERY

所有输出的 VelocityCommand 都经过限幅，急停逻辑不可被绕过。
"""

from __future__ import annotations

import math
from typing import Union

from navigation_core.obstacle_utils import (
    clearance_left,
    clearance_right,
    is_path_blocked,
    min_distance_ahead,
)
from percep_bot_os.contracts.data_types import (
    EdgeFollowContext,
    LocalGoal,
    LocalSubgoal,
    NavigatorState,
    ObstacleScan,
    VelocityCommand,
)

Goal = Union[LocalGoal, LocalSubgoal]

_DEFAULTS: dict[str, float] = {
    "max_linear_speed": 0.35,
    "max_angular_speed": 1.0,
    "safety_distance": 0.30,
    "emergency_stop_distance": 0.10,
    "slowdown_distance": 0.60,
    "goal_tolerance": 0.20,
    "goal_timeout": 3.0,
    "edge_follow_distance": 0.35,
    "edge_follow_timeout": 15.0,
}


class ReactiveNavigator:
    """反应式局部导航器，负责目标追踪、避障和急停。"""

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}
        for key, default in _DEFAULTS.items():
            setattr(self, key, float(cfg.get(key, default)))

        self.nav_state = NavigatorState()

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        return self.nav_state.state

    def compute_command(
        self,
        goal: Goal | None,
        scan: ObstacleScan,
        now: float,
    ) -> VelocityCommand:
        """主入口：根据当前状态分发到子策略，结果经限幅后返回。"""
        front_dist = min_distance_ahead(scan)

        # === 急停判定（任何状态都不可绕过） ===
        if front_dist < self.emergency_stop_distance:
            self.nav_state.state = "EMERGENCY_STOP"
            self.nav_state.last_emergency_stop_time = now
            cmd = self._emergency_stop()
            self.nav_state.last_command = cmd
            return cmd

        # === 状态分发 ===
        if self.nav_state.state == "EMERGENCY_STOP":
            if front_dist >= self.safety_distance:
                self.nav_state.state = "RECOVERY"
            else:
                cmd = self._emergency_stop()
                self.nav_state.last_command = cmd
                return cmd

        if self.nav_state.state == "RECOVERY":
            if goal is not None and not is_path_blocked(scan, self.safety_distance):
                self.nav_state.state = "TRACKING"
                self.nav_state.last_goal_seen_time = now
            else:
                cmd = self._clamp(self._recovery(scan))
                self.nav_state.last_command = cmd
                return cmd

        if self.nav_state.state == "EDGE_FOLLOW":
            ef = self.nav_state.edge_follow
            elapsed = now - ef.start_time
            if elapsed > self.edge_follow_timeout:
                self.nav_state.state = "RECOVERY"
                self.nav_state.edge_follow = EdgeFollowContext()
                cmd = self._clamp(self._recovery(scan))
                self.nav_state.last_command = cmd
                return cmd
            if goal is not None and not is_path_blocked(scan, self.safety_distance):
                self.nav_state.state = "TRACKING"
                self.nav_state.edge_follow = EdgeFollowContext()
                self.nav_state.last_goal_seen_time = now
            else:
                cmd = self._clamp(self._edge_follow(goal, scan, now))
                self.nav_state.last_command = cmd
                return cmd

        # IDLE / TRACKING
        if goal is None:
            self.nav_state.state = "IDLE"
            cmd = VelocityCommand(0.0, 0.0)
            self.nav_state.last_command = cmd
            return cmd

        # 有目标
        self.nav_state.last_goal_seen_time = now
        dist_to_goal = math.hypot(goal.x, goal.y)
        if dist_to_goal < self.goal_tolerance:
            self.nav_state.state = "IDLE"
            cmd = VelocityCommand(0.0, 0.0)
            self.nav_state.last_command = cmd
            return cmd

        if is_path_blocked(scan, self.safety_distance):
            self._init_edge_follow(scan, now)
            cmd = self._clamp(self._edge_follow(goal, scan, now))
            self.nav_state.last_command = cmd
            return cmd

        self.nav_state.state = "TRACKING"
        cmd = self._clamp(self._track_goal(goal, scan))
        self.nav_state.last_command = cmd
        return cmd

    # ------------------------------------------------------------------
    # 子策略
    # ------------------------------------------------------------------

    def _track_goal(self, goal: Goal, scan: ObstacleScan) -> VelocityCommand:
        """目标追踪：计算朝向目标的线速度和角速度。"""
        dist = math.hypot(goal.x, goal.y)
        angle = math.atan2(goal.y, goal.x)

        angular_z = self._proportional_angular(angle)

        linear_x = self.max_linear_speed
        # 转弯时减速
        if abs(angle) > 0.5:
            linear_x *= 0.3
        elif abs(angle) > 0.2:
            linear_x *= 0.6

        linear_x = self._apply_slowdown(linear_x, scan)

        # 接近目标时减速
        if dist < self.slowdown_distance:
            linear_x *= dist / self.slowdown_distance

        return VelocityCommand(linear_x, angular_z)

    def _edge_follow(
        self, goal: Goal | None, scan: ObstacleScan, now: float
    ) -> VelocityCommand:
        """边缘跟随：沿障碍物边缘绕行。"""
        ef = self.nav_state.edge_follow

        if ef.bypass_side == "left":
            angular_z = 0.4
        else:
            angular_z = -0.4

        side_dist = (
            clearance_left(scan) if ef.bypass_side == "left" else clearance_right(scan)
        )

        linear_x = self.max_linear_speed * 0.4
        linear_x = self._apply_slowdown(linear_x, scan)

        if side_dist < self.edge_follow_distance * 0.5:
            angular_z *= 1.5
            linear_x *= 0.5

        ef.last_seen_obstacle_distance = min_distance_ahead(scan)

        return VelocityCommand(linear_x, angular_z)

    def _emergency_stop(self) -> VelocityCommand:
        """急停：返回零速度命令。"""
        return VelocityCommand(0.0, 0.0)

    def _recovery(self, scan: ObstacleScan) -> VelocityCommand:
        """恢复模式：原地旋转寻找出路。"""
        left = clearance_left(scan)
        right = clearance_right(scan)
        direction = 1.0 if left >= right else -1.0
        return VelocityCommand(0.0, self.max_angular_speed * 0.5 * direction)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _init_edge_follow(self, scan: ObstacleScan, now: float) -> None:
        """初始化边缘跟随上下文，选择绕行方向。"""
        left = clearance_left(scan)
        right = clearance_right(scan)
        bypass_side = "left" if left >= right else "right"
        obstacle_side = "right" if bypass_side == "left" else "left"

        self.nav_state.state = "EDGE_FOLLOW"
        self.nav_state.edge_follow = EdgeFollowContext(
            active=True,
            bypass_side=bypass_side,
            obstacle_side=obstacle_side,
            start_time=now,
            last_seen_obstacle_distance=min_distance_ahead(scan),
            last_progress_time=now,
        )

    def _proportional_angular(self, angle: float) -> float:
        """P 控制器计算角速度，增益 1.5。"""
        return max(-self.max_angular_speed, min(self.max_angular_speed, 1.5 * angle))

    def _apply_slowdown(self, linear_x: float, scan: ObstacleScan) -> float:
        """根据前方距离做减速处理。"""
        front_dist = min_distance_ahead(scan)
        if front_dist < self.slowdown_distance:
            ratio = (front_dist - self.emergency_stop_distance) / (
                self.slowdown_distance - self.emergency_stop_distance
            )
            ratio = max(0.0, min(1.0, ratio))
            linear_x *= ratio
        return linear_x

    def _clamp(self, cmd: VelocityCommand) -> VelocityCommand:
        """限幅：确保输出不超过最大速度。"""
        linear_x = max(-self.max_linear_speed, min(self.max_linear_speed, cmd.linear_x))
        angular_z = max(-self.max_angular_speed, min(self.max_angular_speed, cmd.angular_z))
        return VelocityCommand(linear_x, angular_z)
