"""
多设备任务管理器（门面模式）

职责:
    - 作为 ControlPanel 和 DeviceTaskRegistry 之间的桥梁
    - 管理任务模板（工厂方法），为每个设备自动创建独立任务实例
    - 将 start/stop/pause/resume 操作广播到所有已注册设备
    - 聚合多设备任务状态，提供统一的状态查询接口

设计说明:
    ControlPanel 只需要一个 "task_manager" 对象来调用
    start_task / stop_task / get_task_status 等方法。
    在单设备场景下，这个对象就是 TaskManager。
    在多设备场景下，MultiDeviceTaskManager 封装了 DeviceTaskRegistry，
    对外暴露与 TaskManager 相同的接口，内部将操作分发到每个设备的 TaskManager。
"""

import logging
from typing import Dict, Optional, List, Type

from game_platform.task.base_task import BaseTask, TaskStatus
from game_platform.task.device_task_registry import DeviceTaskRegistry

logger = logging.getLogger(__name__)


class MultiDeviceTaskManager:
    """多设备任务管理器，兼容 TaskManager 接口
    
    对外接口与 TaskManager 一致:
        - register(task)          注册任务模板
        - list_tasks()            查询任务列表
        - get_task_status(name)   聚合查询任务状态
        - start_task(name)        在所有设备上启动
        - stop_task(name)         在所有设备上停止
        - pause_task(name)        在所有设备上暂停
        - resume_task(name)       在所有设备上恢复
        - stop_all()              停止所有设备上的所有任务
    
    内部通过 DeviceTaskRegistry 为每个设备维护独立的 TaskManager。
    """

    def __init__(self, device_manager=None):
        """初始化多设备任务管理器
        
        Args:
            device_manager: DeviceManager 实例（可选），用于启动任务时自动重连设备
        """
        self._registry = DeviceTaskRegistry()
        self._device_manager = device_manager
        # task_name -> (task_class, kwargs)  任务模板（工厂）
        self._task_templates: Dict[str, tuple] = {}
        # task_name -> TaskStatus  门面层状态跟踪（不依赖 registry 设备是否存在）
        self._task_states: Dict[str, TaskStatus] = {}

    # ---- 任务模板管理 ----

    def register(self, task: BaseTask, config: dict = None,
                 task_class: Type[BaseTask] = None, task_kwargs: dict = None):
        """注册任务模板
        
        保存任务的类和参数，后续设备注册时会自动创建实例。
        
        Args:
            task: BaseTask 实例（用于获取任务名称）
            config: 任务配置（可选）
            task_class: 任务类，用于为新设备创建实例
            task_kwargs: 传给任务类的参数（不含 device_address）
        """
        if task_class and task_kwargs is not None:
            self._task_templates[task.name] = (task_class, dict(task_kwargs))
            self._task_states[task.name] = TaskStatus.IDLE
            logger.info(f"已注册任务模板: {task.name} ({task_class.__name__})")
        else:
            logger.warning(
                f"任务 {task.name} 未提供 task_class/task_kwargs，"
                f"不会自动为新设备创建实例"
            )

    def list_tasks(self) -> List[str]:
        """列出所有已注册的任务名称"""
        return list(self._task_templates.keys())

    # ---- 设备注册/注销 ----

    def register_device(self, device_address: str):
        """为新连接的设备注册所有任务实例
        
        流程:
            1. 通过 DeviceTaskRegistry 创建该设备的 TaskManager
            2. 遍历所有任务模板，为设备创建独立的任务实例
            3. 每个任务实例的 device_address 参数自动设为该设备地址
        
        Args:
            device_address: 设备地址（如 "localhost:5555"）
        """
        for task_name, (task_class, kwargs) in self._task_templates.items():
            # 为设备创建独立的任务实例
            task_kwargs = dict(kwargs)
            task_kwargs['device_address'] = device_address
            task_instance = task_class(**task_kwargs)
            # 使用 register_task_for_device 确保 _task_devices 映射正确更新
            self._registry.register_task_for_device(device_address, task_instance)
            logger.info(f"为设备 {device_address} 创建任务实例: {task_name}")
        
        logger.info(
            f"设备 {device_address} 已注册，共 {len(self._task_templates)} 个任务"
        )

    def unregister_device(self, device_address: str):
        """设备断开时注销其所有任务
        
        Args:
            device_address: 设备地址
        """
        self._registry.remove_device(device_address)
        logger.info(f"设备 {device_address} 已注销")

    def get_registered_devices(self) -> List[str]:
        """获取所有已注册设备地址"""
        return self._registry.all_devices

    # ---- 任务控制（广播到所有设备） ----

    def _ensure_devices_ready(self):
        """确保有已注册的设备，若无则尝试自动重连已验证设备"""
        if self._registry.all_devices:
            return  # 已有设备，无需重连
        
        if not self._device_manager:
            logger.warning("无 DeviceManager，无法自动重连设备")
            return
        
        # 从配置中获取已验证设备并重新连接
        verified = self._device_manager.config.get_all_verified()
        if not verified:
            logger.warning("无已验证设备可重连")
            return
        
        logger.info(f"无已注册设备，尝试自动重连 {len(verified)} 个已验证设备...")
        for address, info in verified.items():
            try:
                parts = address.rsplit(":", 1)
                if len(parts) != 2:
                    continue
                host, port = parts[0], int(parts[1])
                
                # 预填充设备信息
                from game_platform.adb.scanner import EmulatorInfo
                if address not in self._device_manager._device_infos:
                    device_name = info.name if info and info.name else address
                    self._device_manager._device_infos[address] = EmulatorInfo(
                        host=host, port=port, status="online", name=device_name
                    )
                
                device = self._device_manager.connect_device(host, port)
                if device and device.is_connected():
                    self.register_device(address)
                    logger.info(f"自动重连成功: {address}")
                else:
                    logger.warning(f"自动重连失败: {address}")
            except Exception as e:
                logger.error(f"自动重连异常 {address}: {e}")

    def start_task(self, task_name: str) -> bool:
        """在所有设备上启动指定任务
        
        若无已注册设备，自动尝试重连所有已验证设备。
        
        Args:
            task_name: 任务名称
            
        Returns:
            至少一个设备启动成功返回 True
        """
        # 确保有设备可用
        self._ensure_devices_ready()
        
        results = self._registry.start_task_on_devices(task_name)
        success = any(results.values())
        if success:
            self._task_states[task_name] = TaskStatus.RUNNING
            ok_devices = [addr for addr, ok in results.items() if ok]
            logger.info(f"任务 {task_name} 已在 {len(ok_devices)} 个设备上启动")
        else:
            logger.warning(f"任务 {task_name} 在所有设备上启动失败")
        return success

    def stop_task(self, task_name: str) -> bool:
        """在所有设备上停止指定任务
        
        Args:
            task_name: 任务名称
            
        Returns:
            任务存在即返回 True（即使设备已注销也视为停止成功）
        """
        self._task_states[task_name] = TaskStatus.STOPPED
        results = self._registry.stop_task_on_devices(task_name)
        logger.info(f"任务 {task_name} 已停止")
        return task_name in self._task_templates

    def pause_task(self, task_name: str) -> bool:
        """在所有设备上暂停指定任务"""
        self._task_states[task_name] = TaskStatus.PAUSED
        results = self._registry.pause_task_on_devices(task_name)
        return task_name in self._task_templates

    def resume_task(self, task_name: str) -> bool:
        """在所有设备上恢复指定任务"""
        self._task_states[task_name] = TaskStatus.RUNNING
        results = self._registry.resume_task_on_devices(task_name)
        return task_name in self._task_templates

    # ---- 状态聚合 ----

    def get_task_status(self, task_name: str) -> Optional[TaskStatus]:
        """获取任务在所有设备上的聚合状态
        
        查询逻辑:
            1. 优先从 DeviceTaskRegistry 获取各设备的实时状态并聚合
            2. 若 registry 中无该任务的设备（设备已全部注销），回退到门面层跟踪的状态
            3. 若任务未注册，返回 None
        
        Args:
            task_name: 任务名称
            
        Returns:
            聚合后的 TaskStatus，任务不存在时返回 None
        """
        # 优先从 registry 获取实时状态
        statuses = self._registry.get_task_status_across_devices(task_name)
        if statuses:
            values = [s.value for s in statuses.values()]
            
            if any(v == "error" for v in values):
                return TaskStatus.ERROR
            if any(v == "paused" for v in values):
                return TaskStatus.PAUSED
            if any(v == "running" for v in values):
                return TaskStatus.RUNNING
            if any(v == "stopped" for v in values):
                return TaskStatus.STOPPED
            return TaskStatus.IDLE
        
        # registry 为空（设备已全部注销），回退到门面层跟踪的状态
        return self._task_states.get(task_name)

    # ---- 批量操作 ----

    def stop_all(self):
        """停止所有设备上的所有任务"""
        self._registry.stop_all_tasks_on_all_devices()
        for task_name in self._task_states:
            self._task_states[task_name] = TaskStatus.STOPPED
