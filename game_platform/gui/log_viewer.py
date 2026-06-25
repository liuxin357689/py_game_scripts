"""
日志查看器（通用）

职责:
    - 实时显示运行日志（支持通过下拉框选择最小显示级别）
    - 日志搜索
    - 日志导出

此组件为通用组件，各项目直接复用
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
    QPushButton, QTabWidget, QComboBox, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QTextCursor
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class LogHandler(logging.Handler):
    """自定义日志处理器，将日志发送到 Qt 信号
    
    支持单设备和多设备模式：
        - 单设备：不传 device_address，信号为 (message, level)
        - 多设备：传入 device_address，信号为 (message, level, device_address)
    
    当 attach_to_root=True 时，挂载到根 logger 并通过 logger_name 过滤

    过滤优先级：allowed_prefixes > filter_logger_name
        - allowed_prefixes: 仅允许 logger name 以指定前缀开头的日志（排除第三方库）
        - filter_logger_name: 仅允许 logger name 包含指定关键字的日志
    """

    # 全局日志白名单：只显示应用自身的日志，排除第三方库
    APP_LOGGER_PREFIXES = ("game_platform", "hero_afk", "projects")

    def __init__(
        self, signal, device_address: str = None,
        filter_logger_name: str = None,
        allowed_prefixes: tuple = None,
    ):
        super().__init__()
        self.signal = signal
        self.device_address = device_address
        self.filter_logger_name = filter_logger_name
        self.allowed_prefixes = allowed_prefixes
        self.setFormatter(logging.Formatter(
            '%(asctime)s | %(message)s',
            datefmt='%H:%M:%S'
        ))
    
    def emit(self, record):
        # 白名单过滤：排除第三方库日志（adb_shell, urllib3 等）
        if self.allowed_prefixes:
            if not record.name.startswith(self.allowed_prefixes):
                return

        # 关键字过滤（设备选项卡用）
        if self.filter_logger_name and self.filter_logger_name not in record.name:
            return
        
        msg = self.format(record)
        if self.device_address:
            # 多设备模式
            self.signal.emit(msg, record.levelno, self.device_address)
        else:
            # 单设备模式
            self.signal.emit(msg, record.levelno)


class MultiDeviceLogViewer(QWidget):
    """多设备日志查看器，每个设备独立一个选项卡显示日志
    
    功能:
        - 为每个设备创建独立的日志选项卡
        - 支持动态添加/移除设备日志
        - 统一的日志级别过滤
        - 日志导出
    """
    
    # 日志信号
    log_received = pyqtSignal(str, int, str)  # message, level, device_address
    device_tab_closed = pyqtSignal(str)  # device_address, 设备选项卡被关闭时触发

    def __init__(self, parent=None):
        """初始化多设备日志查看器
        
        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        self._log_handlers: dict = {}  # device_address -> LogHandler
        self._device_tabs: dict = {}   # device_address -> QTextEdit
        self._current_device: str = None  # 当前选中的设备地址
        self._min_level: int = logging.INFO  # 当前最小显示级别
        
        self._init_ui()
        
        # 连接信号
        self.log_received.connect(self._append_log)

    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        # 日志级别选择
        level_label = QLabel("级别:")
        level_label.setStyleSheet("color: #d4d4d4;")
        toolbar.addWidget(level_label)
        
        self._level_combo = QComboBox()
        self._level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self._level_combo.setCurrentText("DEBUG")
        self._level_combo.setToolTip("选择最小日志显示级别")
        self._level_combo.setStyleSheet("""
            QComboBox {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                padding: 2px 8px;
                min-width: 80px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #3c3c3c;
                color: #d4d4d4;
                selection-background-color: #094771;
            }
        """)
        self._level_combo.currentTextChanged.connect(self._on_level_changed)
        toolbar.addWidget(self._level_combo)
        
        toolbar.addStretch()
        
        clear_btn = QPushButton("清除当前")
        clear_btn.setToolTip("清除当前选中设备的日志")
        clear_btn.clicked.connect(self._clear_current_device_logs)
        toolbar.addWidget(clear_btn)
        
        clear_all_btn = QPushButton("清除全部")
        clear_all_btn.setToolTip("清除所有设备的日志")
        clear_all_btn.clicked.connect(self.clear_all_logs)
        toolbar.addWidget(clear_all_btn)
        
        layout.addLayout(toolbar)
        
        # 设备日志选项卡
        self._tab_widget = QTabWidget()
        self._tab_widget.setTabsClosable(True)
        self._tab_widget.tabCloseRequested.connect(self._on_tab_closed)
        self._tab_widget.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tab_widget)
        
        # 默认添加一个“全局”选项卡（显示所有设备日志）
        self._add_device_tab("全局", "global")

    def _add_device_tab(self, device_name: str, device_address: str):
        """为设备添加日志选项卡
        
        Args:
            device_name: 设备名称（显示在选项卡上）
            device_address: 设备地址（唯一标识）
        """
        if device_address in self._device_tabs:
            return  # 已存在
        
        # 创建日志文本框
        log_text = QTextEdit()
        log_text.setReadOnly(True)
        log_text.setStyleSheet("""
            QTextEdit {
                font-family: Consolas, 'Courier New', monospace;
                font-size: 12px;
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
        """)
        
        # 添加到选项卡
        tab_index = self._tab_widget.addTab(log_text, device_name)
        self._tab_widget.setTabToolTip(tab_index, device_address)
        
        # 保存引用
        self._device_tabs[device_address] = log_text
        
        # 创建日志处理器
        # 全局选项卡：挂载到根 logger，只显示应用自身日志（过滤第三方库）
        # 设备选项卡：挂载到根 logger，通过 logger name 过滤只显示该设备的日志
        if device_address == "global":
            handler = LogHandler(
                self.log_received, device_address,
                allowed_prefixes=LogHandler.APP_LOGGER_PREFIXES,
            )
        else:
            handler = LogHandler(
                self.log_received, device_address,
                filter_logger_name=device_address,
                allowed_prefixes=LogHandler.APP_LOGGER_PREFIXES,
            )
        handler.setLevel(logging.DEBUG)
        self._log_handlers[device_address] = handler
        
        # 挂载到根 logger，这样所有子 logger 的日志都会传播过来
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        # 确保根 logger 的级别不会阻断日志传播
        if root_logger.level > logging.DEBUG:
            root_logger.setLevel(logging.DEBUG)
        
        logger.debug(f"已为设备 {device_name} [{device_address}] 创建日志选项卡")

    def remove_device_tab(self, device_address: str):
        """移除设备的日志选项卡
        
        Args:
            device_address: 设备地址
        """
        if device_address not in self._device_tabs:
            return
        
        # 从根 logger 移除日志处理器
        if device_address in self._log_handlers:
            handler = self._log_handlers[device_address]
            root_logger = logging.getLogger()
            root_logger.removeHandler(handler)
            del self._log_handlers[device_address]
        
        # 找到并移除选项卡
        for i in range(self._tab_widget.count()):
            if self._tab_widget.tabToolTip(i) == device_address:
                self._tab_widget.removeTab(i)
                break
        
        # 移除引用
        del self._device_tabs[device_address]
        
        logger.info(f"已移除设备 [{device_address}] 的日志选项卡")

    def _on_tab_closed(self, index: int):
        """选项卡关闭处理"""
        device_address = self._tab_widget.tabToolTip(index)
        if device_address and device_address != "global":
            self.remove_device_tab(device_address)
            self.device_tab_closed.emit(device_address)

    def _on_tab_changed(self, index: int):
        """选项卡切换处理"""
        if index >= 0:
            self._current_device = self._tab_widget.tabToolTip(index)

    def _on_level_changed(self, text: str):
        """日志级别下拉框变化处理"""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
        }
        self._min_level = level_map.get(text, logging.INFO)

    def _append_log(self, message: str, level: int, device_address: str = None):
        """追加日志到对应设备的文本框
        
        Args:
            message: 日志消息
            level: 日志级别
            device_address: 设备地址，None/"global" 表示全局日志
        """
        # 根据下拉框选择的最小级别过滤
        if level < self._min_level:
            return
        
        # 根据级别设置颜色
        color_map = {
            logging.DEBUG: '#808080',      # 灰色
            logging.INFO: '#4ec9b0',       # 青色
            logging.WARNING: '#dcdcaa',    # 黄色
            logging.ERROR: '#f44747',      # 红色
            logging.CRITICAL: '#ff0000',   # 亮红
        }
        color = color_map.get(level, '#d4d4d4')
        
        # 格式化 HTML
        html_msg = f'<span style="color: {color};">{message}</span><br>'
        
        is_global = (device_address is None or device_address == "global")
        
        if is_global:
            # 全局日志：直接写入全局选项卡
            if "global" in self._device_tabs:
                global_log = self._device_tabs["global"]
                global_log.insertHtml(html_msg)
                self._scroll_to_bottom(global_log)
                self._limit_logs(global_log)
        else:
            # 设备日志：写入设备选项卡
            if device_address in self._device_tabs:
                log_text = self._device_tabs[device_address]
                log_text.insertHtml(html_msg)
                self._scroll_to_bottom(log_text)
                self._limit_logs(log_text)
            
            # 同时写入全局选项卡（带设备前缀）
            if "global" in self._device_tabs:
                global_log = self._device_tabs["global"]
                device_prefix = f'<span style="color: #569cd6;">[{device_address}]</span> '
                html_msg_with_prefix = device_prefix + html_msg
                global_log.insertHtml(html_msg_with_prefix)
                self._scroll_to_bottom(global_log)
                self._limit_logs(global_log)

    def _scroll_to_bottom(self, log_text: QTextEdit):
        """滚动到底部"""
        cursor = log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        log_text.setTextCursor(cursor)

    def _limit_logs(self, log_text: QTextEdit, max_lines: int = 1000):
        """限制日志行数，避免内存溢出"""
        doc = log_text.document()
        if doc.blockCount() > max_lines:
            log_text.clear()

    def _clear_current_device_logs(self):
        """清除当前选中设备的日志"""
        current_index = self._tab_widget.currentIndex()
        if current_index >= 0:
            widget = self._tab_widget.widget(current_index)
            if isinstance(widget, QTextEdit):
                widget.clear()

    def clear_all_logs(self):
        """清空所有日志"""
        for log_text in self._device_tabs.values():
            log_text.clear()

    def setup_logger_for_device(self, device_address: str, device_name: str = None, level=logging.INFO):
        """为指定设备设置日志监听
        
        Args:
            device_address: 设备地址
            device_name: 设备名称（用于选项卡显示），默认为设备地址
            level: 日志级别
        """
        if device_name is None:
            device_name = device_address
        
        self._add_device_tab(device_name, device_address)
        
        # 更新日志级别
        if device_address in self._log_handlers:
            self._log_handlers[device_address].setLevel(level)
class LogViewer(QWidget):
    """实时日志查看器，显示程序运行日志（单设备模式）
    
    注意：多设备场景请使用 MultiDeviceLogViewer
    """
    
    # 日志信号
    log_received = pyqtSignal(str, int)  # message, level

    def __init__(self, parent=None):
        """初始化日志查看器

        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        self._log_handler = None
        self._min_level: int = logging.INFO  # 当前最小显示级别
        self._init_ui()
        
        # 连接信号
        self.log_received.connect(self._append_log)

    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        # 日志级别选择
        level_label = QLabel("级别:")
        level_label.setStyleSheet("color: #d4d4d4;")
        toolbar.addWidget(level_label)
        
        self._level_combo = QComboBox()
        self._level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self._level_combo.setCurrentText("INFO")
        self._level_combo.setToolTip("选择最小日志显示级别")
        self._level_combo.setStyleSheet("""
            QComboBox {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                padding: 2px 8px;
                min-width: 80px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #3c3c3c;
                color: #d4d4d4;
                selection-background-color: #094771;
            }
        """)
        self._level_combo.currentTextChanged.connect(self._on_level_changed)
        toolbar.addWidget(self._level_combo)
        
        toolbar.addStretch()
        
        clear_btn = QPushButton("清除")
        clear_btn.clicked.connect(self.clear_logs)
        toolbar.addWidget(clear_btn)
        
        layout.addLayout(toolbar)
        
        # 日志文本框
        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setStyleSheet("""
            QTextEdit {
                font-family: Consolas, 'Courier New', monospace;
                font-size: 12px;
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
        """)
        layout.addWidget(self._log_text)
    
    def setup_logger(self, logger_name=None, level=logging.INFO):
        """设置日志监听
        
        Args:
            logger_name: 要监听的 logger 名称，None 表示根 logger
            level: 日志级别
        """
        # 移除旧的 handler
        if self._log_handler:
            target_logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()
            target_logger.removeHandler(self._log_handler)
        
        # 创建新的 handler（过滤第三方库日志）
        self._log_handler = LogHandler(
            self.log_received,
            allowed_prefixes=LogHandler.APP_LOGGER_PREFIXES,
        )
        self._log_handler.setLevel(level)
        
        # 添加到 logger
        target_logger = logging.getLogger(logger_name) if logger_name else logging.getLogger()
        target_logger.addHandler(self._log_handler)
        target_logger.setLevel(min(target_logger.level, level))

    def _on_level_changed(self, text: str):
        """日志级别下拉框变化处理"""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
        }
        self._min_level = level_map.get(text, logging.INFO)

    def append_log(self, level: str, message: str, timestamp: str = None):
        """追加一条日志

        Args:
            level: 日志级别（DEBUG, INFO, WARNING, ERROR）
            message: 日志内容
            timestamp: 时间戳（可选）
        """
        level_num = getattr(logging, level.upper(), logging.INFO)
        ts = timestamp or datetime.now().strftime('%H:%M:%S')
        formatted = f"{ts} | {level.upper():7s} | {message}"
        self._append_log(formatted, level_num)

    def _append_log(self, message: str, level: int):
        """追加日志到文本框
        
        Args:
            message: 日志消息
            level: 日志级别
        """
        # 根据下拉框选择的最小级别过滤
        if level < self._min_level:
            return
        
        # 根据级别设置颜色
        color_map = {
            logging.DEBUG: '#808080',      # 灰色
            logging.INFO: '#4ec9b0',       # 青色
            logging.WARNING: '#dcdcaa',    # 黄色
            logging.ERROR: '#f44747',      # 红色
            logging.CRITICAL: '#ff0000',   # 亮红
        }
        color = color_map.get(level, '#d4d4d4')
        
        # 格式化 HTML
        html_msg = f'<span style="color: {color};">{message}</span><br>'
        
        # 追加到文本框
        self._log_text.insertHtml(html_msg)
        
        # 自动滚动到底部
        cursor = self._log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._log_text.setTextCursor(cursor)
        
        # 限制日志行数，避免内存溢出
        doc = self._log_text.document()
        if doc.blockCount() > 1000:
            self._log_text.clear()
    
    def clear_logs(self):
        """清空所有日志"""
        self._log_text.clear()

    def search_logs(self, keyword: str):
        """搜索日志内容

        Args:
            keyword: 搜索关键词
        """
        # TODO: 高亮匹配的日志条目
        pass

    def export_logs(self, file_path: str):
        """导出日志到文件

        Args:
            file_path: 导出文件路径
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self._log_text.toPlainText())
        except Exception as e:
            logging.error(f"导出日志失败: {e}")
