"""2D 仿真差速驱动机器人。"""

from __future__ import annotations

import math

from percep_bot_os.contracts.data_types import VelocityCommand


class Sim2DRobot:
    """差速驱动机器人模型。"""

    def __init__(
        self,
        x: float = 0.0,
        y: float = 0.0,
        theta: float = 0.0,
        footprint_radius: float = 0.15,
    ) -> None:
        self.x = x
        self.y = y
        self.theta = theta
        self.footprint_radius = footprint_radius

    def apply_command(self, cmd: VelocityCommand, dt: float) -> None:
        """应用速度指令，更新位姿。"""
        self.x += cmd.linear_x * math.cos(self.theta) * dt
        self.y += cmd.linear_x * math.sin(self.theta) * dt
        self.theta += cmd.angular_z * dt
        self.theta = math.atan2(math.sin(self.theta), math.cos(self.theta))

    def get_pose(self) -> tuple[float, float, float]:
        """返回 (x, y, theta)。"""
        return (self.x, self.y, self.theta)
