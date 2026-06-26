"""
任务引擎模块

提供游戏自动化任务的核心框架：
    - BaseTask: 任务基类，定义通用接口和生命周期
    - FrameTask: 帧任务基类，截图共享架构下的任务抽象
    - ScreenshotService: 截图服务，截图共享架构的核心引擎
    - TaskRunner: 任务执行器，管理任务线程
    - TaskManager: 任务管理器，管理多个任务的注册和调度
    - DeviceTaskRegistry: 多设备任务注册表，支持在多个设备上并行执行任务
"""

from .base_task import BaseTask, TaskStatus
from .frame_task import FrameTask, TapAction, SwipeAction, KeyAction
from .screenshot_service import ScreenshotService
from .task_manager import TaskManager
from .device_task_registry import DeviceTaskRegistry

__all__ = [
    "BaseTask", "TaskStatus",
    "FrameTask", "TapAction", "SwipeAction", "KeyAction",
    "ScreenshotService",
    "TaskManager", "DeviceTaskRegistry",
]
