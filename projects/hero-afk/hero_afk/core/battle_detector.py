"""
战斗结果检测器 — 公共工具模块

模板匹配检测战斗胜利/失败，供所有有战斗流程的任务共用。
模板图片和关闭坐标均为固定值。

用法:
    from hero_afk.core.battle_detector import battle_detector

    class SomeTask(FrameTask):
        def setup(self):
            battle_detector.setup()

        def on_frame(self, screen):
            result = battle_detector.detect(screen)
            if result:
                cx, cy = battle_detector.CLOSE_TAP_POS
                return TapAction(cx, cy, ...)
"""

import logging
import os

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# 模板资源目录（game_platform/screenshot/templates）
_TEMPLATES_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..", "game_platform", "screenshot", "templates",
))


class BattleResultDetector:
    """战斗结果检测器（模板匹配）

    固定模板：zdsb.png（战斗失败）、zdsl.png（战斗胜利）
    固定关闭坐标：(450, 1500)
    """

    TEMPLATE_FAIL = "zdsb.png"
    TEMPLATE_WIN = "zdsl.png"
    CLOSE_TAP_POS = (450, 1500)

    def __init__(self, threshold: float = 0.7):
        self._threshold = threshold
        self._tpl_fail = None
        self._tpl_win = None
        self._screen_gray = None  # 缓存灰度图，避免重复转换

    def setup(self):
        """加载模板图片（只需调用一次）"""
        for name, filename in [
            ("fail", self.TEMPLATE_FAIL),
            ("win", self.TEMPLATE_WIN),
        ]:
            path = os.path.join(_TEMPLATES_DIR, filename)
            if not os.path.exists(path):
                raise FileNotFoundError(f"模板图片不存在: {path}")
            img = cv2.imread(path)
            if img is None:
                raise RuntimeError(f"模板图片读取失败: {path}")
            h, w = img.shape[:2]
            if name == "fail":
                self._tpl_fail = img
            else:
                self._tpl_win = img
            logger.info(f"[BattleDetector] 模板已加载: {filename} ({w}x{h})")

    def detect(self, screen: np.ndarray) -> str:
        """检测战斗结果

        Args:
            screen: BGR 截图

        Returns:
            "战斗失败" / "战斗胜利" / ""（未检测到）
        """
        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)

        for tpl, label in [
            (self._tpl_fail, "战斗失败"),
            (self._tpl_win, "战斗胜利"),
        ]:
            if tpl is None:
                continue
            tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
            result = cv2.matchTemplate(
                screen_gray, tpl_gray, cv2.TM_CCOEFF_NORMED
            )
            _, max_val, _, _ = cv2.minMaxLoc(result)
            if max_val >= self._threshold:
                logger.info(
                    f"[BattleDetector] {label} "
                    f"置信度 {max_val:.4f}"
                )
                return label

        return ""


# 模块级单例 — 所有任务共享同一个实例（模板只加载一次）
battle_detector = BattleResultDetector()
