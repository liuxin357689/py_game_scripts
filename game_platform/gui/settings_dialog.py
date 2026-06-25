"""
设备管理设置对话框

职责:
    - 管理黑名单（查看、移除）
    - 管理已验证设备缓存（查看、清除）
    - 修改设备管理相关设置
    - 导入/导出配置
"""

import logging
from typing import Set

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTabWidget, QWidget, QListWidget, QListWidgetItem,
    QCheckBox, QGroupBox, QFormLayout, QMessageBox,
    QFileDialog, QAbstractItemView
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from game_platform.gui.device_config import get_config_manager, DeviceConfigManager

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """设备管理设置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config: DeviceConfigManager = get_config_manager()

        self.setWindowTitle("设备管理 - 设置")
        self.setMinimumSize(550, 450)
        self.setModal(True)

        self._init_ui()
        self._load_data()

    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)

        # 选项卡
        self._tabs = QTabWidget()

        # ---- Tab 1: 黑名单管理 ----
        blacklist_tab = QWidget()
        bl_layout = QVBoxLayout(blacklist_tab)

        bl_desc = QLabel("黑名单中的设备在扫描时会被忽略，连接时也会被拒绝。")
        bl_desc.setWordWrap(True)
        bl_desc.setStyleSheet("color: #666; margin-bottom: 8px;")
        bl_layout.addWidget(bl_desc)

        self._blacklist_widget = QListWidget()
        self._blacklist_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        bl_layout.addWidget(self._blacklist_widget)

        bl_btn_layout = QHBoxLayout()
        self._remove_bl_btn = QPushButton("移除选中")
        self._remove_bl_btn.clicked.connect(self._on_remove_blacklist)
        bl_btn_layout.addWidget(self._remove_bl_btn)

        self._clear_bl_btn = QPushButton("清空黑名单")
        self._clear_bl_btn.setStyleSheet("color: #d9534f;")
        self._clear_bl_btn.clicked.connect(self._on_clear_blacklist)
        bl_btn_layout.addWidget(self._clear_bl_btn)

        bl_btn_layout.addStretch()
        bl_layout.addLayout(bl_btn_layout)

        self._tabs.addTab(blacklist_tab, "黑名单管理")

        # ---- Tab 2: 已验证设备 ----
        verified_tab = QWidget()
        v_layout = QVBoxLayout(verified_tab)

        v_desc = QLabel("已验证的设备在下次连接时将直接连接，不再弹出验证对话框。")
        v_desc.setWordWrap(True)
        v_desc.setStyleSheet("color: #666; margin-bottom: 8px;")
        v_layout.addWidget(v_desc)

        self._verified_widget = QListWidget()
        self._verified_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        v_layout.addWidget(self._verified_widget)

        v_btn_layout = QHBoxLayout()
        self._remove_v_btn = QPushButton("移除选中")
        self._remove_v_btn.clicked.connect(self._on_remove_verified)
        v_btn_layout.addWidget(self._remove_v_btn)

        self._clear_v_btn = QPushButton("清空所有验证记录")
        self._clear_v_btn.setStyleSheet("color: #d9534f;")
        self._clear_v_btn.clicked.connect(self._on_clear_verified)
        v_btn_layout.addWidget(self._clear_v_btn)

        v_btn_layout.addStretch()
        v_layout.addLayout(v_btn_layout)

        self._tabs.addTab(verified_tab, "已验证设备")

        # ---- Tab 3: 连接设置 ----
        settings_tab = QWidget()
        s_layout = QVBoxLayout(settings_tab)

        # 验证设置组
        verify_group = QGroupBox("连接验证")
        verify_layout = QFormLayout(verify_group)

        self._enable_verify_cb = QCheckBox("启用连接验证")
        self._enable_verify_cb.setToolTip("首次连接设备时弹出验证对话框")
        verify_layout.addRow(self._enable_verify_cb)

        self._auto_settings_cb = QCheckBox("自动打开设置界面")
        self._auto_settings_cb.setToolTip("连接时自动在设备上打开设置界面以帮助识别")
        verify_layout.addRow(self._auto_settings_cb)

        self._show_tips_cb = QCheckBox("显示验证提示")
        self._show_tips_cb.setToolTip("在验证对话框中显示详细提示信息")
        verify_layout.addRow(self._show_tips_cb)

        s_layout.addWidget(verify_group)
        s_layout.addStretch()

        self._tabs.addTab(settings_tab, "连接设置")

        # ---- Tab 4: 配置导入导出 ----
        io_tab = QWidget()
        io_layout = QVBoxLayout(io_tab)

        io_desc = QLabel("可以导出或导入设备配置（包含黑名单和验证记录）。")
        io_desc.setWordWrap(True)
        io_desc.setStyleSheet("color: #666; margin-bottom: 8px;")
        io_layout.addWidget(io_desc)

        # 配置路径
        path_group = QGroupBox("配置文件")
        path_layout = QVBoxLayout(path_group)
        self._path_label = QLabel(f"路径: {self._config.get_config_path()}")
        self._path_label.setWordWrap(True)
        self._path_label.setStyleSheet("color: #666; font-family: monospace;")
        path_layout.addWidget(self._path_label)
        io_layout.addWidget(path_group)

        io_btn_layout = QHBoxLayout()
        self._export_btn = QPushButton("导出配置")
        self._export_btn.clicked.connect(self._on_export)
        io_btn_layout.addWidget(self._export_btn)

        self._import_btn = QPushButton("导入配置")
        self._import_btn.clicked.connect(self._on_import)
        io_btn_layout.addWidget(self._import_btn)

        io_btn_layout.addStretch()
        io_layout.addLayout(io_btn_layout)
        io_layout.addStretch()

        self._tabs.addTab(io_tab, "导入/导出")

        layout.addWidget(self._tabs)

        # ---- 底部按钮 ----
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        save_btn = QPushButton("保存设置")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #0069d9; }
        """)
        save_btn.clicked.connect(self._on_save)
        bottom_layout.addWidget(save_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        bottom_layout.addWidget(close_btn)

        layout.addLayout(bottom_layout)

    def _load_data(self):
        """加载数据到 UI"""
        # 黑名单
        self._blacklist_widget.clear()
        for addr in sorted(self._config.get_blacklist()):
            item = QListWidgetItem(addr)
            self._blacklist_widget.addItem(item)

        # 已验证设备
        self._verified_widget.clear()
        for addr, info in sorted(self._config.get_all_verified().items()):
            display = f"{info.name}  [{addr}]  (验证{info.verification_count}次)"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, addr)
            self._verified_widget.addItem(item)

        # 设置
        settings = self._config.settings
        self._enable_verify_cb.setChecked(settings.enable_verification)
        self._auto_settings_cb.setChecked(settings.auto_open_settings)
        self._show_tips_cb.setChecked(settings.show_verification_tips)

    # ---- 黑名单操作 ----

    def _on_remove_blacklist(self):
        """从黑名单移除选中项"""
        selected = self._blacklist_widget.selectedItems()
        if not selected:
            return

        for item in selected:
            addr = item.text()
            self._config.remove_from_blacklist(addr)
            logger.info(f"从黑名单移除: {addr}")

        self._load_data()

    def _on_clear_blacklist(self):
        """清空黑名单"""
        if not self._config.get_blacklist():
            return

        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空黑名单吗？所有被屏蔽的设备将重新出现在扫描结果中。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._config.clear_blacklist()
            self._load_data()

    # ---- 已验证设备操作 ----

    def _on_remove_verified(self):
        """移除选中的已验证设备"""
        selected = self._verified_widget.selectedItems()
        if not selected:
            return

        for item in selected:
            addr = item.data(Qt.ItemDataRole.UserRole)
            self._config.remove_verified(addr)

        self._load_data()

    def _on_clear_verified(self):
        """清空所有验证记录"""
        if not self._config.get_all_verified():
            return

        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空所有验证记录吗？下次连接设备时将重新弹出验证对话框。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._config.clear_verified_cache()
            self._load_data()

    # ---- 设置保存 ----

    def _on_save(self):
        """保存设置"""
        self._config.update_settings(
            enable_verification=self._enable_verify_cb.isChecked(),
            auto_open_settings=self._auto_settings_cb.isChecked(),
            show_verification_tips=self._show_tips_cb.isChecked(),
        )
        QMessageBox.information(self, "保存成功", "设置已保存")

    # ---- 导入导出 ----

    def _on_export(self):
        """导出配置"""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出配置", "device_config.json",
            "JSON 文件 (*.json)"
        )
        if path:
            try:
                self._config.export_config(path)
                QMessageBox.information(self, "导出成功", f"配置已导出到:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "导出失败", f"导出配置失败: {e}")

    def _on_import(self):
        """导入配置"""
        path, _ = QFileDialog.getOpenFileName(
            self, "导入配置", "",
            "JSON 文件 (*.json)"
        )
        if path:
            reply = QMessageBox.question(
                self, "确认导入",
                "导入配置将覆盖当前的黑名单和验证记录。\n确定要继续吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    self._config.import_config(path)
                    self._load_data()
                    QMessageBox.information(self, "导入成功", "配置已导入")
                except Exception as e:
                    QMessageBox.critical(self, "导入失败", f"导入配置失败: {e}")
