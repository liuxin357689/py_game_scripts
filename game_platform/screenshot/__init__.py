"""
截图管理模块

提供 ADB 设备截图、裁剪、保存等功能：
    - ScreenshotManager: 截图管理核心类
    - 支持全图截图和区域裁剪
    - 自动时间戳命名
    - 可配置默认保存路径
"""

from .manager import ScreenshotManager

__all__ = ["ScreenshotManager"]
