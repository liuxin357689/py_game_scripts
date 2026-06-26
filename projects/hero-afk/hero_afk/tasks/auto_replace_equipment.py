"""
自动替换装备任务（帧任务版）

通过模板匹配检测红色「替换」按钮（replace_btn.png）— 全图扫描。
检测到后返回 TapAction，由 ScreenshotService 执行。

截图共享架构：不自行截图，由 ScreenshotService 推送帧画面。

模板来源: game_platform/screenshot/templates/
"""

import logging
import os

import cv2
import numpy as np

from game_platform.task.frame_task import FrameTask, TapAction

logger = logging.getLogger(__name__)

# 模板资源目录
_TEMPLATES_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..", "game_platform", "screenshot", "templates",
))


class AutoReplaceEquipment(FrameTask):
    """自动替换装备 — 帧任务版"""

    TEMPLATE_FILE = "replace_btn.png"

    def __init__(self, threshold: float = 0.7):
        """
        Args:
            threshold: 模板匹配置信度阈值
        """
        super().__init__(name="自动替换装备", priority=30)
        self._threshold = threshold
        self._template_img = None
        self._click_count = 0

    # ---- 生命周期 ----

    def setup(self):
        """加载模板"""
        self._load_template()

    def teardown(self):
        self._logger.info(
            f"自动替换装备结束, 累计点击 {self._click_count} 次"
        )

    # ---- 帧处理 ----

    def on_frame(self, screen: np.ndarray):
        """检测替换按钮，命中则返回 TapAction"""
        hit, pos = self._detect_replace_btn(screen)
        if hit:
            self._logger.info(
                f"检测到替换按钮: {pos}, "
                f"置信度 >= {self._threshold}"
            )
            return TapAction(pos[0], pos[1], description="点击替换按钮")
        return None

    def on_action_executed(self, action):
        self._click_count += 1

    # ---- 模板匹配 ----

    def _detect_replace_btn(self, screen: np.ndarray):
        """模板匹配替换按钮（全图扫描）

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
        """加载模板图片"""
        path = os.path.join(_TEMPLATES_DIR, self.TEMPLATE_FILE)
        if not os.path.exists(path):
            raise FileNotFoundError(f"模板图片不存在: {path}")
        self._template_img = cv2.imread(path)
        if self._template_img is None:
            raise RuntimeError(f"模板图片读取失败: {path}")
        h, w = self._template_img.shape[:2]
        self._logger.info(f"模板已加载: {self.TEMPLATE_FILE} ({w}x{h})")
