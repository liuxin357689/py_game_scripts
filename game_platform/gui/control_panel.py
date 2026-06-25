"""
控制面板基类（多选任务模式）

职责:
    - 多任务选择（QCheckBox 列表）
    - 批量启动/停止/暂停/恢复
    - 每个任务独立显示状态
    - 任务进度显示

各项目通过继承来定制自己的控制面板
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QCheckBox, QProgressBar, QGroupBox,
    QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor
import logging

logger = logging.getLogger(__name__)

# 状态轮询间隔（毫秒）
STATUS_POLL_INTERVAL = 500

# 状态颜色映射
_STATUS_COLORS = {
    "idle": "#888888",
    "running": "#4ec9b0",
    "paused": "#dcdcaa",
    "stopped": "#888888",
    "error": "#f44747",
}

_STATUS_LABELS = {
    "idle": "空闲",
    "running": "运行中",
    "paused": "已暂停",
    "stopped": "已停止",
    "error": "出错",
}


class ControlPanel(QWidget):
    """多选任务控制面板，支持同时运行多个任务"""

    # 自定义信号
    task_started = pyqtSignal(str)
    task_stopped = pyqtSignal(str)
    task_paused = pyqtSignal(str)
    task_resumed = pyqtSignal(str)

    def __init__(self, task_manager=None, parent=None):
        """初始化控制面板

        Args:
            task_manager: TaskManager / MultiDeviceTaskManager 实例
            parent: 父窗口
        """
        super().__init__(parent)
        self._task_manager = task_manager
        # task_name -> QCheckBox 的映射
        self._checkboxes: dict[str, QCheckBox] = {}
        # task_name -> QLabel (状态标签) 的映射
        self._status_labels: dict[str, QLabel] = {}
        # task_name -> 上一次轮询的状态值（用于检测状态跳变）
        self._prev_status: dict[str, str] = {}

        self._init_ui()

        if self._task_manager:
            self._refresh_task_list()

        # 状态轮询定时器
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._poll_status)
        self._status_timer.start(STATUS_POLL_INTERVAL)

    def _init_ui(self):
        """初始化控制面板 UI"""
        layout = QVBoxLayout(self)

        # ---- 任务选择组 ----
        task_group = QGroupBox("任务列表")
        task_layout = QVBoxLayout()

        # 全选/取消全选
        select_row = QHBoxLayout()
        self._select_all_cb = QCheckBox("全选")
        self._select_all_cb.stateChanged.connect(self._on_select_all)
        select_row.addWidget(self._select_all_cb)
        select_row.addStretch()
        task_layout.addLayout(select_row)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #444;")
        task_layout.addWidget(line)

        # 任务列表（可滚动区域）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMaximumHeight(200)

        self._task_list_widget = QWidget()
        self._task_list_layout = QVBoxLayout(self._task_list_widget)
        self._task_list_layout.setContentsMargins(4, 4, 4, 4)
        self._task_list_layout.setSpacing(2)
        self._task_list_layout.addStretch()

        scroll.setWidget(self._task_list_widget)
        task_layout.addWidget(scroll)

        task_group.setLayout(task_layout)
        layout.addWidget(task_group)

        # ---- 控制按钮 ----
        btn_layout = QHBoxLayout()

        self._start_btn = QPushButton("启动选中")
        self._start_btn.setStyleSheet(
            "QPushButton { background-color: #2ea043; color: white; padding: 6px 16px; font-weight: bold; }"
            "QPushButton:hover { background-color: #3fb950; }"
            "QPushButton:disabled { background-color: #555; color: #999; }"
        )
        self._start_btn.clicked.connect(self._on_start_clicked)
        self._start_btn.setEnabled(False)
        btn_layout.addWidget(self._start_btn)

        self._stop_btn = QPushButton("停止选中")
        self._stop_btn.setStyleSheet(
            "QPushButton { background-color: #da3633; color: white; padding: 6px 16px; font-weight: bold; }"
            "QPushButton:hover { background-color: #f85149; }"
            "QPushButton:disabled { background-color: #555; color: #999; }"
        )
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        self._stop_btn.setEnabled(False)
        btn_layout.addWidget(self._stop_btn)

        self._pause_btn = QPushButton("暂停选中")
        self._pause_btn.clicked.connect(self._on_pause_clicked)
        self._pause_btn.setEnabled(False)
        btn_layout.addWidget(self._pause_btn)

        self._resume_btn = QPushButton("恢复选中")
        self._resume_btn.clicked.connect(self._on_resume_clicked)
        self._resume_btn.setEnabled(False)
        btn_layout.addWidget(self._resume_btn)

        layout.addLayout(btn_layout)

        # ---- 状态汇总 ----
        self._summary_label = QLabel("无可用任务")
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary_label.setStyleSheet("color: #888; padding: 4px;")
        layout.addWidget(self._summary_label)

        # 进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        layout.addStretch()

    # ---- 任务列表管理 ----

    def set_task_manager(self, task_manager):
        """设置任务管理器"""
        self._task_manager = task_manager
        self._refresh_task_list()

    def _refresh_task_list(self):
        """刷新任务列表，为每个任务创建 CheckBox + 状态标签"""
        if not self._task_manager:
            return

        # 清空旧控件
        for cb in self._checkboxes.values():
            cb.deleteLater()
        for lbl in self._status_labels.values():
            lbl.deleteLater()
        self._checkboxes.clear()
        self._status_labels.clear()
        self._prev_status.clear()

        tasks = self._task_manager.list_tasks()
        if not tasks:
            self._summary_label.setText("无可用任务")
            return

        for task_name in tasks:
            row = QHBoxLayout()

            # CheckBox
            cb = QCheckBox(task_name)
            cb.setStyleSheet("QCheckBox { spacing: 8px; padding: 2px; }")
            cb.stateChanged.connect(self._on_selection_changed)
            self._checkboxes[task_name] = cb
            row.addWidget(cb, stretch=1)

            # 状态标签
            status_lbl = QLabel("空闲")
            status_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            status_lbl.setStyleSheet("color: #888; font-size: 12px; padding-right: 4px;")
            status_lbl.setFixedWidth(70)
            self._status_labels[task_name] = status_lbl
            row.addWidget(status_lbl)

            self._task_list_layout.insertLayout(
                self._task_list_layout.count() - 1, row  # 插在 stretch 之前
            )

        self._update_summary()

    def _get_checked_tasks(self) -> list[str]:
        """获取所有勾选的任务名称"""
        return [
            name for name, cb in self._checkboxes.items()
            if cb.isChecked()
        ]

    # ---- 全选/取消全选 ----

    def _on_select_all(self, state):
        """全选/取消全选"""
        checked = state == Qt.CheckState.Checked.value
        for cb in self._checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        self._on_selection_changed()

    # ---- 选区变更 ----

    def _on_selection_changed(self):
        """勾选状态变更，更新按钮可用状态"""
        checked = self._get_checked_tasks()
        has_selection = len(checked) > 0

        self._start_btn.setEnabled(has_selection)
        self._stop_btn.setEnabled(has_selection)
        self._pause_btn.setEnabled(has_selection)
        self._resume_btn.setEnabled(has_selection)

        self._update_summary()

    def _update_summary(self):
        """更新底部汇总"""
        total = len(self._checkboxes)
        checked = len(self._get_checked_tasks())
        if total == 0:
            self._summary_label.setText("无可用任务")
        elif checked == 0:
            self._summary_label.setText(f"共 {total} 个任务，未选中")
        else:
            running = sum(
                1 for name in self._get_checked_tasks()
                if self._task_manager and
                self._task_manager.get_task_status(name)
                and self._task_manager.get_task_status(name).value == "running"
            )
            self._summary_label.setText(
                f"共 {total} 个任务，已选 {checked} 个，运行中 {running} 个"
            )

    # ---- 状态轮询 ----

    def _poll_status(self):
        """轮询所有任务状态，更新 UI；检测 RUNNING→STOPPED 跳变并自动取消勾选"""
        if not self._task_manager:
            return

        for task_name, status_lbl in self._status_labels.items():
            status = self._task_manager.get_task_status(task_name)
            if status is None:
                continue

            status_value = status.value
            color = _STATUS_COLORS.get(status_value, "#888")
            text = _STATUS_LABELS.get(status_value, status_value)
            status_lbl.setText(text)
            status_lbl.setStyleSheet(
                f"color: {color}; font-size: 12px; padding-right: 4px;"
            )

            # 检测 RUNNING → STOPPED 跳变，自动取消勾选
            prev = self._prev_status.get(task_name)
            if prev == "running" and status_value == "stopped":
                cb = self._checkboxes.get(task_name)
                if cb and cb.isChecked():
                    cb.blockSignals(True)
                    cb.setChecked(False)
                    cb.blockSignals(False)
                    logger.info(f"任务 {task_name} 已自动停止，取消勾选")

            self._prev_status[task_name] = status_value

        self._update_summary()

    # ---- 按钮操作（批量） ----

    def _on_start_clicked(self):
        """启动所有选中的任务"""
        if not self._task_manager:
            return

        for name in self._get_checked_tasks():
            status = self._task_manager.get_task_status(name)
            if status and status.value == "running":
                logger.info(f"任务 {name} 已在运行，跳过")
                continue

            success = self._task_manager.start_task(name)
            if success:
                self.task_started.emit(name)
                logger.info(f"已启动任务: {name}")
            else:
                logger.warning(f"启动失败: {name}")

    def _on_stop_clicked(self):
        """停止所有选中的任务"""
        if not self._task_manager:
            return

        for name in self._get_checked_tasks():
            success = self._task_manager.stop_task(name)
            if success:
                self.task_stopped.emit(name)
                logger.info(f"已停止任务: {name}")

    def _on_pause_clicked(self):
        """暂停所有选中的任务"""
        if not self._task_manager:
            return

        for name in self._get_checked_tasks():
            success = self._task_manager.pause_task(name)
            if success:
                self.task_paused.emit(name)

    def _on_resume_clicked(self):
        """恢复所有选中的任务"""
        if not self._task_manager:
            return

        for name in self._get_checked_tasks():
            success = self._task_manager.resume_task(name)
            if success:
                self.task_resumed.emit(name)

    # ---- 外部接口 ----

    def update_progress(self, progress: int, message: str = ""):
        """更新任务进度"""
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(progress)
        if message:
            self._summary_label.setText(message)

    def refresh(self):
        """刷新面板状态"""
        self._refresh_task_list()
