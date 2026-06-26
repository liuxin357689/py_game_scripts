"""
任务管理器

职责:
    - 注册和管理多个任务
    - 任务调度和优先级管理
    - 任务配置持久化
    - 提供任务列表查询接口
"""

import logging
from typing import Dict, Optional, List
from .base_task import BaseTask, TaskStatus

logger = logging.getLogger(__name__)


class TaskManager:
    """任务管理器，管理所有已注册的任务
    
    支持单设备或多设备场景：
        - 单设备：直接创建 TaskManager 实例
        - 多设备：通过 DeviceTaskRegistry 为每个设备创建独立的 TaskManager
    """

    def __init__(self, device_address: str = None):
        """初始化任务管理器
        
        Args:
            device_address: 设备地址（可选），用于标识此 TaskManager 所属的设备
        """
        self._device_address = device_address
        self._tasks: Dict[str, BaseTask] = {}
        self._configs: Dict[str, dict] = {}
        self._enabled_tasks: set = set()

    def register(self, task: BaseTask, config: dict = None):
        """注册一个任务

        Args:
            task: BaseTask 实例
            config: 任务配置（可选）
        """
        if task.name in self._tasks:
            logger.warning(f"任务 {task.name} 已存在，将被覆盖")
        
        self._tasks[task.name] = task
        self._configs[task.name] = config or {}
        self._enabled_tasks.add(task.name)
        logger.info(f"任务已注册: {task.name}")

    def unregister(self, task_name: str):
        """注销一个任务

        Args:
            task_name: 任务名称
        """
        if task_name in self._tasks:
            task = self._tasks[task_name]
            if task.get_status() == TaskStatus.RUNNING:
                task.stop()
            
            del self._tasks[task_name]
            self._configs.pop(task_name, None)
            self._enabled_tasks.discard(task_name)
            logger.info(f"任务已注销: {task_name}")

    def get_task(self, task_name: str) -> Optional[BaseTask]:
        """获取已注册的任务

        Args:
            task_name: 任务名称

        Returns:
            BaseTask 实例或 None
        """
        return self._tasks.get(task_name)

    def list_tasks(self) -> List[str]:
        """列出所有已注册的任务

        Returns:
            任务名称列表
        """
        return list(self._tasks.keys())

    def enable_task(self, task_name: str):
        """启用任务

        Args:
            task_name: 任务名称
        """
        if task_name in self._tasks:
            self._enabled_tasks.add(task_name)
            logger.info(f"任务已启用: {task_name}")

    def disable_task(self, task_name: str):
        """禁用任务

        Args:
            task_name: 任务名称
        """
        if task_name in self._tasks:
            task = self._tasks[task_name]
            if task.get_status() == TaskStatus.RUNNING:
                task.stop()
            self._enabled_tasks.discard(task_name)
            logger.info(f"任务已禁用: {task_name}")

    def start_task(self, task_name: str):
        """启动指定任务

        Args:
            task_name: 任务名称
        """
        task = self._tasks.get(task_name)
        if not task:
            logger.error(f"任务不存在: {task_name}")
            return False
        
        if task_name not in self._enabled_tasks:
            logger.warning(f"任务未启用: {task_name}")
            return False
        
        if task.get_status() == TaskStatus.RUNNING:
            logger.warning(f"任务已在运行: {task_name}")
            return False
        
        task.start()
        return True

    def stop_task(self, task_name: str):
        """停止指定任务

        Args:
            task_name: 任务名称
        """
        task = self._tasks.get(task_name)
        if not task:
            logger.error(f"任务不存在: {task_name}")
            return False
        
        task.stop()
        return True

    def pause_task(self, task_name: str):
        """暂停指定任务

        Args:
            task_name: 任务名称
        """
        task = self._tasks.get(task_name)
        if not task:
            logger.error(f"任务不存在: {task_name}")
            return False
        
        task.pause()
        return True

    def resume_task(self, task_name: str):
        """恢复指定任务

        Args:
            task_name: 任务名称
        """
        task = self._tasks.get(task_name)
        if not task:
            logger.error(f"任务不存在: {task_name}")
            return False
        
        task.resume()
        return True

    def get_task_status(self, task_name: str) -> Optional[TaskStatus]:
        """获取任务状态

        Args:
            task_name: 任务名称

        Returns:
            任务状态或 None
        """
        task = self._tasks.get(task_name)
        if not task:
            return None
        return task.get_status()

    def stop_all(self):
        """停止所有运行中的任务"""
        for task_name, task in self._tasks.items():
            if task.get_status() == TaskStatus.RUNNING:
                task.stop()
                logger.info(f"已停止任务: {task_name}")

    @property
    def device_address(self) -> Optional[str]:
        """获取此 TaskManager 所属的设备地址"""
        return self._device_address
