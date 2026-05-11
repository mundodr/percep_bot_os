"""仿真-导航集成运行器。

在 2D 仿真环境中驱动 ReactiveNavigator，记录轨迹和命令。
"""

from __future__ import annotations

import math

from navigation_core.reactive_navigator import ReactiveNavigator
from percep_bot_os.contracts.data_types import LocalGoal
from sim.sim2d_robot import Sim2DRobot
from sim.sim2d_sensor import Sim2DLidar
from sim.sim2d_world import Sim2DWorld


class SimNavRunner:
    """在 2D 仿真中运行 ReactiveNavigator 的集成驱动器。"""

    def __init__(
        self,
        world: Sim2DWorld,
        robot: Sim2DRobot,
        lidar: Sim2DLidar,
        navigator: ReactiveNavigator,
        goal: tuple[float, float],
        max_steps: int = 2000,
        dt: float = 0.05,
    ) -> None:
        self.world = world
        self.robot = robot
        self.lidar = lidar
        self.navigator = navigator
        self.goal = goal
        self.max_steps = max_steps
        self.dt = dt

    def run(self) -> dict:
        """运行仿真循环直到到达目标或超时。

        返回:
            {
                "reached": bool,
                "steps": int,
                "final_distance": float,
                "trajectory": [(x, y, theta), ...],
                "commands": [(linear_x, angular_z), ...],
            }
        """
        trajectory: list[tuple[float, float, float]] = []
        commands: list[tuple[float, float]] = []
        goal_x, goal_y = self.goal

        for step in range(self.max_steps):
            trajectory.append(self.robot.get_pose())

            dist = math.hypot(self.robot.x - goal_x, self.robot.y - goal_y)
            if dist < self.navigator.goal_tolerance:
                return {
                    "reached": True,
                    "steps": step,
                    "final_distance": dist,
                    "trajectory": trajectory,
                    "commands": commands,
                }

            scan = self.lidar.scan(self.world, self.robot)

            lx, ly = self._global_to_local(goal_x, goal_y, self.robot)
            local_goal = LocalGoal(
                x=lx, y=ly, confidence=1.0, timestamp=self.world.time
            )

            cmd = self.navigator.compute_command(local_goal, scan, self.world.time)
            commands.append((cmd.linear_x, cmd.angular_z))

            self.robot.apply_command(cmd, self.dt)
            self.world.step(self.dt)

        final_dist = math.hypot(self.robot.x - goal_x, self.robot.y - goal_y)
        trajectory.append(self.robot.get_pose())
        return {
            "reached": final_dist < self.navigator.goal_tolerance,
            "steps": self.max_steps,
            "final_distance": final_dist,
            "trajectory": trajectory,
            "commands": commands,
        }

    @staticmethod
    def _global_to_local(gx: float, gy: float, robot: Sim2DRobot) -> tuple[float, float]:
        """世界坐标转机器人局部坐标。"""
        dx = gx - robot.x
        dy = gy - robot.y
        cos_t = math.cos(-robot.theta)
        sin_t = math.sin(-robot.theta)
        local_x = dx * cos_t - dy * sin_t
        local_y = dx * sin_t + dy * cos_t
        return local_x, local_y
