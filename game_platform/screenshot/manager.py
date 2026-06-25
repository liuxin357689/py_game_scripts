"""
截图管理器核心类

职责:
    - 通过 ADB 获取设备截图（原始 PNG 字节流）
    - 解码为 OpenCV 图像 / PIL Image
    - 支持区域裁剪
    - 保存到用户主目录下的 screenshot 文件夹
    - 时间戳命名，避免覆盖
"""

import io
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def _get_app_data_dir() -> str:
    """获取应用数据目录（兼容开发环境和打包环境）

    打包后 exe: exe 所在目录/screenshot
    开发环境:   ~/.game_scripts/screenshot
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包环境：exe 所在目录
        return os.path.join(os.path.dirname(sys.executable), "screenshot")
    else:
        # 开发环境：用户主目录
        return os.path.join(str(Path.home()), ".game_scripts", "screenshot")


# 默认保存目录
DEFAULT_SAVE_DIR = _get_app_data_dir()


class ScreenshotManager:
    """截图管理器：负责从 ADB 设备截图、裁剪、保存"""

    def __init__(self, device, save_dir: str = None):
        """
        Args:
            device: ADBDevice 实例（已连接）
            save_dir: 截图保存目录，None 时使用默认路径
        """
        self._device = device
        self._save_dir = save_dir or DEFAULT_SAVE_DIR
        self._last_raw: Optional[bytes] = None
        self._last_image: Optional[np.ndarray] = None

    @property
    def save_dir(self) -> str:
        """当前保存目录"""
        return self._save_dir

    @save_dir.setter
    def save_dir(self, path: str):
        self._save_dir = path

    @property
    def last_image(self) -> Optional[np.ndarray]:
        """最近一次截图的 OpenCV 图像（BGR 格式）"""
        return self._last_image

    # ---- 截图 ----

    def capture(self) -> np.ndarray:
        """从设备截取全屏画面

        Returns:
            OpenCV BGR 格式的图像 (numpy array)

        Raises:
            ConnectionError: 设备未连接
            RuntimeError: 截图解码失败
        """
        raw = self._device.screenshot()
        self._last_raw = raw

        arr = np.frombuffer(raw, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("截图解码失败，设备返回的数据可能不完整")

        self._last_image = img
        h, w = img.shape[:2]
        logger.info(f"截图成功: {w}x{h}, {len(raw)} bytes")
        return img

    def capture_region(
        self, x1: int, y1: int, x2: int, y2: int
    ) -> np.ndarray:
        """截图并裁剪指定区域

        Args:
            x1: 左上角 X
            y1: 左上角 Y
            x2: 右下角 X
            y2: 右下角 Y

        Returns:
            裁剪后的 OpenCV BGR 图像

        Raises:
            ValueError: 区域坐标越界
        """
        img = self.capture()
        return self.crop(img, x1, y1, x2, y2)

    # ---- 裁剪 ----

    @staticmethod
    def crop(
        image: np.ndarray, x1: int, y1: int, x2: int, y2: int
    ) -> np.ndarray:
        """从已有图像中裁剪指定区域

        Args:
            image: OpenCV BGR 图像
            x1: 左上角 X
            y1: 左上角 Y
            x2: 右下角 X
            y2: 右下角 Y

        Returns:
            裁剪后的图像副本

        Raises:
            ValueError: 区域坐标越界或无效
        """
        h, w = image.shape[:2]

        # 规范化坐标
        left = max(0, min(x1, x2))
        right = min(w, max(x1, x2))
        top = max(0, min(y1, y2))
        bottom = min(h, max(y1, y2))

        if right <= left or bottom <= top:
            raise ValueError(
                f"无效的裁剪区域: ({x1},{y1})-({x2},{y2}), "
                f"图像尺寸 {w}x{h}"
            )

        cropped = image[top:bottom, left:right].copy()
        logger.debug(
            f"裁剪: ({left},{top})-({right},{bottom}), "
            f"结果 {right-left}x{bottom-top}"
        )
        return cropped

    # ---- 保存 ----

    def save(
        self,
        image: np.ndarray = None,
        filename: str = None,
        region: Tuple[int, int, int, int] = None,
    ) -> str:
        """保存截图到文件

        Args:
            image: 要保存的图像，None 时使用最近一次截图
            filename: 文件名（不含路径），None 则自动生成时间戳文件名
            region: 可选的裁剪区域 (x1, y1, x2, y2)，保存前先裁剪

        Returns:
            保存的文件完整路径
        """
        if image is None:
            image = self._last_image
        if image is None:
            raise ValueError("没有可保存的图像，请先调用 capture()")

        # 裁剪
        if region:
            image = self.crop(image, *region)

        # 确保目录存在
        os.makedirs(self._save_dir, exist_ok=True)

        # 生成文件名
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
            filename = f"screen_{timestamp}.png"

        filepath = os.path.join(self._save_dir, filename)

        # 写入
        success, buf = cv2.imencode(".png", image)
        if not success:
            raise RuntimeError("PNG 编码失败")

        with open(filepath, "wb") as f:
            f.write(buf.tobytes())

        h, w = image.shape[:2]
        size_kb = os.path.getsize(filepath) / 1024
        logger.info(f"截图已保存: {filepath}  ({w}x{h}, {size_kb:.1f} KB)")
        return filepath

    def save_full(self, filename: str = None) -> str:
        """截取全屏并保存

        Args:
            filename: 文件名，None 则自动生成

        Returns:
            文件路径
        """
        img = self.capture()
        return self.save(img, filename)

    def save_region(
        self,
        x1: int, y1: int, x2: int, y2: int,
        filename: str = None,
    ) -> str:
        """截取全屏、裁剪指定区域并保存

        Args:
            x1, y1, x2, y2: 裁剪区域
            filename: 文件名，None 则自动生成

        Returns:
            文件路径
        """
        img = self.capture()
        cropped = self.crop(img, x1, y1, x2, y2)
        return self.save(cropped, filename)

    # ---- 便捷方法 ----

    def to_pil(self, image: np.ndarray = None) -> Image.Image:
        """将 OpenCV 图像转为 PIL Image（用于 GUI 显示）

        Args:
            image: OpenCV BGR 图像，None 时使用最近截图

        Returns:
            PIL.Image 对象（RGB 格式）
        """
        if image is None:
            image = self._last_image
        if image is None:
            raise ValueError("没有可用图像，请先调用 capture()")

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)

    def to_bytes(self, image: np.ndarray = None) -> bytes:
        """将 OpenCV 图像编码为 PNG 字节流

        Args:
            image: OpenCV BGR 图像，None 时使用最近截图

        Returns:
            PNG 格式字节数据
        """
        if image is None:
            image = self._last_image
        if image is None:
            raise ValueError("没有可用图像，请先调用 capture()")

        success, buf = cv2.imencode(".png", image)
        if not success:
            raise RuntimeError("PNG 编码失败")
        return buf.tobytes()

    def list_saved(self) -> list[str]:
        """列出保存目录中所有截图文件

        Returns:
            文件路径列表，按修改时间倒序
        """
        if not os.path.exists(self._save_dir):
            return []

        files = []
        for f in os.listdir(self._save_dir):
            if f.lower().endswith((".png", ".jpg", ".jpeg")):
                full = os.path.join(self._save_dir, f)
                files.append(full)

        files.sort(key=os.path.getmtime, reverse=True)
        return files
