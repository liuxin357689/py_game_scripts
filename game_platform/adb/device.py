"""
ADB 设备管理类

职责:
    - 连接/断开 ADB 设备
    - 封装屏幕操作（点击、滑动、按键）
    - 截图功能
    - 设备状态检测
"""

import os
import logging
import time
import random
from pathlib import Path
from typing import Optional, Tuple

import cv2

from adb_shell.adb_device import AdbDeviceTcp, AdbDeviceUsb
from adb_shell.auth.sign_pythonrsa import PythonRSASigner
from adb_shell.auth.keygen import keygen

logger = logging.getLogger(__name__)


def _get_adb_key_path() -> Path:
    """获取 ADB 密钥文件路径，不存在则自动生成"""
    key_dir = Path.home() / ".game_scripts"
    key_dir.mkdir(exist_ok=True)
    priv_path = key_dir / "adbkey"
    pub_path = key_dir / "adbkey.pub"
    if not priv_path.exists():
        keygen(str(priv_path))
    return priv_path, pub_path


class ADBDevice:
    """ADB 设备控制类，封装与 Android 设备的交互"""

    def __init__(self, host: str = "localhost", port: int = 5555):
        """初始化 ADB 设备

        Args:
            host: 设备/模拟器 IP 地址
            port: 设备 ADB 端口（模拟器默认 5555）
        """
        self._host = host
        self._port = port
        self._device = None  # AdbDeviceTcp 或 AdbDeviceUsb 实例

    def connect(self) -> bool:
        """连接到 ADB 设备（TCP 模式，适用于模拟器）

        Returns:
            连接是否成功
        """
        try:
            priv_path, pub_path = _get_adb_key_path()
            with open(priv_path, "rb") as f:
                priv_key = f.read()
            with open(pub_path, "rb") as f:
                pub_key = f.read()
            signer = PythonRSASigner(pub_key, priv_key)

            self._device = AdbDeviceTcp(self._host, self._port, default_transport_timeout_s=9)
            self._device.connect(rsa_keys=[signer], auth_timeout_s=10)
            logger.info(f"已连接到设备 {self._host}:{self._port}")
            return True
        except Exception as e:
            logger.error(f"连接设备失败 {self._host}:{self._port}: {e}")
            self._device = None
            return False

    def disconnect(self):
        """断开 ADB 连接"""
        if self._device:
            try:
                self._device.close()
                logger.info(f"已断开设备 {self._host}:{self._port}")
            except Exception as e:
                logger.warning(f"断开连接时出现异常: {e}")
            finally:
                self._device = None

    def is_connected(self) -> bool:
        """检查设备是否已连接

        Returns:
            是否已连接
        """
        if self._device is None:
            return False
        try:
            # 执行一个轻量命令来验证连接
            self._device.shell("echo ok")
            return True
        except Exception:
            self._device = None
            return False

    def tap(self, x: int, y: int):
        """模拟屏幕点击

        Args:
            x: 点击的 X 坐标
            y: 点击的 Y 坐标
        """
        self._ensure_connected()
        self._device.shell(f"input tap {x} {y}")
        logger.debug(f"点击 ({x}, {y})")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300):
        """模拟屏幕滑动

        Args:
            x1: 起始 X 坐标
            y1: 起始 Y 坐标
            x2: 结束 X 坐标
            y2: 结束 Y 坐标
            duration: 滑动持续时间（毫秒）
        """
        self._ensure_connected()
        self._device.shell(f"input swipe {x1} {y1} {x2} {y2} {duration}")
        logger.debug(f"滑动 ({x1},{y1}) -> ({x2},{y2}) 耗时 {duration}ms")

    def key_event(self, keycode: int):
        """发送按键事件

        Args:
            keycode: Android 按键码（3=HOME, 4=BACK）
        """
        self._ensure_connected()
        self._device.shell(f"input keyevent {keycode}")
        logger.debug(f"按键 keycode={keycode}")

    def screenshot(self, save_path: str = None) -> bytes:
        """截取屏幕

        Args:
            save_path: 截图保存路径（可选），不传则仅返回字节数据

        Returns:
            截图的 PNG 原始字节数据
        """
        self._ensure_connected()
        # screencap -p 输出 PNG 格式字节流
        png_bytes = self._device.shell("screencap -p", decode=False)

        if save_path:
            save_dir = os.path.dirname(save_path)
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(png_bytes)
            logger.debug(f"截图已保存到 {save_path} ({len(png_bytes)} bytes)")

        return png_bytes

    def _ensure_connected(self):
        """确保设备已连接，否则抛出异常"""
        if self._device is None:
            raise ConnectionError("设备未连接，请先调用 connect()")

    # ---- 人类行为模拟 ----

    def tap_human_like(
        self,
        x: int,
        y: int,
        jitter: int = 5,
        delay_min: float = 0.3,
        delay_max: float = 0.7,
    ):
        """模拟人类点击：随机偏移 + 随机延时

        Args:
            x: 目标 X 坐标
            y: 目标 Y 坐标
            jitter: 偏移范围（±jitter 像素），默认 5
            delay_min: 最小延时（秒），默认 0.3
            delay_max: 最大延时（秒），默认 0.7
        """
        # 随机偏移
        offset_x = random.randint(-jitter, jitter)
        offset_y = random.randint(-jitter, jitter)
        actual_x = x + offset_x
        actual_y = y + offset_y

        # 随机延时
        delay = random.uniform(delay_min, delay_max)
        time.sleep(delay)

        # 执行点击
        self.tap(actual_x, actual_y)
        logger.debug(f"人类点击: ({x},{y}) → ({actual_x},{actual_y}), 延时={delay:.2f}s")

    def find_and_tap(
        self,
        template_path: str,
        threshold: float = 0.8,
        jitter: int = 5,
        delay_min: float = 0.3,
        delay_max: float = 0.7,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> bool:
        """截图 → 模板匹配 → 找到则人类点击

        Args:
            template_path: 模板图片路径
            threshold: 匹配阈值
            jitter: 点击偏移范围
            delay_min/max: 点击延时范围
            region: 搜索区域 (x, y, w, h)，None 表示全图

        Returns:
            是否成功找到并点击
        """
        from game_platform.ocr.recognizer import Recognizer

        recognizer = Recognizer()
        
        logger.debug(f"正在截图...")
        screenshot_bytes = self.screenshot()
        logger.debug(f"截图完成，大小: {len(screenshot_bytes)} bytes")

        location = recognizer.find_template(
            screenshot_bytes, template_path, threshold, region=region
        )
        if location:
            x, y, w, h = location
            center_x = x + w // 2
            center_y = y + h // 2

            # 【调试模式】保存带标记的截图用于验证
            import cv2
            import numpy as np
            try:
                # 解码截图为图像
                arr = np.frombuffer(screenshot_bytes, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None:
                    # 绘制矩形框（绿色）
                    cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 3)
                    # 绘制中心点（红色圆点）
                    cv2.circle(img, (center_x, center_y), 10, (0, 0, 255), -1)
                    # 添加文字标注
                    text = f"Click: ({center_x},{center_y})"
                    cv2.putText(img, text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
                    # 保存标注后的截图到临时目录
                    import tempfile
                    debug_path = os.path.join(tempfile.gettempdir(), 'game_scripts_debug_click.png')
                    cv2.imwrite(debug_path, img)
            except Exception as e:
                logger.warning(f"保存标注截图失败: {e}")
            
            self.tap_human_like(center_x, center_y, jitter, delay_min, delay_max)
            return True
        else:
            return False

    def find_and_tap_region(
        self,
        template_path: str,
        region_ratio: str = "bottom_third",
        threshold: float = 0.8,
        jitter: int = 5,
        delay_min: float = 0.3,
        delay_max: float = 0.7,
    ) -> bool:
        """截图 → 裁剪指定区域 → 模板匹配 → 找到则人类点击

        通过只搜索屏幕的一部分来大幅提升匹配速度。

        Args:
            template_path: 模板图片路径
            region_ratio: 区域预设，支持:
                - "bottom_third": 底部 1/3
                - "top_third": 顶部 1/3
                - "center": 中间 1/3
            threshold: 匹配阈值
            jitter: 点击偏移范围
            delay_min/max: 点击延时范围

        Returns:
            是否成功找到并点击
        """
        import numpy as np
        from game_platform.ocr.recognizer import Recognizer

        recognizer = Recognizer()
        screenshot_bytes = self.screenshot()
        screen_img = recognizer._load_image(screenshot_bytes)
        h, w = screen_img.shape[:2]

        # 根据预设计算裁剪区域
        if region_ratio == "bottom_third":
            ry, rh = h * 2 // 3, h // 3
            rx, rw = 0, w
        elif region_ratio == "top_third":
            ry, rh = 0, h // 3
            rx, rw = 0, w
        elif region_ratio == "center":
            ry, rh = h // 3, h // 3
            rx, rw = 0, w
        else:
            raise ValueError(f"不支持的区域预设: {region_ratio}")

        # 裁剪后重新编码为 PNG bytes
        cropped = screen_img[ry : ry + rh, rx : rx + rw]
        _, encoded = cv2.imencode(".png", cropped)
        cropped_bytes = encoded.tobytes()

        location = recognizer.find_template(
            cropped_bytes, template_path, threshold,
            region=(rx, ry, rw, rh),
        )
        if location:
            x, y, tw, th = location
            center_x = x + tw // 2
            center_y = y + th // 2
            self.tap_human_like(center_x, center_y, jitter, delay_min, delay_max)
            return True
        else:
            logger.debug(f"区域 {region_ratio} 未找到模板: {template_path}")
            return False

    # ---- OCR 文字识别便捷方法 ----

    def ocr_text(self, region: tuple = None) -> str:
        """截图并识别文字（一步完成）

        Args:
            region: 识别区域 (x1, y1, x2, y2)，None 表示全图

        Returns:
            识别出的文字内容
        """
        from game_platform.ocr.recognizer import Recognizer

        screenshot_bytes = self.screenshot()
        recognizer = Recognizer()
        return recognizer.recognize_text(screenshot_bytes, region)

    def ocr_all(self, region: tuple = None):
        """截图并识别所有文字，返回详细结果列表

        Args:
            region: 识别区域 (x1, y1, x2, y2)，None 表示全图

        Returns:
            OCRResult 列表
        """
        from game_platform.ocr.recognizer import Recognizer

        screenshot_bytes = self.screenshot()
        recognizer = Recognizer()
        return recognizer.recognize_all(screenshot_bytes, region)

    def find_text_and_tap(
        self,
        target_text: str,
        partial: bool = False,
        jitter: int = 5,
        delay_min: float = 0.3,
        delay_max: float = 0.7,
        region: tuple = None,
    ) -> bool:
        """截图 -> OCR 查找文字 -> 找到则点击文字中心

        Args:
            target_text: 要查找并点击的文字
            partial: True=包含匹配，False=精确匹配
            jitter: 点击偏移范围（像素）
            delay_min: 点击前最小延时（秒）
            delay_max: 点击前最大延时（秒）
            region: 识别区域 (x1, y1, x2, y2)，None 表示全图

        Returns:
            是否成功找到并点击

        用法示例:
            # 点击"开始战斗"按钮
            device.find_text_and_tap("开始战斗")

            # 在底部区域查找并点击"确认"
            device.find_text_and_tap("确认", region=(0, 600, 1280, 720))
        """
        from game_platform.ocr.recognizer import Recognizer

        screenshot_bytes = self.screenshot()
        recognizer = Recognizer()
        result = recognizer.find_text(screenshot_bytes, target_text, region, partial)

        if result:
            cx, cy = result.center
            logger.info(f"OCR 找到 '{target_text}' @ ({cx},{cy}), conf={result.confidence:.2f}")
            self.tap_human_like(cx, cy, jitter, delay_min, delay_max)
            return True
        else:
            logger.debug(f"OCR 未找到文字: '{target_text}'")
            return False

    def text_on_screen(
        self,
        target_text: str,
        partial: bool = False,
        region: tuple = None,
    ) -> bool:
        """截图并检查屏幕上是否存在指定文字

        Args:
            target_text: 要查找的文字
            partial: True=包含匹配，False=精确匹配
            region: 识别区域 (x1, y1, x2, y2)，None 表示全图

        Returns:
            是否存在

        用法示例:
            # 检查是否弹出了对话框
            if device.text_on_screen("确认退出"):
                device.tap(300, 500)
        """
        from game_platform.ocr.recognizer import Recognizer

        screenshot_bytes = self.screenshot()
        recognizer = Recognizer()
        return recognizer.text_exists(screenshot_bytes, target_text, region, partial)

    def read_number_on_screen(self, region: tuple, pattern: str = r'\d+') -> Optional[int]:
        """截图并从指定区域读取数字

        Args:
            region: 识别区域 (x1, y1, x2, y2)，必填
            pattern: 正则表达式，默认匹配第一个整数

        Returns:
            识别到的整数，未找到返回 None
        """
        from game_platform.ocr.recognizer import Recognizer

        screenshot_bytes = self.screenshot()
        recognizer = Recognizer()
        return recognizer.read_number(screenshot_bytes, region, pattern)
