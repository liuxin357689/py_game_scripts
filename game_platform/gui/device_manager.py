"""
设备管理模块（增强版）

职责:
    - DeviceManager: 管理多设备连接、活跃设备切换、黑名单和验证缓存
    - DeviceManagerDialog: 设备管理对话框 UI（扫描、连接/断开、选择活跃设备、验证流程）

此模块为通用组件，各项目直接复用
"""

import logging
from typing import Dict, Optional, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QAbstractItemView, QGroupBox, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QObject
from PyQt6.QtGui import QColor, QFont

from game_platform.adb.device import ADBDevice
from game_platform.adb.scanner import scan_emulators, EmulatorInfo
from game_platform.gui.device_config import get_config_manager, DeviceConfigManager
from game_platform.gui.verification_dialog import VerificationDialog
from game_platform.gui.batch_verification_dialog import BatchVerificationDialog
from game_platform.gui.settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)


# ============================================================
# DeviceManager - 设备连接管理服务（非 UI）
# ============================================================

class DeviceManager(QObject):
    """设备连接管理器，管理多设备连接、活跃设备切换、黑名单和验证缓存

    信号:
        device_connected(str): 设备连接成功，参数为设备地址
        device_disconnected(str): 设备断开，参数为设备地址
        active_device_changed(str): 活跃设备变更，参数为新设备地址
        device_blacklisted(str): 设备被加入黑名单，参数为设备地址
    """

    device_connected = pyqtSignal(str)
    device_disconnected = pyqtSignal(str)
    active_device_changed = pyqtSignal(str)
    device_blacklisted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 配置管理器
        self._config: DeviceConfigManager = get_config_manager()
        # 已连接的设备: address -> ADBDevice
        self._devices: Dict[str, ADBDevice] = {}
        # 设备信息缓存: address -> EmulatorInfo
        self._device_infos: Dict[str, EmulatorInfo] = {}
        # 当前活跃设备地址
        self._active_address: Optional[str] = None

    @property
    def config(self) -> DeviceConfigManager:
        """配置管理器"""
        return self._config

    @property
    def devices(self) -> Dict[str, ADBDevice]:
        """所有已连接的设备"""
        return dict(self._devices)

    @property
    def active_device(self) -> Optional[ADBDevice]:
        """当前活跃设备"""
        if self._active_address and self._active_address in self._devices:
            return self._devices[self._active_address]
        return None

    @property
    def active_address(self) -> Optional[str]:
        """当前活跃设备地址"""
        return self._active_address

    def scan(self, adb_host: str = "localhost", adb_port: int = 5037,
             include_blacklisted: bool = True) -> List[EmulatorInfo]:
        """扫描本地模拟器

        Args:
            adb_host: ADB Server 地址
            adb_port: ADB Server 端口
            include_blacklisted: 是否包含黑名单设备（默认 True，UI 需要显示）

        Returns:
            发现的模拟器列表
        """
        results = scan_emulators(host=adb_host, adb_server_port=adb_port)

        # 缓存设备信息
        for info in results:
            self._device_infos[info.address] = info

        if include_blacklisted:
            return results

        # 过滤黑名单
        return [info for info in results if not self._config.is_blacklisted(info.address)]

    def connect_device(self, host: str, port: int) -> Optional[ADBDevice]:
        """连接到指定设备（不触发验证流程）

        Args:
            host: 设备 IP
            port: 设备 ADB 端口

        Returns:
            连接成功返回 ADBDevice，失败返回 None
        """
        address = f"{host}:{port}"

        # 已连接则直接返回
        if address in self._devices:
            device = self._devices[address]
            if device.is_connected():
                logger.info(f"设备 {address} 已连接")
                return device

        # 创建新连接
        device = ADBDevice(host, port)
        if device.connect():
            self._devices[address] = device
            if address not in self._device_infos:
                self._device_infos[address] = EmulatorInfo(host=host, port=port, status="online")
            logger.info(f"设备 {address} 连接成功")

            # 如果是第一个连接的设备，自动设为活跃设备
            if self._active_address is None:
                self.set_active(address)

            # 更新最后连接时间
            self._config.update_last_connected(address)

            self.device_connected.emit(address)
            return device
        else:
            logger.error(f"设备 {address} 连接失败")
            return None

    def connect_and_verify(self, host: str, port: int, parent_widget=None) -> Optional[ADBDevice]:
        """连接设备并执行验证流程

        流程:
            1. 检查黑名单 → 拒绝连接
            2. 检查已验证 → 直接连接（跳过验证）
            3. 首次连接 → 连接 → 打开设置 → 弹出验证对话框
            4. 用户确认 → 标记为已验证
            5. 用户拒绝 → 加入黑名单 → 断开连接

        Args:
            host: 设备 IP
            port: 设备 ADB 端口
            parent_widget: 父窗口（用于显示对话框）

        Returns:
            连接成功返回 ADBDevice，失败返回 None
        """
        address = f"{host}:{port}"

        # 1. 检查黑名单
        if self._config.is_blacklisted(address):
            QMessageBox.warning(
                parent_widget, "设备在黑名单中",
                f"设备 {address} 已在黑名单中，无法连接。\n"
                f"请先在设置中将其从黑名单移除。"
            )
            return None

        # 2. 检查已验证 → 直接连接
        if self._config.is_verified(address):
            logger.info(f"设备 {address} 已验证，直接连接")
            return self.connect_device(host, port)

        # 3. 首次连接 → 需要验证
        device = self.connect_device(host, port)
        if device is None:
            return None

        # 获取设备信息
        info = self._device_infos.get(address)

        # 尝试打开设置界面
        settings_opened, fallback_msg = self._try_open_settings(device)

        # 4. 弹出验证对话框
        dialog = VerificationDialog(
            address=address,
            device_info=info or EmulatorInfo(host=host, port=port, status="online"),
            settings_opened=settings_opened,
            fallback_message=fallback_msg,
            parent=parent_widget
        )

        result = dialog.exec()

        if result == QDialog.DialogCode.Accepted:
            # 用户确认连接正确 → 标记为已验证
            name = info.name if info else address
            model = info.model if info else ""
            brand = info.brand if info else ""
            self._config.mark_as_verified(address, name, model, brand)
            logger.info(f"设备 {address} 验证通过")
            return device
        else:
            # 用户确认连接错误 → 加入黑名单 → 断开
            self._config.add_to_blacklist(address)
            self.disconnect_device(address)
            self.device_blacklisted.emit(address)
            logger.info(f"设备 {address} 已加入黑名单")
            return None

    def _try_open_settings(self, device: ADBDevice) -> tuple:
        """尝试在设备上打开设置界面

        Args:
            device: ADBDevice 实例

        Returns:
            (是否成功, 失败原因)
        """
        try:
            device._device.shell("am start -a android.settings.SETTINGS")
            logger.info("已在设备上打开设置界面")
            return True, ""
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"打开设置界面失败: {error_msg}")
            return False, error_msg

    def disconnect_device(self, address: str):
        """断开指定设备

        Args:
            address: 设备地址（host:port）
        """
        if address not in self._devices:
            return

        device = self._devices[address]
        device.disconnect()
        del self._devices[address]

        logger.info(f"设备 {address} 已断开")
        self.device_disconnected.emit(address)

        # 如果断开的是活跃设备，切换到其他设备
        if self._active_address == address:
            if self._devices:
                new_active = next(iter(self._devices))
                self.set_active(new_active)
            else:
                self._active_address = None
                self.active_device_changed.emit("")

    def disconnect_all(self):
        """断开所有设备"""
        addresses = list(self._devices.keys())
        for address in addresses:
            self.disconnect_device(address)

    def set_active(self, address: str):
        """设置活跃设备

        Args:
            address: 设备地址
        """
        if address not in self._devices:
            logger.warning(f"设备 {address} 未连接，无法设为活跃设备")
            return

        old_active = self._active_address
        self._active_address = address

        if old_active != address:
            logger.info(f"活跃设备切换: {old_active} → {address}")
            self.active_device_changed.emit(address)

    def get_device(self, address: str) -> Optional[ADBDevice]:
        """获取指定地址的设备"""
        return self._devices.get(address)

    def get_device_info(self, address: str) -> Optional[EmulatorInfo]:
        """获取设备信息"""
        return self._device_infos.get(address)

    def get_all_addresses(self) -> List[str]:
        """获取所有已连接设备的地址列表"""
        return list(self._devices.keys())

    def get_all_scanned_addresses(self) -> List[str]:
        """获取所有已扫描到的设备地址（含未连接）"""
        return list(self._device_infos.keys())

    def is_device_verified(self, address: str) -> bool:
        """检查设备是否已验证"""
        return self._config.is_verified(address)

    def is_device_blacklisted(self, address: str) -> bool:
        """检查设备是否在黑名单中"""
        return self._config.is_blacklisted(address)

    def remove_from_blacklist(self, address: str):
        """从黑名单移除设备"""
        self._config.remove_from_blacklist(address)

    def auto_connect_last_device(self) -> Optional[ADBDevice]:
        """自动连接上次使用的设备

        从持久化配置中找到最后连接的已验证设备，尝试自动连接。
        连接失败不会阻塞，仅记录日志。

        Returns:
            连接成功返回 ADBDevice，无可用设备或连接失败返回 None
        """
        verified = self._config.get_all_verified()
        if not verified:
            logger.info("无已验证设备，跳过自动连接")
            return None

        # 按 last_connected 降序排列，找到最近连接的设备
        candidates = sorted(
            verified.items(),
            key=lambda x: x[1].last_connected or x[1].last_verified,
            reverse=True
        )

        for address, info in candidates:
            # 跳过黑名单设备
            if self._config.is_blacklisted(address):
                continue

            parts = address.rsplit(":", 1)
            if len(parts) != 2:
                continue

            host, port = parts[0], int(parts[1])
            logger.info(f"尝试自动连接上次设备: {info.name} [{address}]")

            device = self.connect_device(host, port)
            if device:
                self.set_active(address)
                logger.info(f"自动连接成功: {info.name} [{address}]")
                return device
            else:
                logger.warning(f"自动连接失败: {info.name} [{address}]，尝试下一个")
                continue

        logger.info("所有已验证设备均无法连接")
        return None


# ============================================================
# _ScanWorker - 后台扫描线程
# ============================================================

class _ScanWorker(QThread):
    """后台扫描线程，避免阻塞 UI"""

    def __init__(self, device_manager: DeviceManager, adb_host: str, adb_port: int, parent=None):
        super().__init__(parent)
        self._device_manager = device_manager
        self._adb_host = adb_host
        self._adb_port = adb_port
        self._results: List[EmulatorInfo] = []

    @property
    def results(self) -> List[EmulatorInfo]:
        return self._results

    def run(self):
        self._results = self._device_manager.scan(self._adb_host, self._adb_port)


# ============================================================
# DeviceManagerDialog - 设备管理对话框
# ============================================================

class DeviceManagerDialog(QDialog):
    """设备管理对话框

    功能:
        - 扫描本地所有模拟器（含黑名单设备标记）
        - 连接/断开设备（首次连接触发验证流程）
        - 选择活跃设备（用于任务执行）
        - 显示设备状态、型号信息和验证状态
    """

    # 表格列定义
    COL_STATUS = 0
    COL_NAME = 1
    COL_MODEL = 2
    COL_RESOLUTION = 3
    COL_TYPE = 4

    def __init__(self, device_manager: DeviceManager, parent=None):
        """初始化设备管理对话框

        Args:
            device_manager: DeviceManager 实例
            parent: 父窗口
        """
        super().__init__(parent)
        self._dm = device_manager
        self._scan_worker = None
        self._last_scan_results: List[EmulatorInfo] = []
        self._batch_dialog = None
        self._settings_dialog = None

        self.setWindowTitle("设备管理")
        self.setMinimumSize(700, 450)
        self.setModal(False)  # 非模态，允许同时操作主窗口

        self._init_ui()
        self._connect_signals()

        # 初始化时自动扫描一次
        self._do_scan()

    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)

        # ---- 设备列表 ----
        device_group = QGroupBox("设备列表")
        group_layout = QVBoxLayout()

        # 表格
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["状态", "设备名称", "型号/品牌", "分辨率", "类型"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)

        # 列宽设置
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(self.COL_STATUS, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_MODEL, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_RESOLUTION, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_TYPE, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(self.COL_STATUS, 80)
        self._table.setColumnWidth(self.COL_RESOLUTION, 110)
        self._table.setColumnWidth(self.COL_TYPE, 80)

        group_layout.addWidget(self._table)

        # ---- 按钮区 ----
        btn_layout = QHBoxLayout()

        self._scan_btn = QPushButton("扫描设备")
        self._scan_btn.setToolTip("扫描本地所有安卓模拟器")
        btn_layout.addWidget(self._scan_btn)

        self._connect_btn = QPushButton("连接")
        self._connect_btn.setToolTip("连接选中的设备（首次连接会验证）")
        self._connect_btn.setEnabled(False)
        btn_layout.addWidget(self._connect_btn)

        self._disconnect_btn = QPushButton("断开")
        self._disconnect_btn.setToolTip("断开选中的设备")
        self._disconnect_btn.setEnabled(False)
        btn_layout.addWidget(self._disconnect_btn)

        self._activate_btn = QPushButton("设为活跃")
        self._activate_btn.setToolTip("将选中设备设为活跃设备（任务将在此设备上运行）")
        self._activate_btn.setEnabled(False)
        btn_layout.addWidget(self._activate_btn)

        self._batch_verify_btn = QPushButton("批量验证")
        self._batch_verify_btn.setToolTip("对所有未验证设备逐个验证")
        btn_layout.addWidget(self._batch_verify_btn)

        self._settings_btn = QPushButton("设置")
        self._settings_btn.setToolTip("管理黑名单、验证记录和连接设置")
        btn_layout.addWidget(self._settings_btn)

        btn_layout.addStretch()

        group_layout.addLayout(btn_layout)
        device_group.setLayout(group_layout)
        layout.addWidget(device_group)

        # ---- 状态栏 ----
        self._status_label = QLabel("就绪")
        layout.addWidget(self._status_label)

    def _connect_signals(self):
        """绑定信号"""
        self._scan_btn.clicked.connect(self._do_scan)
        self._connect_btn.clicked.connect(self._do_connect)
        self._disconnect_btn.clicked.connect(self._do_disconnect)
        self._activate_btn.clicked.connect(self._do_activate)
        self._batch_verify_btn.clicked.connect(self._do_batch_verify)
        self._settings_btn.clicked.connect(self._do_open_settings)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        # DeviceManager 信号
        self._dm.device_connected.connect(self._on_device_connected)
        self._dm.device_disconnected.connect(self._on_device_disconnected)
        self._dm.active_device_changed.connect(self._on_active_changed)
        self._dm.device_blacklisted.connect(self._on_device_blacklisted)

    # ---- 操作处理 ----

    def _do_scan(self):
        """执行扫描"""
        self._scan_btn.setEnabled(False)
        self._status_label.setText("正在扫描...")
        self._table.setRowCount(0)

        self._scan_worker = _ScanWorker(self._dm, "localhost", 5037, self)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.start()

    def _on_scan_finished(self):
        """扫描完成回调"""
        self._scan_btn.setEnabled(True)
        results = self._scan_worker.results
        self._scan_worker = None
        self._last_scan_results = results

        self._refresh_table(results)
        self._status_label.setText(f"扫描完成，发现 {len(results)} 个设备")

    def _do_connect(self):
        """连接选中设备（含验证流程）"""
        row = self._table.currentRow()
        if row < 0:
            return

        # 从隐藏数据中获取真实地址
        name_item = self._table.item(row, self.COL_NAME)
        if not name_item:
            return

        address = name_item.data(Qt.ItemDataRole.UserRole)
        if not address:
            return

        # 检查黑名单
        if self._dm.is_device_blacklisted(address):
            reply = QMessageBox.question(
                self, "设备在黑名单中",
                f"设备 {address} 在黑名单中。\n是否将其移出黑名单并连接？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._dm.remove_from_blacklist(address)
            else:
                return

        parts = address.rsplit(":", 1)
        if len(parts) != 2:
            return

        host, port = parts[0], int(parts[1])
        self._status_label.setText(f"正在连接 {address}...")
        QApplication.processEvents()

        # 使用 connect_and_verify 执行完整验证流程
        device = self._dm.connect_and_verify(host, port, parent_widget=self)
        if device:
            self._status_label.setText(f"已连接 {address}")
        else:
            if not self._dm.is_device_blacklisted(address):
                self._status_label.setText(f"连接失败: {address}")
            else:
                self._status_label.setText(f"设备 {address} 已加入黑名单")

    def _do_disconnect(self):
        """断开选中设备"""
        row = self._table.currentRow()
        if row < 0:
            return

        name_item = self._table.item(row, self.COL_NAME)
        if not name_item:
            return

        address = name_item.data(Qt.ItemDataRole.UserRole)
        if not address:
            return

        self._dm.disconnect_device(address)
        self._status_label.setText(f"已断开 {address}")

    def _do_activate(self):
        """设为活跃设备"""
        row = self._table.currentRow()
        if row < 0:
            return

        name_item = self._table.item(row, self.COL_NAME)
        if not name_item:
            return

        address = name_item.data(Qt.ItemDataRole.UserRole)
        if not address:
            return

        self._dm.set_active(address)

    def _do_batch_verify(self):
        """批量验证未验证设备"""
        # 收集未验证的设备
        unverified = []
        for info in self._last_scan_results:
            if not self._dm.is_device_blacklisted(info.address) and not self._dm.is_device_verified(info.address):
                unverified.append(info)

        if not unverified:
            QMessageBox.information(
                self, "无需验证",
                "所有扫描到的设备都已验证或在黑名单中。"
            )
            return

        self._batch_dialog = BatchVerificationDialog(
            self._dm, unverified, parent=self
        )
        self._batch_dialog.exec()
        self._batch_dialog = None

        # 刷新表格
        self._refresh_table_from_manager()

    def _do_open_settings(self):
        """打开设置对话框"""
        self._settings_dialog = SettingsDialog(parent=self)
        self._settings_dialog.exec()
        self._settings_dialog = None

        # 设置可能改变了黑名单/验证记录，刷新表格
        self._refresh_table_from_manager()

    def _on_selection_changed(self):
        """表格选中行变更"""
        row = self._table.currentRow()
        if row < 0:
            self._connect_btn.setEnabled(False)
            self._disconnect_btn.setEnabled(False)
            self._activate_btn.setEnabled(False)
            return

        name_item = self._table.item(row, self.COL_NAME)
        if not name_item:
            return

        address = name_item.data(Qt.ItemDataRole.UserRole)
        if not address:
            return

        is_blacklisted = self._dm.is_device_blacklisted(address)
        is_connected = address in self._dm.devices
        is_active = address == self._dm.active_address

        self._connect_btn.setEnabled(not is_connected or is_blacklisted)
        self._disconnect_btn.setEnabled(is_connected)
        self._activate_btn.setEnabled(is_connected and not is_active)

    # ---- DeviceManager 信号处理 ----

    def _on_device_connected(self, address: str):
        """设备连接成功"""
        self._refresh_table_from_manager()

    def _on_device_disconnected(self, address: str):
        """设备断开"""
        self._refresh_table_from_manager()

    def _on_active_changed(self, address: str):
        """活跃设备变更"""
        self._refresh_table_from_manager()

    def _on_device_blacklisted(self, address: str):
        """设备被加入黑名单"""
        self._refresh_table_from_manager()

    # ---- 表格刷新 ----

    def _refresh_table(self, scan_results: List[EmulatorInfo]):
        """用扫描结果刷新表格"""
        connected_addresses = set(self._dm.get_all_addresses())
        active = self._dm.active_address
        config = self._dm.config

        self._table.setRowCount(len(scan_results))

        for i, info in enumerate(scan_results):
            address = info.address
            is_connected = address in connected_addresses
            is_active = address == active
            is_blacklisted = config.is_blacklisted(address)
            is_verified = config.is_verified(address)

            # 状态列
            if is_blacklisted:
                status_text = "黑名单"
                status_color = QColor("#f5c6cb")  # 浅红色
            elif is_active:
                status_text = "活跃"
                status_color = QColor("#d4edda")  # 浅绿色
            elif is_connected:
                status_text = "已连接"
                status_color = QColor("#d4edda")
            elif info.status == "online":
                status_text = "在线"
                status_color = None
            else:
                status_text = "未连接"
                status_color = None

            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if status_color:
                status_item.setBackground(status_color)
            self._table.setItem(i, self.COL_STATUS, status_item)

            # 设备名称列（用户友好的名称 + 验证标记）
            device_name = info.name if info.name else info.address
            if is_verified:
                device_name += " [已验证]"
            name_item = QTableWidgetItem(device_name)
            name_item.setData(Qt.ItemDataRole.UserRole, address)  # 隐藏存储真实地址
            if is_blacklisted:
                name_item.setForeground(QColor("#999999"))
                name_item.setFont(QFont("", -1, QFont.Weight.Normal, True))  # 斜体
            self._table.setItem(i, self.COL_NAME, name_item)

            # 型号/品牌列
            model_brand = f"{info.model}"
            if info.brand and info.brand.lower() not in ["unknown", ""]:
                model_brand += f" / {info.brand}"
            if info.android_version:
                model_brand += f" (Android {info.android_version})"
            model_item = QTableWidgetItem(model_brand)
            if is_blacklisted:
                model_item.setForeground(QColor("#999999"))
            self._table.setItem(i, self.COL_MODEL, model_item)

            # 分辨率列
            resolution = info.resolution or "—"
            res_item = QTableWidgetItem(resolution)
            res_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i, self.COL_RESOLUTION, res_item)

            # 类型列
            type_text = "模拟器" if info.is_emulator else "真机"
            type_item = QTableWidgetItem(type_text)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i, self.COL_TYPE, type_item)

            # 高亮活跃设备整行
            if is_active:
                for col in range(self._table.columnCount()):
                    item = self._table.item(i, col)
                    if item:
                        item.setBackground(QColor("#d4edda"))
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)

    def _refresh_table_from_manager(self):
        """从 DeviceManager 当前状态刷新表格（合并已扫描 + 已连接）"""
        if self._last_scan_results:
            # 使用上次扫描结果
            self._refresh_table(self._last_scan_results)
        else:
            # 没有扫描结果时，从已缓存信息构建
            all_addresses = set(self._dm.get_all_scanned_addresses())
            all_addresses.update(self._dm.get_all_addresses())

            infos = []
            for addr in sorted(all_addresses):
                info = self._dm.get_device_info(addr)
                if info:
                    infos.append(info)
                else:
                    parts = addr.rsplit(":", 1)
                    if len(parts) == 2:
                        infos.append(EmulatorInfo(host=parts[0], port=int(parts[1]), status="online"))

            self._refresh_table(infos)
