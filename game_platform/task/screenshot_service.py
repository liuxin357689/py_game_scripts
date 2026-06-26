"""
截图服务 — 截图共享架构的核心引擎

职责：
    1. 管理 ADB 设备连接（一个设备一个连接）
    2. 截图 → 推送给所有激活的 FrameTask → 收集动作请求
    3. 优先级仲裁：每帧只允许最高优先级的一个任务执行写操作
    4. 执行动作 + 人类行为模拟延迟
    5. 设备断连时自动重连
    6. 所有任务处理完毕后立刻进入下一轮（不等待固定间隔）

流水线：
    截图 → 并行处理(所有任务 on_frame) → 仲裁 → 执行 → 截图 → ...

放在 game_platform 项目中，hero_afk 等项目只负责实现具体的 FrameTask。
"""

import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from typing import List, Optional, Tuple

import cv2
import numpy as np

from game_platform.task.frame_task import (
    FrameTask, Action, TapAction, SwipeAction, KeyAction,
)

logger = logging.getLogger(__name__)


class ScreenshotService:
    """截图服务 — 管理设备连接、截图推送、优先级仲裁"""

    # 重连配置
    _RECONNECT_DELAYS = [2, 5, 10]  # 秒，逐次递增
    _MAX_RECONNECT_ATTEMPTS = 3

    # 人类行为模拟
    _TAP_JITTER = 5          # 点击坐标随机偏移（像素）
    _TAP_DELAY_MIN = 0.3     # 点击后最小延迟（秒）
    _TAP_DELAY_MAX = 0.7     # 点击后最大延迟（秒）

    def __init__(self, device_address: str = "localhost:5555"):
        """
        Args:
            device_address: 设备地址，格式 "host:port"
        """
        self._device_address = device_address
        self._device = None

        # 任务管理
        self._tasks: List[FrameTask] = []
        self._tasks_lock = threading.Lock()

        # 服务状态
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # 统计
        self._frame_count = 0
        self._action_count = 0

    # ---- 任务管理 ----

    def register_task(self, task: FrameTask):
        """注册任务

        Args:
            task: FrameTask 实例
        """
        with self._tasks_lock:
            # 按优先级排序（数字小的在前）
            self._tasks.append(task)
            self._tasks.sort(key=lambda t: t.priority)
            logger.info(
                f"注册任务: {task.name} (优先级 {task.priority}), "
                f"当前共 {len(self._tasks)} 个任务"
            )

    def unregister_task(self, task_name: str):
        """注销任务

        Args:
            task_name: 任务名称
        """
        with self._tasks_lock:
            self._tasks = [t for t in self._tasks if t.name != task_name]
            logger.info(f"注销任务: {task_name}")

    def activate_task(self, task_name: str):
        """激活任务（开始参与帧处理）"""
        with self._tasks_lock:
            for t in self._tasks:
                if t.name == task_name:
                    t.activate()
                    return
            logger.warning(f"任务不存在: {task_name}")

    def deactivate_task(self, task_name: str):
        """停用任务"""
        with self._tasks_lock:
            for t in self._tasks:
                if t.name == task_name:
                    t.deactivate()
                    return

    def get_task(self, task_name: str) -> Optional[FrameTask]:
        """获取已注册的任务"""
        with self._tasks_lock:
            for t in self._tasks:
                if t.name == task_name:
                    return t
        return None

    @property
    def tasks(self) -> List[FrameTask]:
        """获取所有已注册的任务（副本）"""
        with self._tasks_lock:
            return list(self._tasks)

    # ---- 生命周期 ----

    def start(self):
        """启动截图服务

        流程：setup 所有任务 → 连接设备 → 启动主循环线程
        """
        if self._running:
            logger.warning("截图服务已在运行")
            return

        self._running = True

        # 1. 初始化所有任务
        for task in self._tasks:
            try:
                task.setup()
                logger.info(f"任务 {task.name} setup 完成")
            except Exception as e:
                logger.error(f"任务 {task.name} setup 失败: {e}", exc_info=True)

        # 2. 连接设备
        self._connect_device()

        # 3. 启动主循环线程
        self._thread = threading.Thread(
            target=self._main_loop, name="ScreenshotService", daemon=True
        )
        self._thread.start()
        logger.info(
            f"截图服务已启动, 设备: {self._device_address}, "
            f"任务数: {len(self._tasks)}"
        )

    def stop(self):
        """停止截图服务

        流程：停止主循环 → teardown 所有任务 → 断开设备
        """
        self._running = False

        # 等待主循环退出
        if self._thread and self._thread.is_alive():
            if threading.current_thread() is not self._thread:
                self._thread.join(timeout=10)

        # teardown 所有任务
        for task in self._tasks:
            try:
                task.teardown()
            except Exception as e:
                logger.warning(f"任务 {task.name} teardown 异常: {e}")

        # 断开设备
        self._disconnect_device()

        logger.info(
            f"截图服务已停止, 共处理 {self._frame_count} 帧, "
            f"执行 {self._action_count} 次操作"
        )

    @property
    def is_running(self) -> bool:
        return self._running

    # ---- 主循环 ----

    def _main_loop(self):
        """截图 → 推送 → 仲裁 → 执行 → 循环"""
        logger.info("截图服务主循环开始")

        while self._running:
            try:
                # ① 截图
                screen = self._take_screenshot()
                if screen is None:
                    # 截图失败，尝试重连后重试
                    if not self._reconnect():
                        break  # 重连失败，退出
                    continue

                self._frame_count += 1

                # ② 并行推送给所有激活的任务
                candidates = self._process_frame(screen)

                # ③ 仲裁：选最高优先级
                if candidates:
                    winner_task, action = candidates[0]

                    if len(candidates) > 1:
                        others = ", ".join(
                            f"{t.name}(p={t.priority})"
                            for t, _ in candidates[1:]
                        )
                        self._logger_for_task(winner_task).info(
                            f"优先级胜出 (vs {others}), "
                            f"执行: {action}"
                        )
                    else:
                        self._logger_for_task(winner_task).info(
                            f"执行: {action}"
                        )

                    # ④ 执行动作
                    self._execute_action(action)
                    self._action_count += 1

                    # 通知获胜任务
                    winner_task.on_action_executed(action)

                    # 通知被抢占的任务
                    for task, _ in candidates[1:]:
                        task.on_frame_skipped()

                    # 动作后延迟（模拟人类行为）
                    delay = random.uniform(
                        self._TAP_DELAY_MIN, self._TAP_DELAY_MAX
                    )
                    time.sleep(delay)

            except Exception as e:
                logger.error(f"主循环异常: {e}", exc_info=True)
                time.sleep(1)

        logger.info("截图服务主循环结束")

    def _process_frame(
        self, screen: np.ndarray
    ) -> List[Tuple[FrameTask, Action]]:
        """并行推送帧给所有激活任务，收集动作请求

        Returns:
            按优先级排序的 (task, action) 列表
        """
        with self._tasks_lock:
            active_tasks = [t for t in self._tasks if t.is_active]

        if not active_tasks:
            return []

        candidates = []

        if len(active_tasks) == 1:
            # 单任务：直接调用，避免线程池开销
            task = active_tasks[0]
            try:
                action = task.on_frame(screen)
                if action is not None:
                    candidates.append((task, action))
            except Exception as e:
                self._logger_for_task(task).error(
                    f"on_frame 异常: {e}", exc_info=True
                )
        else:
            # 多任务：线程池并行
            futures = {}
            with ThreadPoolExecutor(
                max_workers=len(active_tasks)
            ) as executor:
                for task in active_tasks:
                    future = executor.submit(task.on_frame, screen)
                    futures[future] = task

                wait(futures)

            for future, task in futures.items():
                try:
                    action = future.result(timeout=5)
                    if action is not None:
                        candidates.append((task, action))
                except Exception as e:
                    self._logger_for_task(task).error(
                        f"on_frame 异常: {e}", exc_info=True
                    )

        # 按优先级排序（数字小的在前）
        candidates.sort(key=lambda c: c[0].priority)
        return candidates

    # ---- 设备管理 ----

    def _connect_device(self):
        """连接 ADB 设备"""
        from game_platform.adb.device import ADBDevice

        parts = self._device_address.rsplit(":", 1)
        host = parts[0]
        port = int(parts[1]) if len(parts) == 2 else 5555

        self._device = ADBDevice(host, port)
        if not self._device.connect():
            raise ConnectionError(
                f"无法连接设备 {self._device_address}"
            )
        logger.info(f"已连接设备: {self._device_address}")

    def _disconnect_device(self):
        """断开设备连接"""
        if self._device:
            try:
                self._device.disconnect()
            except Exception:
                pass
            self._device = None

    def _take_screenshot(self) -> Optional[np.ndarray]:
        """截图并解码

        Returns:
            BGR 格式的 numpy array，失败返回 None
        """
        if not self._device:
            return None

        try:
            raw = self._device.screenshot()
            arr = np.frombuffer(raw, np.uint8)
            screen = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if screen is None:
                logger.warning("截图解码失败")
            return screen
        except Exception as e:
            err_name = type(e).__name__
            if "timeout" in err_name.lower() or "timeout" in str(e).lower():
                logger.warning(f"截图超时: {e}")
            elif "not connected" in str(e).lower() or "未连接" in str(e):
                logger.warning(f"设备未连接: {e}")
            else:
                logger.error(f"截图异常: {e}", exc_info=True)
            return None

    def _reconnect(self) -> bool:
        """尝试重连设备

        Returns:
            重连成功返回 True
        """
        for attempt, delay in enumerate(self._RECONNECT_DELAYS):
            if not self._running:
                return False

            logger.info(
                f"[重连] 第 {attempt + 1} 次尝试, "
                f"等待 {delay} 秒..."
            )
            time.sleep(delay)

            # 断开旧连接
            self._disconnect_device()

            try:
                self._connect_device()
                logger.info(f"[重连] 成功: {self._device_address}")
                return True
            except Exception as e:
                logger.warning(f"[重连] 失败: {e}")

        logger.error(
            f"[重连] 已达最大重试次数 ({self._MAX_RECONNECT_ATTEMPTS}), "
            f"截图服务停止"
        )
        self._running = False
        return False

    # ---- 动作执行 ----

    def _execute_action(self, action: Action):
        """执行动作（写操作）

        所有写操作都通过此方法串行执行，
        避免多任务并发操作设备。
        """
        if not self._device:
            logger.warning("设备未连接，跳过动作执行")
            return

        try:
            if isinstance(action, TapAction):
                # 人类行为模拟：随机偏移
                jx = random.randint(-self._TAP_JITTER, self._TAP_JITTER)
                jy = random.randint(-self._TAP_JITTER, self._TAP_JITTER)
                x, y = action.x + jx, action.y + jy
                self._device.tap_human_like(x, y)

            elif isinstance(action, SwipeAction):
                self._device.swipe(
                    action.x1, action.y1,
                    action.x2, action.y2,
                    action.duration_ms,
                )

            elif isinstance(action, KeyAction):
                self._device.key_event(action.keycode)

            else:
                logger.warning(f"未知动作类型: {type(action)}")

        except Exception as e:
            logger.error(f"动作执行失败: {action} -> {e}", exc_info=True)

    # ---- 辅助 ----

    @staticmethod
    def _logger_for_task(task: FrameTask) -> logging.Logger:
        """获取任务对应的 logger"""
        return task._logger
