"""
批量验证对话框

职责:
    - 显示所有待验证设备的列表
    - 逐个连接并打开设置界面
    - 让用户逐个确认每个设备
    - 最终显示验证结果汇总
"""

import logging
from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox,
    QProgressDialog, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from game_platform.adb.scanner import EmulatorInfo

logger = logging.getLogger(__name__)


class BatchVerificationDialog(QDialog):
    """批量验证对话框

    自动连接所有未验证设备，逐个让用户确认
    """

    # 结果列定义
    COL_NAME = 0
    COL_MODEL = 1
    COL_RESULT = 2

    # 验证结果
    RESULT_PENDING = "pending"
    RESULT_VERIFIED = "verified"
    RESULT_BLACKLISTED = "blacklisted"
    RESULT_FAILED = "failed"

    def __init__(self, device_manager, unverified_devices: List[EmulatorInfo], parent=None):
        """初始化批量验证对话框

        Args:
            device_manager: DeviceManager 实例
            unverified_devices: 待验证的设备信息列表
            parent: 父窗口
        """
        super().__init__(parent)
        self._dm = device_manager
        self._unverified = unverified_devices
        self._results: Dict[str, str] = {}  # address -> result
        self._current_index = 0

        self.setWindowTitle("批量设备验证")
        self.setMinimumSize(650, 500)
        self.setModal(True)

        self._init_ui()

        # 初始化结果
        for info in self._unverified:
            self._results[info.address] = self.RESULT_PENDING

    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ---- 标题 ----
        title_label = QLabel(f"共发现 {len(self._unverified)} 个未验证设备")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)

        desc_label = QLabel(
            "将逐个连接设备并打开设置界面，请确认每个设备是否正确。\n"
            "验证通过的设备下次连接时不再弹窗。"
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666;")
        layout.addWidget(desc_label)

        # ---- 分隔线 ----
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # ---- 设备列表表格 ----
        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["设备名称", "型号/品牌", "验证结果"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_MODEL, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_RESULT, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(self.COL_RESULT, 100)

        self._populate_table()
        layout.addWidget(self._table)

        # ---- 当前设备提示区 ----
        self._current_frame = QFrame()
        self._current_frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self._current_frame.setStyleSheet("background-color: #fff3cd; border-radius: 5px; padding: 10px;")
        current_layout = QVBoxLayout(self._current_frame)

        self._current_label = QLabel('点击“开始验证”按钮开始逐个验证设备')
        self._current_label.setWordWrap(True)
        self._current_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        current_layout.addWidget(self._current_label)

        self._current_detail_label = QLabel("")
        self._current_detail_label.setWordWrap(True)
        self._current_detail_label.setStyleSheet("color: #666;")
        current_layout.addWidget(self._current_detail_label)

        layout.addWidget(self._current_frame)

        # ---- 按钮区 ----
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._start_btn = QPushButton("开始验证")
        self._start_btn.setMinimumWidth(120)
        self._start_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #0069d9; }
        """)
        self._start_btn.clicked.connect(self._on_start_clicked)
        btn_layout.addWidget(self._start_btn)

        self._skip_btn = QPushButton("跳过此设备")
        self._skip_btn.setMinimumWidth(100)
        self._skip_btn.setEnabled(False)
        self._skip_btn.clicked.connect(self._on_skip_clicked)
        btn_layout.addWidget(self._skip_btn)

        self._correct_btn = QPushButton("连接正确")
        self._correct_btn.setMinimumWidth(100)
        self._correct_btn.setEnabled(False)
        self._correct_btn.setStyleSheet("""
            QPushButton {
                background-color: #5cb85c;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #4cae4c; }
        """)
        self._correct_btn.clicked.connect(self._on_correct_clicked)
        btn_layout.addWidget(self._correct_btn)

        self._wrong_btn = QPushButton("连接错误")
        self._wrong_btn.setMinimumWidth(100)
        self._wrong_btn.setEnabled(False)
        self._wrong_btn.setStyleSheet("""
            QPushButton {
                background-color: #d9534f;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #c9302c; }
        """)
        self._wrong_btn.clicked.connect(self._on_wrong_clicked)
        btn_layout.addWidget(self._wrong_btn)

        self._close_btn = QPushButton("关闭")
        self._close_btn.setMinimumWidth(80)
        self._close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self._close_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _populate_table(self):
        """填充设备列表表格"""
        self._table.setRowCount(len(self._unverified))

        for i, info in enumerate(self._unverified):
            # 设备名称
            name = info.name if info.name else info.address
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, info.address)
            self._table.setItem(i, self.COL_NAME, name_item)

            # 型号/品牌
            model_brand = info.model or "—"
            if info.brand and info.brand.lower() not in ["unknown", ""]:
                model_brand += f" / {info.brand}"
            self._table.setItem(i, self.COL_MODEL, QTableWidgetItem(model_brand))

            # 验证结果
            result_item = QTableWidgetItem("待验证")
            result_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i, self.COL_RESULT, result_item)

    def _on_start_clicked(self):
        """开始批量验证"""
        self._start_btn.setEnabled(False)
        self._current_index = 0
        self._verify_next()

    def _verify_next(self):
        """验证下一个设备"""
        if self._current_index >= len(self._unverified):
            self._show_summary()
            return

        info = self._unverified[self._current_index]
        address = info.address

        # 高亮当前行
        self._table.selectRow(self._current_index)

        # 尝试连接并打开设置
        self._current_label.setText(f"正在验证: {info.name or address}")
        self._current_detail_label.setText(f"地址: {address}  型号: {info.model}")
        QApplication.processEvents()

        # 连接设备
        parts = address.rsplit(":", 1)
        if len(parts) != 2:
            self._results[address] = self.RESULT_FAILED
            self._update_row_result(self._current_index, "连接失败", QColor("#f5c6cb"))
            self._current_index += 1
            self._verify_next()
            return

        host, port = parts[0], int(parts[1])
        device = self._dm.connect_device(host, port)

        if device is None:
            self._results[address] = self.RESULT_FAILED
            self._update_row_result(self._current_index, "连接失败", QColor("#f5c6cb"))
            self._current_label.setText(f"连接失败: {info.name or address}")
            self._current_detail_label.setText("无法连接该设备，已自动跳过")
            self._current_index += 1
            self._verify_next()
            return

        # 尝试打开设置
        settings_opened = True
        try:
            device._device.shell("am start -a android.settings.SETTINGS")
        except Exception as e:
            settings_opened = False
            logger.warning(f"打开设置失败 {address}: {e}")

        # 更新提示
        if settings_opened:
            self._current_label.setText(
                f"已在 [{info.name or address}] 上打开设置界面"
            )
            self._current_detail_label.setText(
                "请观察模拟器屏幕，确认是否是您要的设备"
            )
        else:
            self._current_label.setText(
                f"[{info.name or address}] 无法自动打开设置"
            )
            self._current_detail_label.setText(
                "请手动确认这是否是您的设备"
            )

        # 启用操作按钮
        self._correct_btn.setEnabled(True)
        self._wrong_btn.setEnabled(True)
        self._skip_btn.setEnabled(True)

    def _on_correct_clicked(self):
        """当前设备验证正确"""
        info = self._unverified[self._current_index]
        address = info.address

        self._results[address] = self.RESULT_VERIFIED
        self._dm.config.mark_as_verified(address, info.name or address, info.model, info.brand)
        self._update_row_result(self._current_index, "已验证", QColor("#d4edda"))

        self._correct_btn.setEnabled(False)
        self._wrong_btn.setEnabled(False)
        self._skip_btn.setEnabled(False)
        self._current_index += 1
        self._verify_next()

    def _on_wrong_clicked(self):
        """当前设备验证错误"""
        # 二级确认
        info = self._unverified[self._current_index]
        reply = QMessageBox.question(
            self, "确认标记为错误",
            f"确定要将 [{info.name or info.address}] 标记为错误设备吗？\n\n"
            f"该设备将加入黑名单。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        address = info.address
        self._results[address] = self.RESULT_BLACKLISTED
        self._dm.config.add_to_blacklist(address)
        self._dm.disconnect_device(address)
        self._update_row_result(self._current_index, "黑名单", QColor("#f5c6cb"))

        self._correct_btn.setEnabled(False)
        self._wrong_btn.setEnabled(False)
        self._skip_btn.setEnabled(False)
        self._current_index += 1
        self._verify_next()

    def _on_skip_clicked(self):
        """跳过当前设备"""
        info = self._unverified[self._current_index]
        self._update_row_result(self._current_index, "已跳过", QColor("#fff3cd"))

        # 断开连接
        self._dm.disconnect_device(info.address)

        self._correct_btn.setEnabled(False)
        self._wrong_btn.setEnabled(False)
        self._skip_btn.setEnabled(False)
        self._current_index += 1
        self._verify_next()

    def _update_row_result(self, row: int, text: str, color: QColor):
        """更新某行的验证结果"""
        result_item = QTableWidgetItem(text)
        result_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        result_item.setBackground(color)
        self._table.setItem(row, self.COL_RESULT, result_item)

    def _show_summary(self):
        """显示验证结果汇总"""
        verified = sum(1 for r in self._results.values() if r == self.RESULT_VERIFIED)
        blacklisted = sum(1 for r in self._results.values() if r == self.RESULT_BLACKLISTED)
        failed = sum(1 for r in self._results.values() if r == self.RESULT_FAILED)
        skipped = sum(1 for r in self._results.values() if r == self.RESULT_PENDING)

        self._current_frame.setStyleSheet("background-color: #d4edda; border-radius: 5px; padding: 10px;")
        self._current_label.setText("批量验证完成!")
        self._current_detail_label.setText(
            f"已验证: {verified} 个  |  黑名单: {blacklisted} 个  |  "
            f"失败: {failed} 个  |  跳过: {skipped} 个"
        )

        self._correct_btn.setEnabled(False)
        self._wrong_btn.setEnabled(False)
        self._skip_btn.setEnabled(False)

        logger.info(f"批量验证完成: verified={verified}, blacklisted={blacklisted}, "
                    f"failed={failed}, skipped={skipped}")

    @property
    def results(self) -> Dict[str, str]:
        """获取验证结果"""
        return dict(self._results)
