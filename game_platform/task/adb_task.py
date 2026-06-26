"""
ADB 设备任务基类

在 BaseTask 基础上封装 ADB 设备的通用管理逻辑：
    - 设备解析（优先 DeviceManager，回退直连）
    - 无条件重连（含 DeviceManager 缓存绕过）
    - 生命周期自动释放设备连接

各项目的 ADB 任务应继承此类代替 BaseTask
"""

import logging

from game_platform.task.base_task import BaseTask

logger = logging.getLogger(__name__)


class ADBTask(BaseTask):
    """ADB 设备任务基类，封装设备连接、重连、释放的通用逻辑"""

    def __init__(
        self,
        name: str = "ADBTask",
        device_manager=None,
        device_address: str = None,
    ):
        """
        Args:
            name: 任务名称
            device_manager: DeviceManager 实例（可选）
            device_address: 设备地址，如 "localhost:5555"
        """
        super().__init__(name=name)
        self._device_manager = device_manager
        self._device_address = device_address
        self._device = None
        self._owns_device = False

    # ---- 设备管理 ----

    def _resolve_device(self):
        """解析 ADB 设备连接（优先 DeviceManager，回退 host:port 直连）"""
        if self._device_manager and self._device_address:
            device = self._device_manager.get_device(self._device_address)
            if device and device.is_connected():
                self._device = device
                self._owns_device = False
                logger.info(
                    f"[{self._name}] 通过 DeviceManager 获取设备: "
                    f"{self._device_address}"
                )
                return

        from game_platform.adb.device import ADBDevice
        parts = (self._device_address or "localhost:5555").rsplit(":", 1)
        host = parts[0]
        port = int(parts[1]) if len(parts) == 2 else 5555
        self._device = ADBDevice(host, port)
        if not self._device.connect():
            raise ConnectionError(f"无法连接设备 {host}:{port}")
        self._owns_device = True
        logger.info(f"[{self._name}] 直接连接设备: {host}:{port}")

    def _try_reconnect(self):
        """尝试重连设备（无条件重连，不依赖 is_connected 状态）

        - 自有设备: 断开后重连同一实例
        - DeviceManager 设备: 关闭旧连接，创建新的独立连接绕过缓存
        """
        self.sleep(5)
        try:
            logger.info(f"[{self._name}] 尝试重连设备...")
            if self._owns_device:
                try:
                    self._device.disconnect()
                except Exception:
                    pass
                self._device.connect()
            else:
                # 关闭旧连接
                old_device = self._device
                try:
                    if old_device:
                        old_device.disconnect()
                except Exception:
                    pass
                # 创建独立连接，绕过 DeviceManager 缓存
                from game_platform.adb.device import ADBDevice
                parts = (
                    self._device_address or "localhost:5555"
                ).rsplit(":", 1)
                host = parts[0]
                port = int(parts[1]) if len(parts) == 2 else 5555
                new_device = ADBDevice(host, port)
                if new_device.connect():
                    self._device = new_device
                    self._owns_device = True
                    logger.info(
                        f"[{self._name}] 通过独立连接重连成功: "
                        f"{host}:{port}"
                    )
                else:
                    raise ConnectionError(
                        f"独立连接失败: {host}:{port}"
                    )
            logger.info(f"[{self._name}] 重连成功")
        except Exception as e:
            logger.warning(f"[{self._name}] 重连失败: {e}")

    # ---- 生命周期 ----

    def teardown(self):
        """释放设备连接（子类可覆写以添加额外清理，需调用 super().teardown()）"""
        if self._owns_device and self._device:
            self._device.disconnect()
