"""
混沌牧场任务（帧任务版）

状态机：
    LOOKING_CHALLENGE → 检测挑战按钮 → 点击 → LOOKING_RESULT
    LOOKING_RESULT    → 检测战斗结果 → 关闭结算 → LOOKING_CHALLENGE / BATTLE_FAILED

截图共享架构：不自行截图，由 ScreenshotService 推送帧画面。

模板来源: game_platform/screenshot/templates/
坐标数据: game_platform/screenshot/templates/templates.json
"""

import logging
import os
from enum import Enum, auto

import cv2
import numpy as np

from game_platform.task.frame_task import FrameTask, TapAction
from hero_afk.core.battle_detector import battle_detector

logger = logging.getLogger(__name__)

# 模板资源目录
_TEMPLATES_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..", "game_platform", "screenshot", "templates",
))


class _State(Enum):
    LOOKING_CHALLENGE = auto()
    LOOKING_RESULT = auto()
    BATTLE_FAILED = auto()


class AutoChaosRanch(FrameTask):
    """混沌牧场 — 帧任务版"""

    TEMPLATE_FILE = "tz.png"

    def __init__(
        self,
        threshold: float = 0.7,
    ):
        """
        Args:
            threshold: 模板匹配置信度阈值
        """
        super().__init__(name="混沌牧场", priority=40)
        self._threshold = threshold
        self._template_img = None
        self._click_count = 0
        self._state = _State.LOOKING_CHALLENGE
        self._wait_frames = 0
        self._MAX_WAIT = 90  # 战斗动画最长等待帧数

    def activate(self):
        """激活任务 — 重置状态机，确保重启后从初始状态开始"""
        super().activate()
        self._state = _State.LOOKING_CHALLENGE
        self._wait_frames = 0
        self._logger.info("状态已重置 -> LOOKING_CHALLENGE")

    # ---- 生命周期 ----

    def setup(self):
        """加载模板"""
        self._load_template()
        battle_detector.setup()

    def teardown(self):
        self._logger.info(
            f"混沌牧场结束, 累计点击 {self._click_count} 次"
        )

    # ---- 帧处理 ----

    def on_frame(self, screen: np.ndarray):
        """处理一帧"""
        if self._state == _State.BATTLE_FAILED:
            return None

        if self._state == _State.LOOKING_CHALLENGE:
            return self._handle_challenge(screen)

        elif self._state == _State.LOOKING_RESULT:
            return self._handle_result(screen)

        return None

    def on_action_executed(self, action):
        self._click_count += 1

    # ---- 状态处理 ----

    def _handle_challenge(self, screen: np.ndarray):
        """检测挑战按钮"""
        hit, pos = self._detect_challenge_btn(screen)
        if hit:
            self._logger.info(
                f"检测到挑战按钮: {pos}, 置信度 >= {self._threshold}"
            )
            self._state = _State.LOOKING_RESULT
            self._wait_frames = 0
            return TapAction(pos[0], pos[1], description="点击挑战按钮")
        return None

    def _handle_result(self, screen: np.ndarray):
        """检测战斗结果"""
        result = battle_detector.detect(screen)
        cx, cy = battle_detector.CLOSE_TAP_POS

        if result == "战斗失败":
            self._logger.info("战斗失败，任务停止")
            self._state = _State.BATTLE_FAILED
            return TapAction(cx, cy, description="关闭结算(失败)")

        if result == "战斗胜利":
            self._logger.info("战斗胜利，关闭结算")
            self._state = _State.LOOKING_CHALLENGE
            self._wait_frames = 0
            return TapAction(cx, cy, description="关闭结算(胜利)")

        # 超时保护
        self._wait_frames += 1
        if self._wait_frames > self._MAX_WAIT:
            self._logger.warning(
                f"等待战斗结果超时 ({self._wait_frames} 帧)，"
                f"回退到挑战按钮"
            )
            self._state = _State.LOOKING_CHALLENGE
            self._wait_frames = 0

        return None

    # ---- 模板匹配 ----

    def _detect_challenge_btn(self, screen: np.ndarray):
        """模板匹配挑战按钮（全图扫描）

        Returns:
            (hit: bool, pos: tuple|None)
        """
        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.cvtColor(self._template_img, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(
            screen_gray, tpl_gray, cv2.TM_CCOEFF_NORMED
        )
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= self._threshold:
            th, tw = tpl_gray.shape[:2]
            cx = max_loc[0] + tw // 2
            cy = max_loc[1] + th // 2
            return True, (cx, cy)
        return False, None

    # ---- 内部方法 ----

    def _load_template(self):
        """加载模板"""
        path = os.path.join(_TEMPLATES_DIR, self.TEMPLATE_FILE)
        if not os.path.exists(path):
            raise FileNotFoundError(f"模板图片不存在: {path}")
        self._template_img = cv2.imread(path)
        if self._template_img is None:
            raise RuntimeError(f"模板图片读取失败: {path}")
        h, w = self._template_img.shape[:2]
        self._logger.info(f"模板已加载: {self.TEMPLATE_FILE} ({w}x{h})")
