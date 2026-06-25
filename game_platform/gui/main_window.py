"""
主窗口基类

职责:
    - 应用程序主窗口框架
    - 菜单栏、工具栏、状态栏
    - 各功能面板的容器和切换
    - 窗口事件处理（关闭、最小化到托盘等）

各项目通过继承 MainWindow 来定制自己的主窗口
"""


from PyQt6.QtWidgets import QMainWindow, QApplication, QLabel, QVBoxLayout, QWidget, QMessageBox, QMenu
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QAction
import sys
import logging

from game_platform.gui.device_manager import DeviceManager, DeviceManagerDialog
from game_platform.gui.settings_dialog import SettingsDialog
from game_platform.gui.multi_device_task_panel import MultiDeviceTaskPanel

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """应用程序主窗口基类

    基于 PyQt6 QMainWindow 构建，管理所有子面板。
    各项目应继承此类并定制。
    """

    # 设备名称变更信号（用于跨线程安全更新 UI）
    device_name_changed = pyqtSignal(str)  # str 为设备名称，空字符串表示清除

    def __init__(self, app_name: str = "Game Script", app_version: str = "0.1.0"):
        """初始化主窗口

        Args:
            app_name: 应用名称（显示在标题栏）
            app_version: 应用版本
        """
        super().__init__()
        self.app_name = app_name
        self.app_version = app_version
        self._device_name = None  # 当前连接的设备名称
        
        # 设备管理器（全局单例，管理多设备连接）
        self._device_manager = DeviceManager(self)
        self._device_manager_dialog = None  # 延迟创建
        self._settings_dialog = None  # 延迟创建
        self._screenshot_dialog = None  # 截图工具对话框
        self._multi_device_panel = None  # 多设备任务面板
        
        # 设置窗口属性
        self._update_title()
        self.resize(800, 600)
        
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.layout = QVBoxLayout(central_widget)
        
        # 添加欢迎标签
        welcome_label = QLabel(f"欢迎使用 {app_name}")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        self.layout.addWidget(welcome_label)
        
        # 添加状态标签
        self.status_label = QLabel("就绪 - 请连接设备后开始")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.status_label)
        
        # 创建菜单栏
        self._create_menu_bar()
        
        # 创建工具栏
        self._create_toolbar()
        
        # 创建状态栏
        self._create_status_bar()
        
        # 连接设备名称变更信号到槽函数
        self.device_name_changed.connect(self._on_device_name_changed)
        
        # 监听 DeviceManager 活跃设备变更，自动更新标题栏
        self._device_manager.active_device_changed.connect(self._on_dm_active_changed)
        
        # 初始化子面板
        self._init_panels()
        
        # 延迟自动连接上次设备（等 UI 完全就绪）
        QTimer.singleShot(500, self._auto_connect_last_device)

    def _create_menu_bar(self):
        """创建菜单栏"""
        menu_bar = self.menuBar()
        
        # 文件菜单
        file_menu = menu_bar.addMenu("文件(&F)")
        file_menu.addAction("退出", self.close)
        
        # 工具菜单
        tools_menu = menu_bar.addMenu("工具(&T)")
        tools_menu.addAction("设备管理", self._open_device_manager)
        tools_menu.addAction("设备设置", self._open_device_settings)
        
        # 最近设备子菜单
        self._recent_menu = QMenu("最近设备", tools_menu)
        self._recent_menu.aboutToShow.connect(self._refresh_recent_devices)
        tools_menu.addMenu(self._recent_menu)
        
        tools_menu.addAction("任务配置")
        
        tools_menu.addSeparator()
        # 截图工具仅开发环境可见（打包后不显示）
        if not getattr(sys, 'frozen', False):
            tools_menu.addAction("截图工具 (F5)", self._open_screenshot_tool)
        
        # 帮助菜单
        help_menu = menu_bar.addMenu("帮助(&H)")
        help_menu.addAction("关于")

    def _create_toolbar(self):
        """创建工具栏"""
        toolbar = self.addToolBar("主工具栏")
        toolbar.addAction("启动")
        toolbar.addAction("停止")
        toolbar.addAction("暂停")

    def _create_status_bar(self):
        """创建状态栏"""
        self.statusBar().showMessage("准备就绪")

    def set_device_name(self, device_name: str):
        """设置当前连接的设备名称并更新标题栏（线程安全）

        Args:
            device_name: 设备名称（如 localhost:5555 或设备序列号）
        """
        # 发射信号，由主线程处理 UI 更新
        self.device_name_changed.emit(device_name)

    def _on_device_name_changed(self, device_name: str):
        """处理设备名称变更（在主线程中执行）

        Args:
            device_name: 设备名称，空字符串表示清除
        """
        if device_name:
            self._device_name = device_name
        else:
            self._device_name = None
        self._update_title()

    def _update_title(self):
        """更新窗口标题（不再显示设备信息）"""
        title = f"{self.app_name} v{self.app_version}"
        self.setWindowTitle(title)

    def clear_device_name(self):
        """清除设备名称（断开连接时调用，线程安全）"""
        # 发射空字符串信号，由主线程处理 UI 更新
        self.device_name_changed.emit("")

    @property
    def device_manager(self) -> DeviceManager:
        """获取全局设备管理器"""
        return self._device_manager

    def _open_device_manager(self):
        """打开设备管理对话框"""
        if self._device_manager_dialog is None:
            self._device_manager_dialog = DeviceManagerDialog(
                self._device_manager, parent=self
            )
        self._device_manager_dialog.show()
        self._device_manager_dialog.raise_()
        self._device_manager_dialog.activateWindow()

    def _open_device_settings(self):
        """打开设备设置对话框"""
        self._settings_dialog = SettingsDialog(parent=self)
        self._settings_dialog.exec()
        self._settings_dialog = None

    def _open_screenshot_tool(self):
        """打开截图工具对话框
        
        获取当前活跃设备，若未连接则提示用户先连接设备。
        """
        device = self._device_manager.active_device
        if not device or not device.is_connected():
            QMessageBox.warning(
                self, "未连接设备",
                "请先在【工具 → 设备管理】中连接设备，再使用截图工具。"
            )
            return

        from game_platform.screenshot.dialog import ScreenshotDialog

        if self._screenshot_dialog is None:
            self._screenshot_dialog = ScreenshotDialog(
                device=device,
                parent=self,
            )
        self._screenshot_dialog.show()
        self._screenshot_dialog.raise_()
        self._screenshot_dialog.activateWindow()

    def _refresh_recent_devices(self):
        """刷新最近设备子菜单"""
        self._recent_menu.clear()
        config = self._device_manager.config
        verified = config.get_all_verified()

        if not verified:
            no_action = self._recent_menu.addAction("（无已验证设备）")
            no_action.setEnabled(False)
            return

        # 按最后连接时间排序
        sorted_devices = sorted(
            verified.items(),
            key=lambda x: x[1].last_connected or x[1].last_verified,
            reverse=True
        )

        for addr, info in sorted_devices:
            display = f"{info.name}  [{addr}]"
            action = QAction(display, self._recent_menu)
            action.setData(addr)
            action.triggered.connect(lambda checked, a=addr: self._quick_connect(a))
            self._recent_menu.addAction(action)

    def _quick_connect(self, address: str):
        """快速连接已验证设备"""
        parts = address.rsplit(":", 1)
        if len(parts) != 2:
            return

        host, port = parts[0], int(parts[1])
        device = self._device_manager.connect_device(host, port)
        if device:
            self._device_manager.set_active(address)
            self.statusBar().showMessage(f"已连接 {address}", 3000)
        else:
            self.statusBar().showMessage(f"连接失败: {address}", 3000)
            QMessageBox.warning(
                self, "连接失败",
                f"无法快速连接到 {address}\n请打开设备管理重新扫描。"
            )

    def _auto_connect_last_device(self):
        """自动连接上次使用的设备"""
        device = self._device_manager.auto_connect_last_device()
        if device:
            info = self._device_manager.get_device_info(self._device_manager.active_address)
            name = info.name if info else self._device_manager.active_address
            self.statusBar().showMessage(f"已自动连接: {name}", 5000)
        else:
            logger.debug("无可用设备自动连接")

    def _on_dm_active_changed(self, address: str):
        """DeviceManager 活跃设备变更回调，更新标题栏

        Args:
            address: 新活跃设备地址，空字符串表示清除
        """
        if address:
            self.set_device_name(address)
        else:
            self.clear_device_name()

    def _init_panels(self):
        """初始化各功能面板（由子类重写以定制）"""
        # 基类提供默认实现：添加多设备任务控制面板
        from PyQt6.QtWidgets import QScrollArea
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self._multi_device_panel = MultiDeviceTaskPanel(
            device_manager=self._device_manager,
            parent=scroll
        )
        scroll.setWidget(self._multi_device_panel)
        
        self.layout.addWidget(scroll)
        
        # 监听设备连接/断开事件，自动刷新面板
        self._device_manager.device_connected.connect(self._on_device_list_changed)
        self._device_manager.device_disconnected.connect(self._on_device_list_changed)

    def _on_device_list_changed(self, address: str):
        """设备列表变更回调，刷新多设备任务面板"""
        if self._multi_device_panel:
            self._multi_device_panel.refresh_device_list()

    def closeEvent(self, event):
        """窗口关闭事件处理

        Args:
            event: 关闭事件
        """
        # 确认退出
        reply = QMessageBox.question(
            self,
            "确认退出",
            f"确定要退出 {self.app_name} 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()
