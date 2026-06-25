"""
Hero AFK - 核心自动化引擎

提供 UI 自动化的基础组件：
    - PixelChecker: 像素颜色检测器（ADB 截图 + RGB 采样）
    - ScreenPilot: 坐标驱动的屏幕导航器
    - RewardModule: 可插拔的奖励收集模块基类
    - BattleResultDetector: 战斗结果检测器（模板匹配）
    - Priority: 任务优先级枚举
    - TaskScheduler: 任务调度器（优先级仲裁 + 冷却管理）
    - TaskRegistry: 任务注册中心（定义 + 工厂）
    - DailyTaskManager: 每日任务管理器（全局编排）
"""

from .pixel_checker import PixelChecker
from .screen_pilot import ScreenPilot
from .reward_module import RewardModule, CollectResult
from .battle_detector import BattleResultDetector, battle_detector
from .priority import Priority
from .task_scheduler import TaskScheduler
from .task_registry import TaskRegistry, TaskDefinition
from .daily_task_manager import DailyTaskManager

__all__ = [
    "PixelChecker", "ScreenPilot",
    "RewardModule", "CollectResult",
    "BattleResultDetector", "battle_detector",
    "Priority",
    "TaskScheduler",
    "TaskRegistry", "TaskDefinition",
    "DailyTaskManager",
]
