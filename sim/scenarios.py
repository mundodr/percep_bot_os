"""预定义测试场景。"""

from __future__ import annotations

from .sim2d_robot import Sim2DRobot
from .sim2d_world import Sim2DWorld


def _add_room_walls(world: Sim2DWorld) -> None:
    """给世界添加四面墙壁。"""
    w, h = world.width, world.height
    world.add_wall(0, 0, w, 0)
    world.add_wall(0, h, w, h)
    world.add_wall(0, 0, 0, h)
    world.add_wall(w, 0, w, h)


def create_empty_room(
    width: float = 10.0,
    height: float = 10.0,
) -> tuple[Sim2DWorld, Sim2DRobot]:
    """空房间，机器人在中心。"""
    world = Sim2DWorld(width, height)
    _add_room_walls(world)
    robot = Sim2DRobot(x=width / 2, y=height / 2, theta=0.0)
    return world, robot


def create_single_obstacle(
    obstacle_x: float = 3.0,
    obstacle_y: float = 0.0,
    radius: float = 0.5,
) -> tuple[Sim2DWorld, Sim2DRobot]:
    """一个障碍在机器人正前方。

    机器人在 (5, 5) 朝 x+ 方向，障碍在 (5+obstacle_x, 5+obstacle_y)。
    """
    world = Sim2DWorld(15.0, 10.0)
    _add_room_walls(world)
    robot = Sim2DRobot(x=5.0, y=5.0, theta=0.0)
    world.add_obstacle(5.0 + obstacle_x, 5.0 + obstacle_y, radius)
    return world, robot


def create_corridor(
    width: float = 1.5,
    length: float = 10.0,
) -> tuple[Sim2DWorld, Sim2DRobot]:
    """窄走廊。机器人在入口处居中朝前。"""
    world = Sim2DWorld(length, width)
    _add_room_walls(world)
    robot = Sim2DRobot(x=1.0, y=width / 2, theta=0.0)
    return world, robot


def create_l_shaped_room() -> tuple[Sim2DWorld, Sim2DRobot]:
    """L 形房间，需要转弯。

    10×10 的空间，右上 5×5 被墙封住，形成 L 形。
    """
    world = Sim2DWorld(10.0, 10.0)
    # 外墙
    world.add_wall(0, 0, 10, 0)
    world.add_wall(0, 0, 0, 10)
    world.add_wall(0, 10, 5, 10)
    world.add_wall(10, 0, 10, 5)
    # 内墙拐角
    world.add_wall(5, 5, 5, 10)
    world.add_wall(5, 5, 10, 5)
    robot = Sim2DRobot(x=2.5, y=2.5, theta=0.0)
    return world, robot
