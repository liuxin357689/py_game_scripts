"""
任务优先级定义

数字越小优先级越高，与 FrameTask.priority 约定一致。
ScreenshotService 按优先级排序，每帧只执行最高优先级的动作。
"""

from enum import IntEnum


class Priority(IntEnum):
    """任务优先级（值越小越优先）"""

    BACKGROUND = 0
    GAMEPLAY = 10
    ALERT = 20
