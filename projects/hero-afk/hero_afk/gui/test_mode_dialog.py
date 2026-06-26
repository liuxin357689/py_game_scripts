"""
测试模式对话框（单设备版本）

功能：
    - 选择任务进行手动测试
    - 点击"手动截取画面"推送截图给选中的任务
    - 任务返回动作后在截图上标注并保存到 test_captures 目录
    - 支持连续多帧测试

截图保存路径：D:\game_scripts\game_platform\hero-afk\test_captures\
"""

import logging
import os
from datetime import datetime

import cv2
import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QTextEdit,
)

logger = logging.getLogger(__name__)

# 测试截图保存根目录（game_platform项目下的共享目录）
_TEST_CAPTURES_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )))),
    "game_platform", "hero-afk", "test_captures",
)


def _ensure_dir(path: str):
    """确保目录存在"""
    os.makedirs(path, exist_ok=True)


def _cv2_to_qpixmap(img: np.ndarray) -> QPixmap:
    """将 BGR numpy array 转换为 QPixmap"""
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    bytes_per_line = 3 * w
    qimage = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimage)


class TestModeDialog(QDialog):
    """测试模式对话框（单设备版本）"""

    # 对话框关闭信号
    closed = pyqtSignal()

    def __init__(
        self,
        task_manager,
        parent=None,
    ):
        """
        Args:
            task_manager: FrameTaskManagerAdapter 实例（单设备）
            parent: 父窗口
        """
        super().__init__(parent)
        self._task_manager = task_manager
        self._current_task = None
        self._frame_count = 0

        # 确保保存目录存在
        _ensure_dir(_TEST_CAPTURES_ROOT)

        self.setWindowTitle("测试模式")
        self.resize(500, 700)
        self.setModal(False)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ---- 任务选择 ----
        task_group = QGroupBox("任务选择")
        task_layout = QHBoxLayout()
        self._task_combo = QComboBox()
        self._task_combo.currentIndexChanged.connect(self._on_task_changed)
        task_layout.addWidget(QLabel("任务:"))
        task_layout.addWidget(self._task_combo, 1)
        task_group.setLayout(task_layout)
        layout.addWidget(task_group)

        # ---- 连接状态 ----
        self._status_label = QLabel("未连接设备")
        self._status_label.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(self._status_label)

        # ---- 截图预览 ----
        preview_group = QGroupBox("截图预览")
        preview_layout = QVBoxLayout()

        self._preview_label = QLabel("<点击「手动截取画面」开始测试>")
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet(
            "background-color: #2b2b2b; color: #888; "
            "border: 1px solid #444; font-size: 14px;"
        )
        self._preview_label.setMinimumHeight(400)
        self._preview_label.setWordWrap(True)

        preview_layout.addWidget(self._preview_label)
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group, 1)

        # ---- 操作日志 ----
        log_group = QGroupBox("操作日志")
        log_layout = QVBoxLayout()
        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumHeight(120)
        log_layout.addWidget(self._log_text)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        # ---- 按钮栏 ----
        btn_layout = QHBoxLayout()
        self._capture_btn = QPushButton("手动截取画面")
        self._capture_btn.setMinimumHeight(40)
        self._capture_btn.clicked.connect(self._on_capture)

        self._activate_btn = QPushButton("激活任务")
        self._activate_btn.clicked.connect(self._on_toggle_activation)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)

        btn_layout.addWidget(self._capture_btn)
        btn_layout.addWidget(self._activate_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        # 初始刷新
        self._refresh_status()
        self._refresh_tasks()

    def closeEvent(self, event):
        """窗口关闭时发射信号"""
        self.closed.emit()
        super().closeEvent(event)

    def showEvent(self, event):
        """对话框显示时刷新状态"""
        super().showEvent(event)
        self._refresh_status()

    def _refresh_status(self):
        """刷新连接状态"""
        if self._task_manager.is_connected:
            addr = self._task_manager.device_address or "未知"
            self._status_label.setText(f"已连接: {addr}")
            self._status_label.setStyleSheet("color: #4ec9b0; font-size: 12px;")
            self._capture_btn.setEnabled(True)
        else:
            self._status_label.setText("未连接设备")
            self._status_label.setStyleSheet("color: #888; font-size: 12px;")
            self._capture_btn.setEnabled(False)

    def _refresh_tasks(self):
        """刷新任务列表"""
        self._task_combo.clear()
        for name in self._task_manager.list_tasks():
            self._task_combo.addItem(name, name)

    def _on_task_changed(self, index: int):
        """任务选择变更"""
        self._current_task = None
        self._update_activate_btn()

    def _on_toggle_activation(self):
        """切换任务激活状态"""
        task_name = self._task_combo.currentData()
        if not task_name:
            return

        service = self._get_current_service()
        if not service:
            self._log("错误: 无可用截图服务")
            return

        task = service.get_task(task_name)
        if not task:
            self._log(f"错误: 任务 {task_name} 不存在")
            return

        if task.is_active:
            self._task_manager.stop_task(task_name)
            self._log(f"[{task_name}] 已停用")
        else:
            self._task_manager.start_task(task_name)
            self._log(f"[{task_name}] 已激活")
        self._update_activate_btn()

    def _update_activate_btn(self):
        """更新激活按钮状态"""
        task_name = self._task_combo.currentData()
        if not task_name:
            self._activate_btn.setEnabled(False)
            return

        service = self._get_current_service()
        if not service:
            self._activate_btn.setEnabled(False)
            return

        task = service.get_task(task_name)
        if not task:
            self._activate_btn.setEnabled(False)
            return

        self._activate_btn.setEnabled(True)
        self._activate_btn.setText("停用任务" if task.is_active else "激活任务")

    def _get_current_service(self):
        """获取截图服务（单设备）"""
        return self._task_manager._service

    def _log(self, msg: str):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_text.append(f"[{timestamp}] {msg}")
        # 滚动到底部
        self._log_text.verticalScrollBar().setValue(
            self._log_text.verticalScrollBar().maximum()
        )

    def _on_capture(self):
        """手动截图并推送给任务"""
        service = self._get_current_service()
        if not service:
            self._log("错误: 无可用截图服务")
            return

        task_name = self._task_combo.currentData()
        if not task_name:
            self._log("错误: 未选择任务")
            return

        task = service.get_task(task_name)
        if not task:
            self._log(f"错误: 任务 {task_name} 不存在")
            return

        device = service._device
        if not device or not device.is_connected():
            self._log("错误: 设备未连接")
            return

        # 截图
        try:
            raw = device.screenshot()
            screen = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
            if screen is None:
                self._log("错误: 截图解码失败")
                return
        except Exception as e:
            self._log(f"错误: 截图失败 - {e}")
            return

        self._frame_count += 1

        # 调用任务 on_frame
        try:
            action = task.on_frame(screen)
        except Exception as e:
            self._log(f"错误: on_frame 异常 - {e}")
            return

        # 获取任务内部状态（通过日志上下文推断）
        state_desc = self._get_task_state_desc(task)

        # 调用 annotate_detection 绘制标注
        try:
            annotated = task.annotate_detection(screen, action)
        except Exception:
            annotated = screen.copy()

        # 更新预览
        pixmap = _cv2_to_qpixmap(annotated)
        scaled = pixmap.scaled(
            self._preview_label.width(),
            self._preview_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_label.setPixmap(scaled)
        self._preview_label.setText("")

        # 保存截图
        self._save_capture(task_name, state_desc, annotated, action)

        # 日志
        if action is not None:
            self._log(
                f"[{self._frame_count}] {task_name} | {state_desc} | "
                f"{action.description or '点击'}({action.x}, {action.y})"
            )
        else:
            self._log(f"[{self._frame_count}] {task_name} | {state_desc} | 无操作")

    def _get_task_state_desc(self, task) -> str:
        """获取任务当前状态描述"""
        # 尝试获取任务内部状态（通过内部变量）
        state = getattr(task, "_state", None)
        if state is not None:
            # FrameTask 可能有内部状态机
            state_name = getattr(state, "name", str(state))
            return state_name
        return "RUNNING" if task.is_active else "IDLE"

    def _save_capture(
        self,
        task_name: str,
        state: str,
        annotated: np.ndarray,
        action,
    ):
        """保存标注后的截图"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = task_name.replace("/", "_").replace("\\", "_")
        safe_state = state.replace("/", "_").replace("\\", "_")

        filename = f"{safe_name}_{safe_state}_{timestamp}.png"
        filepath = os.path.join(_TEST_CAPTURES_ROOT, filename)

        try:
            cv2.imwrite(filepath, annotated)
            self._log(f"已保存: {filename}")
            logger.info(f"测试截图已保存: {filepath}")
        except Exception as e:
            self._log(f"保存失败: {e}")
            logger.error(f"保存测试截图失败: {e}")

    def resizeEvent(self, event):
        """窗口大小改变时重新缩放预览图"""
        super().resizeEvent(event)
        # 预览图会在下次截图时自动更新大小
