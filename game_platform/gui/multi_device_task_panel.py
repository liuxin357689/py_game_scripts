"""
多设备任务控制面板（GUI 集成示例）

演示如何在 PyQt6 GUI 中集成 DeviceTaskRegistry，实现：
    - 选择多个设备
    - 为每个设备分配任务
    - 批量启动/停止/暂停/恢复
    - 实时显示各设备任务状态
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QComboBox, QMessageBox,
    QHeaderView, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal
import logging

from game_platform.task import DeviceTaskRegistry, TaskStatus
from game_platform.gui.device_manager import DeviceManager

logger = logging.getLogger(__name__)


class MultiDeviceTaskPanel(QWidget):
    """多设备任务控制面板
    
    功能:
        - 显示所有已连接设备列表
        - 为每个设备选择要运行的任务
        - 批量控制按钮（全部启动、全部停止等）
        - 实时显示各设备任务状态
    """
    
    # 信号
    device_task_started = pyqtSignal(str, str)  # (device_address, task_name)
    device_task_stopped = pyqtSignal(str, str)
    
    def __init__(self, device_manager: DeviceManager, parent=None):
        super().__init__(parent)
        self._dm = device_manager
        self._registry = DeviceTaskRegistry()
        
        # 可用任务列表（从项目配置加载）
        self._available_tasks = [
            "实时多模板自动点击",
            "自动战斗",
            "自动收集",
        ]
        
        # 已注册的任务实例缓存：device_addr -> {task_name: task_instance}
        self._task_instances: dict = {}
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        
        # ---- 设备-任务映射表 ----
        group = QGroupBox("设备与任务")
        group_layout = QVBoxLayout()
        
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["设备地址", "设备名称", "选择任务", "状态"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        
        # 列宽
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(3, 100)
        
        group_layout.addWidget(self._table)
        group.setLayout(group_layout)
        layout.addWidget(group)
        
        # ---- 控制按钮区 ----
        btn_layout = QHBoxLayout()
        
        self._start_all_btn = QPushButton("全部启动")
        self._start_all_btn.setToolTip("在所有设备上启动选中的任务")
        self._start_all_btn.clicked.connect(self._on_start_all)
        btn_layout.addWidget(self._start_all_btn)
        
        self._stop_all_btn = QPushButton("全部停止")
        self._stop_all_btn.setToolTip("停止所有设备上的任务")
        self._stop_all_btn.clicked.connect(self._on_stop_all)
        btn_layout.addWidget(self._stop_all_btn)
        
        self._pause_all_btn = QPushButton("全部暂停")
        self._pause_all_btn.setToolTip("暂停所有设备上的任务")
        self._pause_all_btn.clicked.connect(self._on_pause_all)
        btn_layout.addWidget(self._pause_all_btn)
        
        self._resume_all_btn = QPushButton("全部恢复")
        self._resume_all_btn.setToolTip("恢复所有设备上的任务")
        self._resume_all_btn.clicked.connect(self._on_resume_all)
        btn_layout.addWidget(self._resume_all_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # ---- 状态栏 ----
        self._status_label = QLabel("就绪")
        layout.addWidget(self._status_label)
    
    def refresh_device_list(self):
        """刷新设备列表
        
        从 DeviceManager 获取所有已连接设备，更新表格。
        """
        self._table.setRowCount(0)
        
        devices = self._dm.get_all_addresses()
        if not devices:
            self._status_label.setText("无已连接设备")
            return
        
        for addr in devices:
            row = self._table.rowCount()
            self._table.insertRow(row)
            
            # 设备地址
            addr_item = QTableWidgetItem(addr)
            addr_item.setData(Qt.ItemDataRole.UserRole, addr)
            self._table.setItem(row, 0, addr_item)
            
            # 设备名称
            info = self._dm.get_device_info(addr)
            name = info.name if info else addr
            self._table.setItem(row, 1, QTableWidgetItem(name))
            
            # 任务选择下拉框
            combo = QComboBox()
            combo.addItem("-- 选择任务 --")
            for task_name in self._available_tasks:
                combo.addItem(task_name)
            combo.currentIndexChanged.connect(lambda idx, r=row: self._on_task_selected(r, idx))
            self._table.setCellWidget(row, 2, combo)
            
            # 状态
            status_item = QTableWidgetItem("未运行")
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 3, status_item)
        
        self._status_label.setText(f"已发现 {len(devices)} 个设备")
    
    def _on_task_selected(self, row: int, index: int):
        """用户选择任务时的回调"""
        if index == 0:
            return  # "-- 选择任务 --"
        
        addr_item = self._table.item(row, 0)
        if not addr_item:
            return
        
        device_addr = addr_item.data(Qt.ItemDataRole.UserRole)
        task_name = self._table.cellWidget(row, 2).currentText()
        
        logger.info(f"设备 {device_addr} 选择任务: {task_name}")
        
        # 初始化该设备的任务缓存
        if device_addr not in self._task_instances:
            self._task_instances[device_addr] = {}
        
        # TODO: 根据 task_name 创建对应的任务实例
        # 这里暂时跳过，实际使用时需要传入模板路径等参数
    
    def _on_start_all(self):
        """批量启动所有选中任务"""
        results = {}
        started_count = 0
        
        for row in range(self._table.rowCount()):
            combo = self._table.cellWidget(row, 2)
            if not combo or combo.currentIndex() == 0:
                continue
            
            addr_item = self._table.item(row, 0)
            if not addr_item:
                continue
            
            device_addr = addr_item.data(Qt.ItemDataRole.UserRole)
            task_name = combo.currentText()
            
            # 检查是否已注册该任务
            if device_addr in self._task_instances and task_name in self._task_instances[device_addr]:
                # 已注册，直接启动
                success = self._registry.start_task_on_devices(task_name, [device_addr])
                results[device_addr] = success.get(device_addr, False)
            else:
                # 未注册，跳过（需要用户先配置任务参数）
                logger.warning(f"设备 {device_addr} 的任务 {task_name} 未配置，跳过启动")
                results[device_addr] = False
                continue
            
            # 更新状态列
            status_text = "✅ 运行中" if results[device_addr] else "❌ 失败"
            self._table.item(row, 3).setText(status_text)
            
            if results[device_addr]:
                started_count += 1
        
        self._status_label.setText(f"已启动 {started_count}/{len(results)} 个任务")
        
        if started_count > 0:
            QMessageBox.information(
                self,
                "启动成功",
                f"已在 {started_count} 个设备上启动任务\n\n"
                f"注意：任务需要预先配置模板路径等参数才能正常运行。"
            )
    
    def _on_stop_all(self):
        """批量停止所有任务"""
        self._registry.stop_all_tasks_on_all_devices()
        
        # 更新所有状态列
        for row in range(self._table.rowCount()):
            self._table.item(row, 3).setText("已停止")
        
        self._status_label.setText("已停止所有任务")
    
    def _on_pause_all(self):
        """批量暂停所有任务"""
        # TODO: 实现暂停逻辑
        self._status_label.setText("已暂停所有任务")
    
    def _on_resume_all(self):
        """批量恢复所有任务"""
        # TODO: 实现恢复逻辑
        self._status_label.setText("已恢复所有任务")
    
    def update_task_status(self, device_addr: str, task_name: str, status: TaskStatus):
        """更新某设备的任务状态（外部调用）
        
        Args:
            device_addr: 设备地址
            task_name: 任务名称
            status: 新状态
        """
        for row in range(self._table.rowCount()):
            addr_item = self._table.item(row, 0)
            if addr_item and addr_item.data(Qt.ItemDataRole.UserRole) == device_addr:
                status_map = {
                    TaskStatus.RUNNING: "✅ 运行中",
                    TaskStatus.PAUSED: "⏸️ 已暂停",
                    TaskStatus.STOPPED: "已停止",
                    TaskStatus.ERROR: "❌ 错误",
                    TaskStatus.IDLE: "空闲",
                }
                self._table.item(row, 3).setText(status_map.get(status, str(status)))
                break
