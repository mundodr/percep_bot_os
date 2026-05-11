"""2D 虚拟传感器 —— 激光雷达仿真。

通过对占用栅格做步进式光线投射生成 ObstacleScan。
"""

from __future__ import annotations

import math

from percep_bot_os.contracts.data_types import ObstacleScan

from .sim2d_robot import Sim2DRobot
from .sim2d_world import Sim2DWorld


class Sim2DLidar:
    """2D 虚拟激光雷达，生成 ObstacleScan。"""

    def __init__(
        self,
        num_rays: int = 72,
        max_range: float = 5.0,
        fov: float = 2 * math.pi,
    ) -> None:
        self.num_rays = num_rays
        self.max_range = max_range
        self.fov = fov

    def scan(self, world: Sim2DWorld, robot: Sim2DRobot) -> ObstacleScan:
        """对每条射线做光线投射，返回 ObstacleScan。

        距离已扣除 footprint_radius，与接口契约一致。
        """
        angles: list[float] = []
        distances: list[float] = []
        start_angle = -self.fov / 2
        angle_step = self.fov / self.num_rays

        for i in range(self.num_rays):
            local_angle = start_angle + i * angle_step
            world_angle = robot.theta + local_angle
            raw_dist = self._cast_ray(world, robot.x, robot.y, world_angle)
            if raw_dist < math.inf:
                adjusted = raw_dist - robot.footprint_radius
                adjusted = max(0.0, adjusted)
            else:
                adjusted = math.inf
            angles.append(local_angle)
            distances.append(adjusted)

        return ObstacleScan(angles=angles, distances=distances, timestamp=world.time)

    def _cast_ray(
        self,
        world: Sim2DWorld,
        ox: float,
        oy: float,
        angle: float,
    ) -> float:
        """沿 angle 方向步进，返回原始命中距离（从机器人中心算起）。"""
        dx = math.cos(angle)
        dy = math.sin(angle)
        step = world.resolution * 0.5
        dist = step  # 跳过起始格，避免自检测
        while dist <= self.max_range:
            px = ox + dx * dist
            py = oy + dy * dist
            gx = int(px / world.resolution)
            gy = int(py / world.resolution)
            if not world.in_bounds(gx, gy):
                return math.inf
            if world.grid[gy][gx] == 1:
                return dist
            dist += step
        return math.inf
