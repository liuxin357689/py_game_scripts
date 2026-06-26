"""
帧任务基类与动作类型

设计思路：
    在截图共享架构下，ScreenshotService 负责截图和推送，
    每个 FrameTask 只需实现 on_frame(screen) 方法：
        - 分析当前帧，判断是否需要执行操作
        - 返回 Action 对象（需要操作）或 None（跳过）

    ScreenshotService 收集所有任务的 Action，按优先级仲裁，
    每帧只允许最高优先级的一个任务执行写操作。

放置类游戏适用：
    - 帧率约 1-2fps，无需高频截图
    - 任务间通过优先级解决冲突，无需互斥锁
    - 任务内部自行维护跨帧状态（状态机）
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np


# ---- 动作类型 ----

@dataclass
class TapAction:
    """点击动作"""
    x: int
    y: int
    description: str = ""


@dataclass
class SwipeAction:
    """滑动动作"""
    x1: int
    y1: int
    x2: int
    y2: int
    duration_ms: int = 300
    description: str = ""


@dataclass
class KeyAction:
    """按键动作（Android keycode）"""
    keycode: int
    description: str = ""


# 所有动作类型的联合类型
Action = TapAction | SwipeAction | KeyAction


# ---- 帧任务基类 ----

class FrameTask(ABC):
    """帧任务基类 — 截图共享架构下的任务抽象

    子类需实现：
        - on_frame(screen): 处理一帧画面，返回 Action 或 None
        - setup(): 加载模板、配置等资源（在 ScreenshotService 启动前调用）
        - teardown(): 清理资源（在 ScreenshotService 停止后调用）

    任务内部状态（如状态机）由子类自行管理，
    ScreenshotService 不介入任务的业务逻辑。
    """

    def __init__(self, name: str, priority: int = 50):
        """
        Args:
            name: 任务名称（用于日志和优先级配置匹配）
            priority: 优先级，数字越小优先级越高（0 = 最高）
        """
        self._name = name
        self._priority = priority
        self._logger = logging.getLogger(
            f"game_platform.frame_task.{name}"
        )
        self._active = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def priority(self) -> int:
        return self._priority

    @priority.setter
    def priority(self, value: int):
        self._priority = value

    @property
    def is_active(self) -> bool:
        """任务是否处于激活状态（参与帧处理）"""
        return self._active

    def activate(self):
        """激活任务（开始参与帧处理）"""
        self._active = True
        self._logger.info(f"[{self._name}] 已激活")

    def deactivate(self):
        """停用任务（不再参与帧处理）"""
        self._active = False
        self._logger.info(f"[{self._name}] 已停用")

    # ---- 子类必须实现 ----

    @abstractmethod
    def on_frame(self, screen: np.ndarray) -> Optional[Action]:
        """处理一帧画面

        Args:
            screen: BGR 格式的截图（numpy array）

        Returns:
            Action 对象表示需要执行的操作，None 表示本帧无需操作
        """

    # ---- 子类可选覆写 ----

    def setup(self):
        """初始化资源（加载模板、配置等）

        在 ScreenshotService.start() 时调用，
        所有任务的 setup 在主循环开始前完成。
        """

    def teardown(self):
        """清理资源

        在 ScreenshotService.stop() 时调用。
        """

    def on_action_executed(self, action: Action):
        """当本任务的动作被执行后回调

        可用于更新内部状态（如状态机切换）。

        Args:
            action: 已执行的动作
        """

    def on_frame_skipped(self):
        """当本帧本任务有动作但被优先级更高的任务抢占时回调

        可用于处理"想操作但没轮到"的情况。
        默认不做处理。
        """

    def annotate_detection(
        self,
        screen: np.ndarray,
        action: Optional["Action"],
    ) -> np.ndarray:
        """在截图上绘制检测结果标注（供测试模式使用）

        子类可覆盖此方法，绘制自己任务特有的检测区域和识别结果。
        默认实现只标注任务名、激活状态和返回的动作。

        Args:
            screen: 原始截图（BGR格式）
            action: 本帧返回的动作（可能为None）

        Returns:
            标注后的截图副本
        """
        import cv2

        canvas = screen.copy()
        h, w = canvas.shape[:2]

        # 标题背景
        cv2.rectangle(canvas, (0, 0), (w, 40), (30, 30, 30), -1)

        # 任务名称
        status = "激活" if self._active else "未激活"
        label = f"[{self._name}] {status}"
        if action is not None:
            label += f" | {action}"
        cv2.putText(canvas, label, (8, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (255, 255, 255), 1, cv2.LINE_AA)

        # 如果有动作，在点击位置画圆
        if isinstance(action, TapAction):
            cv2.circle(canvas, (action.x, action.y), 15,
                       (0, 255, 0), 2)
            cv2.putText(canvas, action.description or "点击",
                        (action.x + 20, action.y + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (0, 255, 0), 1, cv2.LINE_AA)

        return canvas
