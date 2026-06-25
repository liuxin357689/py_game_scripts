"""
坐标驱动的屏幕导航器

基于固定坐标和像素检测驱动页面导航。
所有坐标值从 YAML 配置文件加载，不硬编码。
"""

import time
import logging
from typing import Optional

from .pixel_checker import PixelChecker

logger = logging.getLogger(__name__)


class ScreenPilot:
    """坐标驱动的屏幕导航器"""

    def __init__(self, device, pixel_checker: PixelChecker, nav_config: dict):
        """
        Args:
            device: ADBDevice 实例
            pixel_checker: PixelChecker 实例
            nav_config: 从 YAML 加载的导航配置（screens + modules）
        """
        self._device = device
        self._pc = pixel_checker
        self._nav = nav_config
        self._logger = logger

    @property
    def pixel_checker(self) -> PixelChecker:
        """获取关联的 PixelChecker"""
        return self._pc

    def tap(self, x: int, y: int, duration_ms: int = 50):
        """点击指定坐标

        Args:
            x: 横坐标
            y: 纵坐标
            duration_ms: 点击持续时间（毫秒）
        """
        self._device.shell(f"input tap {x} {y}")
        self._logger.debug(f"点击 ({x}, {y})")

    def tap_and_wait(
        self, x: int, y: int, state_check: list, timeout: float = 5.0
    ) -> bool:
        """点击坐标并等待目标状态出现

        Args:
            x: 横坐标
            y: 纵坐标
            state_check: [(x, y, expected_rgb), ...] 目标状态检测点
            timeout: 超时时间（秒）

        Returns:
            目标状态是否出现
        """
        self.tap(x, y)
        return self.wait_for_state(state_check, timeout)

    def wait_for_state(self, state_check: list, timeout: float = 5.0) -> bool:
        """轮询检测目标状态，超时返回 False

        Args:
            state_check: [(x, y, expected_rgb), ...] 目标状态检测点
            timeout: 超时时间（秒）

        Returns:
            目标状态是否在超时前出现
        """
        start = time.time()
        while time.time() - start < timeout:
            if self._pc.check_state(state_check):
                return True
            time.sleep(0.3)
        self._logger.warning(f"等待状态超时 ({timeout}s)")
        return False

    def detect_current_screen(self) -> str:
        """检测当前所在哪个页面

        遍历所有已知页面的状态检测点，返回第一个匹配的页面名称。

        Returns:
            页面名称字符串，未匹配到返回 "unknown"
        """
        for screen_name, screen_cfg in self._nav.get("screens", {}).items():
            if self._pc.check_state(screen_cfg.get("detect", [])):
                return screen_name
        return "unknown"

    def go_home(self) -> bool:
        """返回主界面

        检测当前是否在主界面，不在则按 BACK 直到回到主界面（最多 5 次）。

        Returns:
            是否成功回到主界面
        """
        home_detect = self._nav.get("screens", {}).get("home", {}).get("detect", [])
        if not home_detect:
            self._logger.error("未配置主界面检测点")
            return False

        for attempt in range(5):
            if self._pc.check_state(home_detect):
                return True
            self._device.shell("input keyevent KEYCODE_BACK")
            time.sleep(0.5)
            self._pc.invalidate_cache()

        self._logger.warning("返回主界面失败（5 次 BACK 后仍未检测到主界面）")
        return False

    def navigate_to(self, screen_name: str) -> bool:
        """按配置的导航路径跳转到目标页面

        先检测是否已在目标页面，不在则先回主界面再按步骤跳转。

        Args:
            screen_name: 目标页面名称（需在 YAML 配置中定义）

        Returns:
            是否成功到达目标页面
        """
        screens = self._nav.get("screens", {})
        if screen_name not in screens:
            self._logger.error(f"未知的目标页面: {screen_name}")
            return False

        target = screens[screen_name]

        # 已在目标页面
        if self._pc.check_state(target.get("detect", [])):
            return True

        # 先回主界面
        if not self.go_home():
            return False

        # 按导航步骤跳转
        for step in target.get("steps", []):
            if "tap" in step:
                self.tap(*step["tap"])
            if "wait" in step:
                if not self.wait_for_state(step["wait"], timeout=5):
                    self._logger.warning(f"导航步骤超时: {screen_name}")
                    return False
            self._pc.invalidate_cache()
            time.sleep(step.get("delay", 0.3))

        # 最终确认
        if not self._pc.check_state(target.get("detect", [])):
            self._logger.warning(f"导航完成但未检测到目标页面: {screen_name}")
            return False

        return True
