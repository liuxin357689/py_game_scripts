"""
任务调度器 — 优先级仲裁 + 冷却管理

职责：
    1. 根据优先级、冷却时间、任务冲突确定当前应执行的任务
    2. 管理任务冷却时间
    3. 检查任务依赖关系
"""

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TaskScheduler:
    """任务调度器（优先级仲裁 + 冷却管理）"""

    def __init__(self):
        self._cooldowns: dict[str, float] = {}       # task_id -> 冷却到期时间戳
        self._running: dict[str, bool] = {}           # task_id -> 是否正在执行
        self._failure_count: dict[str, int] = {}      # task_id -> 累计失败次数
        self._max_failures: dict[str, int] = {}       # task_id -> 最大允许失败次数

    # ---- 冷却管理 ----

    def set_cooldown(self, task_id: str, seconds: int):
        """设置任务冷却时间"""
        self._cooldowns[task_id] = time.time() + seconds
        logger.info(f"[Scheduler] {task_id} 进入冷却: {seconds}s")

    def clear_cooldown(self, task_id: str):
        """清除任务冷却"""
        self._cooldowns.pop(task_id, None)

    def is_on_cooldown(self, task_id: str) -> bool:
        """任务是否在冷却中"""
        expiry = self._cooldowns.get(task_id, 0)
        return time.time() < expiry

    def cooldown_remaining(self, task_id: str) -> float:
        """剩余冷却秒数（0 = 可执行）"""
        expiry = self._cooldowns.get(task_id, 0)
        remaining = expiry - time.time()
        return max(0.0, remaining)

    # ---- 执行状态 ----

    def start_task(self, task_id: str):
        """标记任务开始执行"""
        self._running[task_id] = True

    def finish_task(self, task_id: str, success: bool = True):
        """标记任务执行完毕"""
        self._running.pop(task_id, None)
        if not success:
            self._failure_count[task_id] = self._failure_count.get(task_id, 0) + 1

    def is_running(self, task_id: str) -> bool:
        """任务是否正在执行"""
        return self._running.get(task_id, False)

    # ---- 失败追踪 ----

    def set_max_failures(self, task_id: str, max_count: int):
        """设置任务最大允许失败次数"""
        self._max_failures[task_id] = max_count

    def reset_failures(self, task_id: str):
        """重置失败计数"""
        self._failure_count.pop(task_id, None)

    def failure_count(self, task_id: str) -> int:
        """获取失败次数"""
        return self._failure_count.get(task_id, 0)

    def is_blocked_by_failures(self, task_id: str) -> bool:
        """任务是否因连续失败被阻止"""
        max_f = self._max_failures.get(task_id, 3)
        return self._failure_count.get(task_id, 0) >= max_f

    # ---- 依赖检查 ----

    def check_dependencies(self, task_id: str, dependencies: list[str]) -> bool:
        """检查任务依赖是否满足（依赖任务不在运行中 = 满足）"""
        for dep in dependencies:
            if self.is_running(dep):
                return False
        return True

    # ---- 仲裁 ----

    def can_execute(self, task_id: str, dependencies: list[str] | None = None) -> bool:
        """综合判断任务是否可执行

        依次检查：
            1. 未在运行
            2. 未在冷却
            3. 未因连续失败被阻止
            4. 依赖已满足
        """
        if self.is_running(task_id):
            return False
        if self.is_on_cooldown(task_id):
            return False
        if self.is_blocked_by_failures(task_id):
            return False
        if dependencies and not self.check_dependencies(task_id, dependencies):
            return False
        return True

    def resolve_conflict(self, candidates: list[dict]) -> Optional[dict]:
        """从候选任务列表中选择优先级最高且可执行的任务

        Args:
            candidates: [{"task_id": str, "priority": int, "dependencies": list}, ...]

        Returns:
            胜出的任务 dict，或 None（全部被阻止）
        """
        valid = []
        for c in candidates:
            tid = c["task_id"]
            deps = c.get("dependencies", [])
            if self.can_execute(tid, deps):
                valid.append(c)

        if not valid:
            return None

        # 按 priority 升序排列（值越小优先级越高）
        valid.sort(key=lambda c: c["priority"])
        return valid[0]

    def tick(self):
        """每帧调用，清理过期冷却（可选优化）"""
        now = time.time()
        expired = [tid for tid, exp in self._cooldowns.items() if now >= exp]
        for tid in expired:
            del self._cooldowns[tid]

    # ---- 状态快照 ----

    def get_status(self) -> dict:
        """获取调度器当前状态快照"""
        return {
            "cooldowns": {
                tid: round(self.cooldown_remaining(tid), 1)
                for tid in self._cooldowns
            },
            "running": list(self._running.keys()),
            "failures": dict(self._failure_count),
        }
