"""
像素颜色检测器

通过 ADB 截图后读取指定坐标的像素颜色，判断当前画面状态。
截图使用 `adb exec-out screencap -p` 获取 PNG 二进制数据，直接内存解析，不落盘。
100ms 内复用同一张截图，减少 ADB 通信开销。
"""

import time
import io
import logging
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)


class PixelChecker:
    """像素颜色检测器：通过截图采样指定坐标的 RGB 值"""

    def __init__(self, device, cache_ms: int = 100, tolerance: int = 30):
        """
        Args:
            device: ADBDevice 实例
            cache_ms: 截图缓存有效期（毫秒），避免频繁截图
            tolerance: 颜色匹配的默认容差
        """
        self._device = device
        self._cache_ms = cache_ms
        self._tolerance = tolerance
        self._last_screenshot: Optional[Image.Image] = None
        self._last_screenshot_time: float = 0

    def _take_screenshot(self) -> Image.Image:
        """截图（带缓存，cache_ms 内不重复截图）

        Returns:
            PIL.Image 对象

        Raises:
            ConnectionError: ADB 连接异常
        """
        now = time.time()
        if (
            self._last_screenshot is not None
            and (now - self._last_screenshot_time) * 1000 < self._cache_ms
        ):
            return self._last_screenshot

        raw = self._device.screenshot()
        self._last_screenshot = Image.open(io.BytesIO(raw))
        self._last_screenshot_time = now
        return self._last_screenshot

    def get_pixel(self, x: int, y: int) -> tuple:
        """获取指定坐标的 (R, G, B) 值

        Args:
            x: 横坐标
            y: 纵坐标

        Returns:
            (R, G, B) 元组，各分量 0-255
        """
        img = self._take_screenshot()
        return img.getpixel((x, y))[:3]

    def match_color(self, actual: tuple, expected: tuple, tolerance: Optional[int] = None) -> bool:
        """颜色匹配，允许 +/- tolerance 的色差

        Args:
            actual: 实际颜色 (R, G, B)
            expected: 期望颜色 (R, G, B)
            tolerance: 容差，None 时使用实例默认值

        Returns:
            是否匹配
        """
        tol = tolerance if tolerance is not None else self._tolerance
        return all(abs(a - e) <= tol for a, e in zip(actual[:3], expected[:3]))

    def check_state(self, checks: list[tuple]) -> bool:
        """批量检测一组像素点是否匹配预期颜色

        Args:
            checks: [(x, y, expected_rgb), ...] 检测点列表

        Returns:
            全部匹配返回 True，任一不匹配返回 False
        """
        img = self._take_screenshot()
        for x, y, expected in checks:
            actual = img.getpixel((x, y))[:3]
            if not self.match_color(actual, expected):
                logger.debug(
                    f"像素检测不匹配: ({x},{y}) 实际={actual} 期望={expected}"
                )
                return False
        return True

    def invalidate_cache(self):
        """手动使截图缓存失效（用于需要强制刷新的场景）"""
        self._last_screenshot = None
        self._last_screenshot_time = 0
