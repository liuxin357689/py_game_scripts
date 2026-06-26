"""
设备验证对话框

职责:
    - 在首次连接设备时显示验证对话框
    - 引导用户确认设备是否正确
    - 支持降级模式（当 am start 失败时）
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

import logging

logger = logging.getLogger(__name__)


class VerificationDialog(QDialog):
    """设备验证对话框
    
    用于首次连接设备时让用户确认设备是否正确
    """
    
    def __init__(self, address: str, device_info, settings_opened: bool = True, 
                 fallback_message: str = "", parent=None):
        """初始化验证对话框
        
        Args:
            address: 设备地址（host:port）
            device_info: EmulatorInfo 对象，包含设备详细信息
            settings_opened: 设置界面是否成功打开
            fallback_message: 降级模式的错误信息
            parent: 父窗口
        """
        super().__init__(parent)
        self._address = address
        self._device_info = device_info
        self._settings_opened = settings_opened
        self._fallback_message = fallback_message
        
        self.setWindowTitle("⚠️ 请确认设备连接正确")
        self.setMinimumSize(500, 350)
        self.setModal(True)
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # ---- 标题和图标 ----
        title_layout = QHBoxLayout()
        
        # 警告图标
        warning_label = QLabel("⚠️")
        warning_label.setStyleSheet("font-size: 32px;")
        title_layout.addWidget(warning_label)
        
        # 标题
        if self._settings_opened:
            title_text = "已在目标设备上打开设置界面"
            title_color = "#d9534f"  # 红色
        else:
            title_text = "设备连接（降级模式）"
            title_color = "#f0ad4e"  # 橙色
        
        title_label = QLabel(title_text)
        title_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {title_color};")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        layout.addLayout(title_layout)
        
        # ---- 分隔线 ----
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)
        
        # ---- 提示信息 ----
        if self._settings_opened:
            tip_label = QLabel(
                "请在模拟器屏幕上观察是否显示设置界面。\n"
                "如果没有看到设置界面，说明连接的设备不正确。"
            )
        else:
            tip_label = QLabel(
                f"⚠️ 该设备不支持自动打开设置界面\n"
                f"原因: {self._fallback_message}\n\n"
                "请手动确认:\n"
                "1. 观察模拟器屏幕是否正常显示\n"
                "2. 确认这是您要连接的设备"
            )
        
        tip_label.setWordWrap(True)
        tip_label.setStyleSheet("font-size: 13px; color: #666;")
        layout.addWidget(tip_label)
        
        # ---- 设备信息卡片 ----
        info_frame = QFrame()
        info_frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        info_frame.setStyleSheet("background-color: #f5f5f5; border-radius: 5px;")
        info_layout = QVBoxLayout(info_frame)
        info_layout.setSpacing(8)
        
        # 设备名称
        name_label = QLabel(f"<b>设备名称:</b> {self._device_info.name}")
        info_layout.addWidget(name_label)
        
        # 型号/品牌
        model_brand = f"{self._device_info.model}"
        if self._device_info.brand and self._device_info.brand.lower() not in ["unknown", ""]:
            model_brand += f" / {self._device_info.brand}"
        if self._device_info.android_version:
            model_brand += f" (Android {self._device_info.android_version})"
        model_label = QLabel(f"<b>型号/品牌:</b> {model_brand}")
        info_layout.addWidget(model_label)
        
        # 分辨率
        if self._device_info.resolution:
            res_label = QLabel(f"<b>分辨率:</b> {self._device_info.resolution}")
            info_layout.addWidget(res_label)
        
        # 地址（小字显示）
        addr_label = QLabel(f"<small>地址: {self._address}</small>")
        addr_label.setStyleSheet("color: #999;")
        info_layout.addWidget(addr_label)
        
        layout.addWidget(info_frame)
        
        # ---- 按钮区 ----
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        # 正确按钮
        self._correct_btn = QPushButton("✅ 连接正确")
        self._correct_btn.setMinimumWidth(120)
        self._correct_btn.setStyleSheet("""
            QPushButton {
                background-color: #5cb85c;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #4cae4c;
            }
        """)
        self._correct_btn.clicked.connect(self._on_correct_clicked)
        btn_layout.addWidget(self._correct_btn)
        
        # 错误按钮
        self._wrong_btn = QPushButton("❌ 连接错误")
        self._wrong_btn.setMinimumWidth(120)
        self._wrong_btn.setStyleSheet("""
            QPushButton {
                background-color: #d9534f;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #c9302c;
            }
        """)
        self._wrong_btn.clicked.connect(self._on_wrong_clicked)
        btn_layout.addWidget(self._wrong_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
    
    def _on_correct_clicked(self):
        """用户点击"连接正确"按钮"""
        logger.info(f"用户确认设备 {self._address} 连接正确")
        self.accept()  # 返回 Accepted
    
    def _on_wrong_clicked(self):
        """用户点击"连接错误"按钮"""
        # 二级确认
        reply = QMessageBox.question(
            self,
            "确认标记为错误",
            f"确定要将 {self._address} 标记为错误设备吗？\n\n"
            f"该设备将加入黑名单，下次扫描时自动忽略。\n"
            f"您可以在【工具 → 设备管理 → 设置】中管理黑名单。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            logger.info(f"用户标记设备 {self._address} 为错误")
            self.reject()  # 返回 Rejected
        # 否则不做任何操作，保持对话框打开
