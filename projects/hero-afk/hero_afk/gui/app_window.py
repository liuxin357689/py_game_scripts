"""
Hero AFK 主窗口

继承平台 MainWindow 基类，定制英雄挂机游戏的专属界面：
    - 添加英雄挂机特有的菜单项
    - 注册英雄挂机专属的任务面板
    - 定制窗口标题和图标

继承: platform.platform.gui.main_window.MainWindow
"""

import sys

from hero_afk._paths import setup_platform_path
setup_platform_path()

from PyQt6.QtWidgets import QSplitter, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt
from game_platform.gui.main_window import MainWindow
from game_platform.gui.control_panel import ControlPanel
from game_platform.gui.log_viewer import MultiDeviceLogViewer
from game_platform.task.screenshot_service import ScreenshotService
from game_platform.task.base_task import TaskStatus

from game_platform.adb.scanner import EmulatorInfo
from hero_afk.tasks import (
    AutoReplaceEquipment, AutoCloseNotify,
    AutoChaosRanch, AutoDarkRealm,
    AutoActivityReward,
)
from hero_afk.gui.test_mode_dialog import TestModeDialog
import logging

logger = logging.getLogger(__name__)


class FrameTaskManagerAdapter:
    """FrameTask 管理器适配器 — 桥接截图共享架构与 ControlPanel

    管理多个 ScreenshotService 实例（每设备一个），
    对外提供与 MultiDeviceTaskManager 相同的接口供 ControlPanel 调用。
    """

    def __init__(self):
        # address -> ScreenshotService
        self._services: dict[str, ScreenshotService] = {}
        # task_name -> factory() -> FrameTask
        self._task_factories: dict = {}
        # task_name -> 期望的激活状态（跨设备重连时保持用户选择）
        self._desired_active: dict[str, bool] = {}

    # ---- 任务工厂注册 ----

    def register_task_factory(self, name: str, factory):
        """注册任务工厂

        Args:
            name: 任务名称（显示在控制面板中）
            factory: 无参可调用对象，返回 FrameTask 实例
        """
        self._task_factories[name] = factory
        self._desired_active[name] = False
        logger.info(f"已注册任务工厂: {name}")

    # ---- 设备管理 ----

    def register_device(self, address: str):
        """为设备创建 ScreenshotService，注册并激活所有任务"""
        if address in self._services:
            logger.warning(f"设备 {address} 已有截图服务，跳过")
            return

        service = ScreenshotService(device_address=address)

        for task_name, factory in self._task_factories.items():
            task = factory()
            service.register_task(task)
            if self._desired_active.get(task_name, False):
                task.activate()

        service.start()
        self._services[address] = service
        logger.info(
            f"为设备 {address} 创建截图服务，"
            f"共 {len(self._task_factories)} 个任务"
        )

    def unregister_device(self, address: str):
        """停止并移除设备的 ScreenshotService"""
        service = self._services.pop(address, None)
        if service:
            service.stop()
            logger.info(f"已停止设备 {address} 的截图服务")

    # ---- ControlPanel 兼容接口 ----

    def list_tasks(self) -> list[str]:
        """列出所有已注册的任务名称"""
        return list(self._task_factories.keys())

    def get_task_status(self, task_name: str):
        """获取任务在所有设备上的聚合状态"""
        if task_name not in self._task_factories:
            return None

        if not self._services:
            if self._desired_active.get(task_name, False):
                return TaskStatus.RUNNING
            return TaskStatus.IDLE

        states = []
        for service in self._services.values():
            task = service.get_task(task_name)
            if task:
                states.append(
                    TaskStatus.RUNNING if task.is_active else TaskStatus.IDLE
                )

        if not states:
            return (
                TaskStatus.RUNNING
                if self._desired_active.get(task_name, False)
                else TaskStatus.IDLE
            )
        if any(s == TaskStatus.RUNNING for s in states):
            return TaskStatus.RUNNING
        return TaskStatus.IDLE

    def start_task(self, task_name: str) -> bool:
        """激活任务（所有设备）"""
        if task_name not in self._task_factories:
            return False
        self._desired_active[task_name] = True
        for service in self._services.values():
            service.activate_task(task_name)
        logger.info(f"已激活任务: {task_name}")
        return True

    def stop_task(self, task_name: str) -> bool:
        """停用任务（所有设备）"""
        if task_name not in self._task_factories:
            return False
        self._desired_active[task_name] = False
        for service in self._services.values():
            service.deactivate_task(task_name)
        logger.info(f"已停用任务: {task_name}")
        return True

    def pause_task(self, task_name: str) -> bool:
        """暂停任务（等价于停用，FrameTask 无独立暂停态）"""
        return self.stop_task(task_name)

    def resume_task(self, task_name: str) -> bool:
        """恢复任务（等价于激活，FrameTask 无独立暂停态）"""
        return self.start_task(task_name)

    def stop_all(self):
        """停止所有设备的所有服务和任务"""
        for name in self._desired_active:
            self._desired_active[name] = False
        for service in self._services.values():
            service.stop()
        self._services.clear()
        logger.info("已停止所有截图服务")


class HeroAfkWindow(MainWindow):
    """英雄挂机游戏主窗口"""

    def __init__(self):
        """初始化 Hero AFK 主窗口"""
        # 任务管理器适配器（截图共享架构）
        self._task_manager = FrameTaskManagerAdapter()

        # 初始化 UI 组件引用
        self._control_panel = None
        self._log_viewer = None  # MultiDeviceLogViewer
        self._test_mode_dialog = None  # 测试模式对话框

        # 调用父类初始化（会调用 _init_panels，创建 self._device_manager）
        super().__init__(app_name="Hero AFK", app_version="0.1.0")

        # 设置日志（必须在注册任务之前，否则日志不会显示在 GUI 中）
        self._setup_logging()

        # 注册任务工厂
        self._register_tasks()

        # 监听设备选项卡关闭事件
        if self._log_viewer:
            self._log_viewer.device_tab_closed.connect(self._on_device_tab_closed)

        # 延迟自动连接所有已验证设备（等 UI 就绪后执行）
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(800, self._auto_connect_verified_devices)

        # 刷新控制面板任务列表
        if self._control_panel:
            self._control_panel.refresh()

        # 验证模式：设置环境变量 AUTO_CLOSE_SECONDS 后程序自动退出
        import os
        auto_close = os.environ.get("AUTO_CLOSE_SECONDS")
        if auto_close:
            from PyQt6.QtCore import QTimer
            delay_ms = int(auto_close) * 1000
            QTimer.singleShot(delay_ms, self._auto_close_for_verify)
            logger.info(f"[验证模式] {auto_close} 秒后自动退出")

    def _auto_close_for_verify(self):
        """验证模式自动退出：执行清理后直接退出进程，跳过确认对话框"""
        logger.info("[验证模式] 正在自动退出...")
        if self._task_manager:
            self._task_manager.stop_all()
        import sys
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        sys.exit(0)

    def _auto_connect_last_device(self):
        """覆盖父类的单设备自动连接，改为多设备连接（在 __init__ 中用 QTimer 调用）"""
        pass  # 由 _auto_connect_verified_devices 替代

    def _init_panels(self):
        """初始化 Hero AFK 专属面板"""
        # 创建分割器（上下布局）
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 上面：控制面板
        self._control_panel = ControlPanel(task_manager=self._task_manager)
        splitter.addWidget(self._control_panel)

        # 下面：多设备日志查看器
        self._log_viewer = MultiDeviceLogViewer()
        splitter.addWidget(self._log_viewer)

        # 设置分割比例
        splitter.setStretchFactor(0, 1)  # 控制面板占 1 份
        splitter.setStretchFactor(1, 2)  # 日志查看器占 2 份

        # 替换欢迎标签为分割器
        # 移除原来的 welcome_label 和 status_label
        while self.layout.count() > 0:
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 添加分割器
        self.layout.addWidget(splitter)

        logger.info("界面初始化完成")

    def _register_tasks(self):
        """注册任务工厂（设备连接时自动创建实例并注册到 ScreenshotService）"""

        # ---- 任务 1: 自动完成任务（优先级最高 — 关闭弹窗通知）----
        self._task_manager.register_task_factory(
            "自动完成任务",
            lambda: AutoCloseNotify(pixel_tolerance=40),
        )

        # ---- 任务 2: 暗能秘境（星星计数+模板匹配+像素点）----
        self._task_manager.register_task_factory(
            "暗能秘境",
            lambda: AutoDarkRealm(
                threshold=0.7,
                star_threshold=0.70,
                pixel_tolerance=40,
            ),
        )

        # ---- 任务 3: 自动替换装备（模板匹配）----
        self._task_manager.register_task_factory(
            "自动替换装备",
            lambda: AutoReplaceEquipment(threshold=0.7),
        )

        # ---- 任务 4: 混沌牧场（模板匹配+坐标像素点）----
        self._task_manager.register_task_factory(
            "混沌牧场",
            lambda: AutoChaosRanch(
                threshold=0.7,
            ),
        )

        # ---- 任务 5: 自动领取活动奖励（模板匹配+角标检测）----
        self._task_manager.register_task_factory(
            "自动领取活动奖励",
            lambda: AutoActivityReward(threshold=0.7),
        )

        # 监听设备连接事件，为新连接的设备创建截图服务
        self._device_manager.device_connected.connect(self._on_device_connected)

    def _create_toolbar(self):
        """创建工具栏"""
        toolbar = self.addToolBar("主工具栏")
        toolbar.addAction("启动")
        toolbar.addAction("停止")
        toolbar.addAction("暂停")
        toolbar.addSeparator()
        test_action = toolbar.addAction("测试模式")
        test_action.triggered.connect(self._open_test_mode)

    def _open_test_mode(self):
        """打开测试模式对话框"""
        if self._test_mode_dialog is None:
            self._test_mode_dialog = TestModeDialog(
                task_manager=self._task_manager,
                device_manager=self._device_manager,
                parent=self,
            )
            self._test_mode_dialog.closed.connect(self._on_test_mode_closed)
        self._test_mode_dialog.show()
        self._test_mode_dialog.raise_()
        self._test_mode_dialog.activateWindow()

    def _on_test_mode_closed(self):
        """测试模式对话框关闭回调"""
        self._test_mode_dialog = None

    def _setup_logging(self):
        """设置日志系统"""
        if self._log_viewer:
            # 监听根 logger，捕获所有日志（全局选项卡）
            self._log_viewer.setup_logger_for_device("global", "全局", level=logging.DEBUG)
            logger.info("日志系统已启动")

    def _auto_connect_verified_devices(self):
        """启动时自动连接所有已验证设备（多设备同时在线）

        流程:
            1. 从 DeviceConfigManager 读取已验证设备列表
            2. 逐个尝试 ADB 连接
            3. 连接成功：为该设备创建截图服务，设备状态保持为"已连接"
            4. 连接失败：在全局日志中打印错误信息，跳过该设备继续连接下一个
            5. 所有成功连接的设备均保持活跃状态，ADB 可同时控制多台模拟器
        """
        if not self._device_manager or not self._log_viewer:
            return

        config = self._device_manager.config
        verified = config.get_all_verified()

        if not verified:
            logger.info("无已验证设备，跳过自动连接")
            self._log_global_info("[系统] 无已验证设备，请先在【工具 → 设备管理】中扫描并验证设备")
            return

        logger.info(f"发现 {len(verified)} 个已验证设备，开始自动连接...")
        self._log_global_info(f"[系统] 发现 {len(verified)} 个已验证设备，开始自动连接...")

        success_count = 0
        fail_count = 0
        connected_addresses = []

        for address, info in verified.items():
            try:
                # 解析 host:port
                parts = address.rsplit(":", 1)
                if len(parts) != 2:
                    logger.warning(f"无效的设备地址格式: {address}")
                    continue

                host, port = parts[0], int(parts[1])
                device_name = info.name if info and info.name else address

                # 预填充设备信息到 DeviceManager，确保 connect_device 不会创建空的 EmulatorInfo
                if address not in self._device_manager._device_infos:
                    self._device_manager._device_infos[address] = EmulatorInfo(
                        host=host, port=port, status="online", name=device_name
                    )

                # 尝试连接
                logger.info(f"正在连接 {device_name} [{address}]...")
                device = self._device_manager.connect_device(host, port)

                if device and device.is_connected():
                    success_count += 1
                    connected_addresses.append(address)
                    # 显式为设备创建日志选项卡 + 截图服务
                    self._on_device_connected(address)
                    logger.info(f"✅ 成功连接 {device_name} [{address}]")
                else:
                    fail_count += 1
                    error_msg = f"[系统] 无法连接到 {device_name} [{address}] - 设备未响应或 ADB 服务异常"
                    self._log_global_error(error_msg)
                    logger.warning(error_msg)

            except Exception as e:
                fail_count += 1
                device_name = info.name if info else address
                error_msg = f"[系统] 连接 {device_name} [{address}] 时发生异常: {str(e)}"
                self._log_global_error(error_msg)
                logger.error(error_msg, exc_info=True)

        # 汇总结果
        if success_count > 0:
            summary = f"[系统] 自动连接完成: {success_count} 成功, {fail_count} 失败"
            logger.info(summary)
            self._log_global_info(summary)
            # 列出所有已连接设备
            for addr in connected_addresses:
                dev_info = self._device_manager.get_device_info(addr)
                dev_name = dev_info.name if dev_info else addr
                self._log_global_info(f"  ✅ {dev_name} [{addr}]")
        elif fail_count > 0:
            error_msg = f"[系统] 自动连接失败: 所有 {fail_count} 个已验证设备均无法连接"
            logger.warning(error_msg)
            self._log_global_error(error_msg)

    def _log_global_info(self, message: str):
        """在全局日志选项卡中打印信息

        Args:
            message: 信息内容
        """
        if self._log_viewer and "global" in self._log_viewer._device_tabs:
            from datetime import datetime
            timestamp = datetime.now().strftime('%H:%M:%S')
            html_msg = f'<span style="color: #4ec9b0;">{timestamp} | INFO    | {message}</span><br>'
            global_log = self._log_viewer._device_tabs["global"]
            global_log.insertHtml(html_msg)
            cursor = global_log.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            global_log.setTextCursor(cursor)

    def _log_global_error(self, message: str):
        """在全局日志选项卡中打印错误信息

        Args:
            message: 错误消息
        """
        if self._log_viewer and "global" in self._log_viewer._device_tabs:
            from datetime import datetime
            timestamp = datetime.now().strftime('%H:%M:%S')
            html_msg = f'<span style="color: #f44747;">{timestamp} | ERROR   | {message}</span><br>'
            global_log = self._log_viewer._device_tabs["global"]
            global_log.insertHtml(html_msg)
            # 滚动到底部
            cursor = global_log.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            global_log.setTextCursor(cursor)

    def _on_device_connected(self, address: str):
        """设备连接回调

        流程:
            1. 为设备创建日志选项卡
            2. 为设备创建 ScreenshotService 并注册所有任务
            3. 刷新控制面板
        """
        if not self._log_viewer:
            return

        # 获取设备信息（优先从 DeviceManager 获取，其次从配置文件获取）
        info = self._device_manager.get_device_info(address)
        device_name = ""
        if info and info.name:
            device_name = info.name
        else:
            # 从配置中获取已验证设备的名称
            verified_info = self._device_manager.config.get_verified_info(address)
            if verified_info and verified_info.name:
                device_name = verified_info.name
        if not device_name:
            device_name = address

        # 为设备创建日志选项卡
        self._log_viewer.setup_logger_for_device(address, device_name, level=logging.DEBUG)

        # 为设备创建截图服务（内部会注册并启动所有任务）
        self._task_manager.register_device(address)

        # 刷新控制面板显示新注册的任务
        if self._control_panel:
            self._control_panel.refresh()

        logger.info(f"已为设备 {device_name} [{address}] 创建日志选项卡和截图服务")

    def _on_device_tab_closed(self, address: str):
        """设备选项卡关闭回调

        流程:
            1. 停止对应设备的截图服务
            2. 断开 ADB 连接
            3. 在全局日志中记录断开信息
            4. 若所有设备已断开，确保所有服务已停止
        """
        # 停止截图服务 + 断开设备连接
        if self._device_manager:
            # 先停止截图服务（内部会 stop 所有任务 + 断开 ScreenshotService 的 ADB 连接）
            self._task_manager.unregister_device(address)
            # 断开 DeviceManager 的 ADB 连接
            self._device_manager.disconnect_device(address)
            self._log_global_info(f"[系统] 已断开设备连接: {address}")
            logger.info(f"选项卡关闭，已停止截图服务并断开设备: {address}")

        # 检查是否还有设备选项卡（排除全局选项卡）
        if self._log_viewer:
            remaining = [addr for addr in self._log_viewer._device_tabs if addr != "global"]
            if not remaining:
                # 最后一个设备选项卡已关闭，确保所有服务已停止
                self._task_manager.stop_all()
                self._log_global_info("[系统] 所有设备已断开，截图服务已停止")
                logger.info("最后一个设备选项卡已关闭，所有截图服务已停止")

    def closeEvent(self, event):
        """窗口关闭事件处理"""
        # 停止所有截图服务
        if self._task_manager:
            self._task_manager.stop_all()

        # 调用父类关闭事件
        super().closeEvent(event)
