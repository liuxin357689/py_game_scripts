"""
任务基类

定义所有自动化任务的通用接口和基础功能：
    - 任务生命周期（启动、停止、暂停、恢复）
    - 状态管理
    - 日志记录
    - 错误处理

各项目的具体任务必须继承 BaseTask
"""

import logging
import threading
from abc import ABC, abstractmethod
from enum import Enum


class TaskStatus(Enum):
    """任务状态枚举"""
    IDLE = "idle"           # 空闲
    RUNNING = "running"     # 运行中
    PAUSED = "paused"       # 已暂停
    STOPPED = "stopped"     # 已停止
    ERROR = "error"         # 出错


class BaseTask(ABC):
    """自动化任务基类，所有具体任务必须继承此类"""

    def __init__(self, name: str = "BaseTask"):
        """初始化任务

        Args:
            name: 任务名称
        """
        self._name = name
        self._status = TaskStatus.IDLE
        self._thread: threading.Thread | None = None
        self._logger = logging.getLogger(f"task.{name}")

        # 控制标志
        self._stop_event = threading.Event()    # set() 表示请求停止
        self._pause_event = threading.Event()   # clear() 表示暂停中
        self._pause_event.set()                 # 初始状态为不暂停

        self._lock = threading.Lock()           # 保护 _status 写入

    @property
    def name(self) -> str:
        return self._name

    # ---- 子类必须实现的抽象方法 ----

    @abstractmethod
    def setup(self):
        """任务初始化（在 execute 前调用）

        用于加载资源、检查前置条件等
        """

    @abstractmethod
    def execute(self):
        """执行任务主逻辑

        由子类实现具体的任务行为。
        子类应在循环中定期调用 self.sleep() 以响应暂停/停止请求。
        """

    @abstractmethod
    def teardown(self):
        """任务清理（在停止后调用）

        用于释放资源、保存状态等
        """

    # ---- 生命周期控制 ----

    def start(self):
        """启动任务（在后台线程中运行 setup -> execute -> teardown）"""
        if self.get_status() == TaskStatus.RUNNING:
            self._logger.warning(f"任务 {self._name} 已在运行中")
            return

        self._stop_event.clear()
        self._pause_event.set()
        self._set_status(TaskStatus.RUNNING)

        self._thread = threading.Thread(target=self._run_loop, name=self._name, daemon=True)
        self._thread.start()
        self._logger.info(f"任务 {self._name} 已启动")

    def stop(self):
        """停止任务（设置停止标志，等待线程退出并执行 teardown）"""
        self._stop_event.set()
        self._pause_event.set()  # 如果在暂停中，唤醒线程使其退出
        
        # 等待线程实际退出（避免竞态：stop 后立即断开设备，线程还在用连接）
        if self._thread and self._thread.is_alive():
            if threading.current_thread() is not self._thread:
                self._thread.join(timeout=5)
        
        self._set_status(TaskStatus.STOPPED)
        self._logger.info(f"任务 {self._name} 已停止")

    def pause(self):
        """暂停任务"""
        if self.get_status() != TaskStatus.RUNNING:
            return
        self._pause_event.clear()
        self._set_status(TaskStatus.PAUSED)
        self._logger.info(f"任务 {self._name} 已暂停")

    def resume(self):
        """恢复任务"""
        if self.get_status() != TaskStatus.PAUSED:
            return
        self._pause_event.set()
        self._set_status(TaskStatus.RUNNING)
        self._logger.info(f"任务 {self._name} 已恢复")

    def get_status(self) -> TaskStatus:
        """获取当前任务状态

        Returns:
            当前任务状态
        """
        with self._lock:
            return self._status

    # ---- 子类可用的辅助方法 ----

    def sleep(self, seconds: float):
        """可中断的睡眠，响应暂停和停止请求

        子类在 execute() 循环中应调用此方法代替 time.sleep()

        Args:
            seconds: 睡眠时间（秒）
        """
        import time as _time

        # 如果停止事件被设置，立即返回
        if self._stop_event.is_set():
            return

        # 正常运行时，执行真实睡眠
        _time.sleep(seconds)

        # 睡眠结束后如果被暂停，阻塞直到恢复或停止
        while not self._pause_event.is_set() and not self._stop_event.is_set():
            self._pause_event.wait(timeout=0.1)

    @property
    def is_stopped(self) -> bool:
        """是否已被请求停止"""
        return self._stop_event.is_set()

    # ---- 内部方法 ----

    def _run_loop(self):
        """后台线程主入口：setup -> execute -> teardown"""
        try:
            self._logger.debug(f"[{self._name}] 执行 setup")
            self.setup()

            if not self._stop_event.is_set():
                self._logger.debug(f"[{self._name}] 执行 execute")
                self.execute()

        except Exception as e:
            self._logger.error(f"请确定安卓模拟器已启动", exc_info=True)
            self._set_status(TaskStatus.ERROR)
        finally:
            try:
                self._logger.debug(f"[{self._name}] 执行 teardown")
                self.teardown()
            except Exception as e:
                self._logger.error(f"[{self._name}] teardown 异常: {e}", exc_info=True)

            # 如果不是出错状态，则设置为已停止
            if self.get_status() == TaskStatus.RUNNING:
                self._set_status(TaskStatus.STOPPED)

    def _set_status(self, status: TaskStatus):
        """线程安全地设置状态"""
        with self._lock:
            self._status = status
