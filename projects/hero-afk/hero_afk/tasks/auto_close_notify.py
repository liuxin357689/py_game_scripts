"""
自动关闭通知任务（帧任务版）

通过坐标+像素点检测黄色感叹号（wcrw.png）通知：
    1. 检测感叹号 → 返回点击动作
    2. 等待关闭中 → 检测「点击关闭」（close.png）→ 返回点击动作
    3. 超时自动复位

截图共享架构：不自行截图，由 ScreenshotService 推送帧画面。
只实现 on_frame(screen) 返回 TapAction 或 None。

坐标数据: game_platform/screenshot/templates/templates.json
"""

import json
import logging
import os

import numpy as np

from game_platform.task.frame_task import FrameTask, TapAction

logger = logging.getLogger(__name__)

# 模板资源目录（game_platform/screenshot/templates）
_TEMPLATES_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..", "game_platform", "screenshot", "templates",
))


class AutoCloseNotify(FrameTask):
    """自动关闭通知 — 帧任务版

    状态机：
        IDLE → 检测感叹号 → 点击 → WAITING_CLOSE
        WAITING_CLOSE → 检测关闭按钮 → 点击 → IDLE
        WAITING_CLOSE → 超时(5帧) → IDLE
    """

    # 像素检测目标
    _PIXEL_TARGETS = {
        "quest_notify": {
            "file": "wcrw.png",
            "description": "黄色感叹号通知",
        },
        "close_btn": {
            "file": "close.png",
            "description": "点击关闭按钮",
        },
    }

    # 等待关闭按钮的最大空转帧数
    _MAX_STALE_FRAMES = 5

    def __init__(self, pixel_tolerance: int = 40):
        """
        Args:
            pixel_tolerance: 像素颜色容差（RGB 各通道）
        """
        super().__init__(name="自动完成任务", priority=10)
        self._pixel_tolerance = pixel_tolerance
        self._pixel_config: dict = {}
        self._click_count = 0
        self._waiting_for_close = False
        self._stale_frames = 0

    def activate(self):
        """激活任务 — 重置状态，确保重启后不会卡在中间态"""
        super().activate()
        self._waiting_for_close = False
        self._stale_frames = 0
        self._logger.info("状态已重置")

    # ---- 生命周期 ----

    def setup(self):
        """加载像素检测配置"""
        self._load_pixel_config()

    def teardown(self):
        """清理"""
        self._logger.info(
            f"自动完成任务结束, 累计点击 {self._click_count} 次"
        )

    # ---- 帧处理 ----

    def on_frame(self, screen: np.ndarray):
        """处理一帧：检测感叹号或关闭按钮

        Returns:
            TapAction 或 None
        """
        # ① 始终检测感叹号（防止状态锁死）
        if self._detect_pixel(screen, "quest_notify"):
            cfg = self._pixel_config["quest_notify"]
            cx, cy = cfg["center"]
            self._logger.info(f"检测到感叹号通知: ({cx}, {cy})")
            self._waiting_for_close = True
            self._stale_frames = 0
            return TapAction(cx, cy, description="点击感叹号通知")

        # ② 等待关闭中 → 检测关闭按钮
        if self._waiting_for_close:
            if self._detect_pixel(screen, "close_btn"):
                cfg = self._pixel_config["close_btn"]
                cx, cy = cfg["center"]
                self._logger.info(f"检测到关闭按钮: ({cx}, {cy})")
                self._waiting_for_close = False
                self._stale_frames = 0
                return TapAction(cx, cy, description="点击关闭按钮")

            # 空转计数
            self._stale_frames += 1
            if self._stale_frames >= self._MAX_STALE_FRAMES:
                self._logger.warning(
                    f"等待关闭按钮超时 "
                    f"({self._stale_frames} 帧未检测到)，复位状态"
                )
                self._waiting_for_close = False
                self._stale_frames = 0

        return None

    def on_action_executed(self, action):
        """动作执行后更新计数"""
        self._click_count += 1

    # ---- 像素检测 ----

    def _detect_pixel(self, screen: np.ndarray, key: str) -> bool:
        """多点像素检测：所有采样点匹配才算命中"""
        cfg = self._pixel_config.get(key)
        if not cfg:
            return False

        h, w = screen.shape[:2]
        tol = self._pixel_tolerance

        for sp in cfg["sample_points"]:
            sx, sy = sp["abs_pos"]
            if sx >= w or sy >= h:
                return False
            b, g, r = screen[sy, sx]
            actual = (int(r), int(g), int(b))
            expected = sp["expected_rgb"]
            if not all(abs(a - e) <= tol for a, e in zip(actual, expected)):
                return False

        return True

    # ---- 内部方法 ----

    def _load_pixel_config(self):
        """从 templates.json 加载坐标+像素点检测配置"""
        json_path = os.path.join(_TEMPLATES_DIR, "templates.json")
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"templates.json 不存在: {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            entries = json.load(f)

        by_file = {e["image_file"]: e for e in entries}

        for key, target in self._PIXEL_TARGETS.items():
            entry = by_file.get(target["file"])
            if not entry:
                raise RuntimeError(
                    f"templates.json 中未找到 "
                    f"{target['file']}（{target['description']}）"
                )
            cr = entry["crop_region"]
            cx = (cr["x1"] + cr["x2"]) // 2
            cy = (cr["y1"] + cr["y2"]) // 2

            sample_points = []
            for name, kc in entry["key_colors"].items():
                abs_x = cr["x1"] + kc["x"]
                abs_y = cr["y1"] + kc["y"]
                sample_points.append({
                    "name": name,
                    "abs_pos": (abs_x, abs_y),
                    "expected_rgb": tuple(kc["rgb"]),
                })

            self._pixel_config[key] = {
                "center": (cx, cy),
                "sample_points": sample_points,
                "description": target["description"],
            }
            self._logger.info(
                f"[{key}] {target['description']}: "
                f"中心 ({cx}, {cy}), {len(sample_points)} 个采样点"
            )
