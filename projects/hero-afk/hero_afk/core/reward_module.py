"""
奖励模块基类

定义奖励收集模块的统一接口和数据模型。
所有具体的奖励模块（签到、邮件、任务等）均继承此基类。
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .screen_pilot import ScreenPilot


@dataclass
class CollectResult:
    """奖励收集结果"""
    module_name: str
    success: bool
    items_collected: int
    details: str


class RewardModule(ABC):
    """奖励收集模块基类

    子类需实现 name 属性和 collect() 方法。
    """

    def __init__(self, pilot: ScreenPilot, module_config: dict):
        """
        Args:
            pilot: ScreenPilot 实例
            module_config: 该模块对应的 YAML 配置片段
        """
        self._pilot = pilot
        self._cfg = module_config
        self._logger = logging.getLogger(self.__class__.__name__)

    @property
    @abstractmethod
    def name(self) -> str:
        """模块名称"""
        ...

    @abstractmethod
    def collect(self) -> CollectResult:
        """执行完整的收集流程

        Returns:
            CollectResult 收集结果
        """
        ...
