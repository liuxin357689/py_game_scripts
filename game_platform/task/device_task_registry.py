"""
多设备任务注册表

职责:
    - 为每个设备维护独立的 TaskManager
    - 支持批量在多个设备上启动/停止相同任务
    - 提供统一的设备-任务映射查询接口
"""

import logging
from typing import Dict, List, Optional, Set
from .task_manager import TaskManager
from .base_task import BaseTask, TaskStatus

logger = logging.getLogger(__name__)


class DeviceTaskRegistry:
    """多设备任务注册表
    
    管理多个设备的任务执行，每个设备对应一个独立的 TaskManager。
    
    使用场景:
        1. 同时在 2 台模拟器上运行自动战斗
        2. 在不同设备上执行不同的任务组合
        3. 统一管理所有设备的任务状态
    """
    
    def __init__(self):
        """初始化注册表"""
        # device_address -> TaskManager
        self._registries: Dict[str, TaskManager] = {}
        # task_name -> set of device_addresses (哪些设备运行了此任务)
        self._task_devices: Dict[str, Set[str]] = {}
    
    def get_or_create(self, device_address: str) -> TaskManager:
        """获取或创建设备对应的 TaskManager
        
        Args:
            device_address: 设备地址（如 "localhost:5555"）
            
        Returns:
            该设备对应的 TaskManager 实例
        """
        if device_address not in self._registries:
            self._registries[device_address] = TaskManager(device_address=device_address)
            logger.info(f"为设备 {device_address} 创建 TaskManager")
        
        return self._registries[device_address]
    
    def register_task_for_device(
        self, 
        device_address: str, 
        task: BaseTask, 
        config: dict = None
    ):
        """为指定设备注册任务
        
        Args:
            device_address: 设备地址
            task: 任务实例
            config: 任务配置
        """
        tm = self.get_or_create(device_address)
        tm.register(task, config)
        
        # 记录任务-设备映射
        if task.name not in self._task_devices:
            self._task_devices[task.name] = set()
        self._task_devices[task.name].add(device_address)
        
        logger.info(f"任务 {task.name} 已注册到设备 {device_address}")
    
    def unregister_task_for_device(self, device_address: str, task_name: str):
        """从指定设备注销任务
        
        Args:
            device_address: 设备地址
            task_name: 任务名称
        """
        if device_address in self._registries:
            tm = self._registries[device_address]
            tm.unregister(task_name)
            
            # 更新映射
            if task_name in self._task_devices:
                self._task_devices[task_name].discard(device_address)
                if not self._task_devices[task_name]:
                    del self._task_devices[task_name]
            
            logger.info(f"任务 {task_name} 已从设备 {device_address} 注销")
    
    def start_task_on_devices(
        self, 
        task_name: str, 
        device_addresses: List[str] = None
    ) -> Dict[str, bool]:
        """在多个设备上启动同一任务
        
        Args:
            task_name: 任务名称
            device_addresses: 目标设备列表，None 表示在所有已注册该任务的设备上启动
            
        Returns:
            字典 {device_address: success}，记录每个设备的启动结果
        """
        results = {}
        
        # 确定目标设备
        if device_addresses is None:
            # 在所有已注册该任务的设备上启动
            if task_name not in self._task_devices:
                logger.warning(f"任务 {task_name} 未在任何设备上注册")
                return {}
            target_devices = list(self._task_devices[task_name])
        else:
            target_devices = device_addresses
        
        # 逐个设备启动
        for addr in target_devices:
            if addr not in self._registries:
                logger.warning(f"设备 {addr} 无对应的 TaskManager")
                results[addr] = False
                continue
            
            tm = self._registries[addr]
            success = tm.start_task(task_name)
            results[addr] = success
            
            status = "✅ 成功" if success else " 失败"
            logger.info(f"[{addr}] 启动任务 {task_name}: {status}")
        
        return results
    
    def stop_task_on_devices(
        self, 
        task_name: str, 
        device_addresses: List[str] = None
    ) -> Dict[str, bool]:
        """在多个设备上停止同一任务
        
        Args:
            task_name: 任务名称
            device_addresses: 目标设备列表，None 表示在所有运行该任务的设备上停止
            
        Returns:
            字典 {device_address: success}
        """
        results = {}
        
        if device_addresses is None:
            if task_name not in self._task_devices:
                return {}
            target_devices = list(self._task_devices[task_name])
        else:
            target_devices = device_addresses
        
        for addr in target_devices:
            if addr not in self._registries:
                results[addr] = False
                continue
            
            tm = self._registries[addr]
            success = tm.stop_task(task_name)
            results[addr] = success
        
        return results
    
    def pause_task_on_devices(
        self, 
        task_name: str, 
        device_addresses: List[str] = None
    ) -> Dict[str, bool]:
        """在多个设备上暂停同一任务"""
        results = {}
        
        if device_addresses is None:
            if task_name not in self._task_devices:
                return {}
            target_devices = list(self._task_devices[task_name])
        else:
            target_devices = device_addresses
        
        for addr in target_devices:
            if addr not in self._registries:
                results[addr] = False
                continue
            
            tm = self._registries[addr]
            success = tm.pause_task(task_name)
            results[addr] = success
        
        return results
    
    def resume_task_on_devices(
        self, 
        task_name: str, 
        device_addresses: List[str] = None
    ) -> Dict[str, bool]:
        """在多个设备上恢复同一任务"""
        results = {}
        
        if device_addresses is None:
            if task_name not in self._task_devices:
                return {}
            target_devices = list(self._task_devices[task_name])
        else:
            target_devices = device_addresses
        
        for addr in target_devices:
            if addr not in self._registries:
                results[addr] = False
                continue
            
            tm = self._registries[addr]
            success = tm.resume_task(task_name)
            results[addr] = success
        
        return results
    
    def get_task_status_across_devices(
        self, 
        task_name: str
    ) -> Dict[str, TaskStatus]:
        """查询任务在所有设备上的状态
        
        Args:
            task_name: 任务名称
            
        Returns:
            字典 {device_address: TaskStatus}
        """
        statuses = {}
        
        if task_name not in self._task_devices:
            return statuses
        
        for addr in self._task_devices[task_name]:
            if addr in self._registries:
                tm = self._registries[addr]
                status = tm.get_task_status(task_name)
                if status:
                    statuses[addr] = status
        
        return statuses
    
    def list_devices_for_task(self, task_name: str) -> List[str]:
        """列出运行某任务的所有设备
        
        Args:
            task_name: 任务名称
            
        Returns:
            设备地址列表
        """
        if task_name not in self._task_devices:
            return []
        return list(self._task_devices[task_name])
    
    def list_tasks_for_device(self, device_address: str) -> List[str]:
        """列出某设备上的所有任务
        
        Args:
            device_address: 设备地址
            
        Returns:
            任务名称列表
        """
        if device_address not in self._registries:
            return []
        return self._registries[device_address].list_tasks()
    
    def stop_all_tasks_on_device(self, device_address: str):
        """停止某设备上的所有任务
        
        Args:
            device_address: 设备地址
        """
        if device_address in self._registries:
            tm = self._registries[device_address]
            tm.stop_all()
            logger.info(f"已停止设备 {device_address} 上的所有任务")
    
    def stop_all_tasks_on_all_devices(self):
        """停止所有设备上的所有任务"""
        for addr, tm in self._registries.items():
            tm.stop_all()
        logger.info("已停止所有设备上的所有任务")
    
    def remove_device(self, device_address: str):
        """移除设备及其所有任务
        
        Args:
            device_address: 设备地址
        """
        if device_address in self._registries:
            # 先停止所有任务
            self.stop_all_tasks_on_device(device_address)
            
            # 清理任务-设备映射
            for task_name in list(self._task_devices.keys()):
                self._task_devices[task_name].discard(device_address)
                if not self._task_devices[task_name]:
                    del self._task_devices[task_name]
            
            # 删除 TaskManager
            del self._registries[device_address]
            logger.info(f"已移除设备 {device_address}")
    
    @property
    def all_devices(self) -> List[str]:
        """获取所有已注册的设备地址"""
        return list(self._registries.keys())
    
    @property
    def all_task_names(self) -> List[str]:
        """获取所有已注册的任务名称"""
        return list(self._task_devices.keys())
