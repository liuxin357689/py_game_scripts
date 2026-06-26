"""
ADB 设备控制模块

提供与 Android 设备的交互接口：
    - 设备连接与断开
    - 屏幕截图
    - 触摸、滑动操作
    - 按键事件
"""

from .device import ADBDevice

__all__ = ["ADBDevice"]
