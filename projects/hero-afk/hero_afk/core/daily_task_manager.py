"""
每日任务管理器 — 全局任务编排器

职责：
    1. 管理每日任务执行计划和调度
    2. 集成 TaskScheduler（冷却/冲突） + ScreenshotService（帧推送）
    3. 根据时间窗口和冷却时间自动激活/停用任务
    4. 处理任务失败和重试逻辑

与现有 GUI 的关系：
    DailyTaskManager 是 FrameTaskManagerAdapter 的增强层。
    FrameTaskManagerAdapter 负责设备级任务生命周期（创建、注册到 ScreenshotService），
    DailyTaskManager 负责全局调度策略（何时激活、何时冷却、何时重试）。
"""

import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class DailyTaskManager:
    """每日任务管理器（全局任务编排器）"""

    def __init__(self, task_registry):
        """
        Args:
            task_registry: TaskRegistry 实例（已加载任务定义和工厂）
        """
        from hero_afk.core.task_scheduler import TaskScheduler

        self._registry = task_registry
        self._scheduler = TaskScheduler()
        self._schedule: dict[str, dict] = {}   # task_id -> 调度配置
        self._enabled: dict[str, bool] = {}    # task_id -> 是否启用
        self._failure_tracker: dict[str, dict] = {}  # task_id -> 失败统计
        self._running = False

    # ---- 调度配置 ----

    def load_schedule(self, config: dict):
        """加载调度配置

        Args:
            config: 调度配置字典，结构如下：
                {
                    "task_id": {
                        "enabled": True,
                        "schedule": {"start": "08:00", "end": "23:00"},
                        "cooldown": 1800
                    },
                    ...
                }
        """
        for task_id, task_config in config.items():
            self._schedule[task_id] = task_config.get("schedule", {})
            self._enabled[task_id] = task_config.get("enabled", True)

            # 将冷却和失败上限同步到调度器
            defn = None
            try:
                defn = self._registry.get_definition(task_id)
            except KeyError:
                pass

            cooldown = task_config.get(
                "cooldown",
                defn.cooldown if defn else 0,
            )
            max_fail = task_config.get(
                "max_failures",
                defn.max_failures if defn else 3,
            )
            self._scheduler.set_max_failures(task_id, max_fail)

        logger.info(
            f"[DailyTaskManager] 加载了 {len(self._schedule)} 个调度配置"
        )

    # ---- 生命周期 ----

    def start(self, screenshot_service=None):
        """启动任务管理器

        Args:
            screenshot_service: ScreenshotService 实例（可选，用于直接控制任务激活）
        """
        self._screenshot_service = screenshot_service
        self._running = True
        logger.info("[DailyTaskManager] 已启动")

    def stop(self):
        """停止任务管理器"""
        self._running = False
        logger.info("[DailyTaskManager] 已停止")

    # ---- 核心调度逻辑 ----

    def tick(self):
        """每帧/每周期调用：检查并更新任务状态

        流程：
            1. 清理过期冷却
            2. 遍历所有已注册任务
            3. 判断是否应该激活（启用 + 时间窗口 + 调度器允许）
            4. 通过 ScreenshotService 激活/停用任务
        """
        if not self._running:
            return

        self._scheduler.tick()

        for defn in self._registry.list_tasks():
            task_id = defn.id

            # 跳过未启用的任务
            if not self._enabled.get(task_id, True):
                continue

            # 检查时间窗口
            if not self._in_schedule_window(task_id):
                self._deactivate_task(task_id)
                continue

            # 检查调度器（冷却 + 失败 + 依赖）
            deps = self._registry.get_dependencies(task_id)
            if self._scheduler.can_execute(task_id, deps):
                self._activate_task(task_id)
            else:
                remaining = self._scheduler.cooldown_remaining(task_id)
                if remaining > 0:
                    pass  # 冷却中，不激活但不需要日志噪音
                elif self._scheduler.is_blocked_by_failures(task_id):
                    pass  # 连续失败被阻止

    # ---- 任务激活/停用 ----

    def _activate_task(self, task_id: str):
        """激活任务（通过 ScreenshotService）"""
        if self._screenshot_service:
            self._screenshot_service.activate_task(task_id)

    def _deactivate_task(self, task_id: str):
        """停用任务"""
        if self._screenshot_service:
            self._screenshot_service.deactivate_task(task_id)

    def activate_task(self, task_id: str) -> bool:
        """手动激活任务（用户操作）"""
        self._enabled[task_id] = True
        logger.info(f"[DailyTaskManager] 手动激活: {task_id}")
        return True

    def deactivate_task(self, task_id: str) -> bool:
        """手动停用任务（用户操作）"""
        self._enabled[task_id] = False
        self._deactivate_task(task_id)
        logger.info(f"[DailyTaskManager] 手动停用: {task_id}")
        return True

    def activate_all(self):
        """激活所有任务"""
        for defn in self._registry.list_tasks():
            self._enabled[defn.id] = True
        logger.info("[DailyTaskManager] 激活所有任务")

    def deactivate_all(self):
        """停用所有任务"""
        for defn in self._registry.list_tasks():
            self._enabled[defn.id] = False
            self._deactivate_task(defn.id)
        logger.info("[DailyTaskManager] 停用所有任务")

    # ---- 失败追踪与重试 ----

    def record_failure(self, task_id: str):
        """记录任务失败"""
        if task_id not in self._failure_tracker:
            self._failure_tracker[task_id] = {
                "count": 0,
                "last_failure": 0,
            }
        self._failure_tracker[task_id]["count"] += 1
        self._failure_tracker[task_id]["last_failure"] = time.time()
        self._scheduler.finish_task(task_id, success=False)
        logger.warning(
            f"[DailyTaskManager] 任务失败: {task_id} "
            f"(累计 {self._failure_tracker[task_id]['count']} 次)"
        )

    def record_success(self, task_id: str):
        """记录任务成功（重置失败计数）"""
        self._failure_tracker.pop(task_id, None)
        self._scheduler.reset_failures(task_id)
        self._scheduler.finish_task(task_id, success=True)

        # 应用冷却
        cooldown = self._registry.get_cooldown(task_id)
        if cooldown > 0:
            self._scheduler.set_cooldown(task_id, cooldown)

        logger.info(f"[DailyTaskManager] 任务完成: {task_id}, 冷却 {cooldown}s")

    def should_retry(self, task_id: str) -> bool:
        """判断任务是否应该重试"""
        policy = self._registry.get_retry_policy(task_id)
        if not policy.get("retry_on_error", False):
            return False

        tracker = self._failure_tracker.get(task_id, {})
        count = tracker.get("count", 0)
        max_attempts = policy.get("max_attempts", 3)

        if count >= max_attempts:
            return False

        # 退避检查
        backoff = policy.get("backoff_seconds", 30)
        last_failure = tracker.get("last_failure", 0)
        if time.time() - last_failure < backoff:
            return False

        return True

    def get_failure_info(self, task_id: str) -> dict:
        """获取任务失败统计"""
        return self._failure_tracker.get(task_id, {"count": 0, "last_failure": 0})

    # ---- 时间窗口 ----

    def _in_schedule_window(self, task_id: str) -> bool:
        """检查当前时间是否在任务的调度窗口内"""
        schedule = self._schedule.get(task_id, {})
        if not schedule:
            return True  # 无调度限制 = 始终可执行

        now = datetime.now()
        start_str = schedule.get("start")
        end_str = schedule.get("end")

        if not start_str or not end_str:
            return True  # 未配置起止时间 = 始终可执行

        try:
            start_time = datetime.strptime(start_str, "%H:%M").time()
            end_time = datetime.strptime(end_str, "%H:%M").time()
        except ValueError:
            logger.warning(
                f"[DailyTaskManager] {task_id} 时间格式错误: "
                f"start={start_str}, end={end_str}"
            )
            return True

        current_time = now.time()

        if start_time <= end_time:
            # 正常区间：08:00 - 23:00
            return start_time <= current_time <= end_time
        else:
            # 跨午夜区间：23:00 - 08:00
            return current_time >= start_time or current_time <= end_time

    # ---- 状态查询 ----

    def get_status(self) -> dict:
        """获取所有任务状态"""
        status = {}
        for defn in self._registry.list_tasks():
            tid = defn.id
            failure = self._failure_tracker.get(tid, {})
            status[tid] = {
                "name": defn.name,
                "priority": defn.priority,
                "enabled": self._enabled.get(tid, True),
                "cooldown_remaining": round(
                    self._scheduler.cooldown_remaining(tid), 1
                ),
                "failures": failure.get("count", 0),
                "blocked": self._scheduler.is_blocked_by_failures(tid),
                "in_schedule": self._in_schedule_window(tid),
            }
        return status

    def get_schedule(self, task_id: str) -> dict:
        """获取任务调度配置"""
        return self._schedule.get(task_id, {})
