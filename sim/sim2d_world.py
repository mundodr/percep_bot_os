"""2D 仿真世界 —— 管理占用栅格、障碍物、墙壁。

纯 Python 实现，不依赖 numpy。
"""

from __future__ import annotations

import math


class Sim2DWorld:
    """2D 仿真世界 - 管理地图、机器人、障碍物。"""

    def __init__(self, width: float, height: float, resolution: float = 0.05) -> None:
        self.width = width
        self.height = height
        self.resolution = resolution
        self.cols = math.ceil(width / resolution)
        self.rows = math.ceil(height / resolution)
        self.grid: list[list[int]] = [[0] * self.cols for _ in range(self.rows)]
        self.time: float = 0.0

    # ------------------------------------------------------------------
    # 坐标转换
    # ------------------------------------------------------------------

    def world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        """世界坐标 → 栅格索引 (gx, gy)。"""
        return int(x / self.resolution), int(y / self.resolution)

    def in_bounds(self, gx: int, gy: int) -> bool:
        return 0 <= gx < self.cols and 0 <= gy < self.rows

    def is_occupied_world(self, x: float, y: float) -> bool:
        """判断世界坐标点是否被占用（越界视为占用）。"""
        gx, gy = self.world_to_grid(x, y)
        if not self.in_bounds(gx, gy):
            return True
        return self.grid[gy][gx] == 1

    # ------------------------------------------------------------------
    # 地图编辑
    # ------------------------------------------------------------------

    def add_obstacle(self, x: float, y: float, radius: float) -> None:
        """在 (x, y) 添加圆形障碍物，半径 radius（米）。"""
        gx_min = max(0, int((x - radius) / self.resolution))
        gx_max = min(self.cols - 1, int((x + radius) / self.resolution))
        gy_min = max(0, int((y - radius) / self.resolution))
        gy_max = min(self.rows - 1, int((y + radius) / self.resolution))
        r_sq = radius * radius
        for gy in range(gy_min, gy_max + 1):
            cy = (gy + 0.5) * self.resolution
            for gx in range(gx_min, gx_max + 1):
                cx = (gx + 0.5) * self.resolution
                if (cx - x) ** 2 + (cy - y) ** 2 <= r_sq:
                    self.grid[gy][gx] = 1

    def add_wall(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """添加从 (x1,y1) 到 (x2,y2) 的线段墙壁。"""
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 1e-9:
            gx, gy = self.world_to_grid(x1, y1)
            if self.in_bounds(gx, gy):
                self.grid[gy][gx] = 1
            return
        steps = max(1, int(length / (self.resolution * 0.4)))
        for i in range(steps + 1):
            t = i / steps
            x = x1 + t * (x2 - x1)
            y = y1 + t * (y2 - y1)
            gx = int(x / self.resolution)
            gy = int(y / self.resolution)
            gx = max(0, min(gx, self.cols - 1))
            gy = max(0, min(gy, self.rows - 1))
            self.grid[gy][gx] = 1

    # ------------------------------------------------------------------
    # 仿真步进
    # ------------------------------------------------------------------

    def step(self, dt: float) -> None:
        """推进仿真时间。"""
        self.time += dt
