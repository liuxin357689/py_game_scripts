"""
截图对话框

提供可视化截图 + 裁剪 + 坐标标记功能：
    - 从 ADB 设备截取画面
    - 鼠标框选裁剪区域（橡皮筋选框）
    - 实时显示选区坐标和尺寸
    - 手动输入坐标或点击拾取，在截图上标记位置
    - 保存全图 / 保存裁剪区域
    - 复制裁剪区域到剪贴板
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional, Tuple

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import (
    QImage, QPixmap, QPainter, QPen, QColor, QFont,
    QAction, QKeySequence,
)
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QFileDialog, QMessageBox,
    QScrollArea, QSplitter, QStatusBar, QApplication,
    QSpinBox, QFormLayout, QWidget, QInputDialog,
    QListWidget, QListWidgetItem,
)

logger = logging.getLogger(__name__)


# ---- 标记颜色列表（循环使用）----
_MARKER_COLORS = [
    QColor(255, 68, 68),     # 红
    QColor(68, 170, 255),    # 蓝
    QColor(68, 221, 119),    # 绿
    QColor(255, 204, 68),    # 黄
    QColor(170, 102, 255),   # 紫
    QColor(255, 136, 68),    # 橙
    QColor(68, 221, 221),    # 青
    QColor(255, 102, 170),   # 粉
]


class _ScreenshotCanvas(QWidget):
    """截图画布：显示图像 + 鼠标框选裁剪区域 + 坐标标记"""

    # 选区变更信号: (x1, y1, x2, y2) 原始图像坐标
    selection_changed = pyqtSignal(int, int, int, int)
    selection_cleared = pyqtSignal()
    # 标记添加信号: (x, y) 原始图像坐标
    marker_added = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._image_size = (0, 0)  # 原始图像 (w, h)

        # 选框状态（画布坐标系）
        self._selecting = False
        self._sel_start = QPoint()
        self._sel_end = QPoint()
        self._sel_rect = QRect()  # 当前选框（画布坐标）

        # 坐标标记（原始图像坐标）
        self._markers: list[tuple[int, int]] = []

        # 拾取模式：点击画布添加标记
        self._pick_mode = False

        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_image(self, pixmap: QPixmap, original_size: Tuple[int, int]):
        """设置要显示的图像

        Args:
            pixmap: 图像
            original_size: 原始图像尺寸 (w, h)，用于坐标换算
        """
        self._pixmap = pixmap
        self._image_size = original_size
        self._sel_rect = QRect()
        self._markers.clear()
        self._update_size()
        self.update()

    def _update_size(self):
        """根据图像调整画布大小"""
        if self._pixmap:
            self.setFixedSize(self._pixmap.size())
        else:
            self.setFixedSize(320, 240)

    # ---- 标记管理 ----

    def add_marker(self, x: int, y: int):
        """添加坐标标记（原始图像坐标）"""
        self._markers.append((x, y))
        self.update()

    def set_markers(self, markers: list[tuple[int, int]]):
        """批量设置标记"""
        self._markers = list(markers)
        self.update()

    def get_markers(self) -> list[tuple[int, int]]:
        """获取所有标记"""
        return list(self._markers)

    def marker_count(self) -> int:
        return len(self._markers)

    def clear_markers(self):
        """清除所有标记"""
        self._markers.clear()
        self.update()

    def set_pick_mode(self, enabled: bool):
        """开关拾取模式（点击画布添加标记）"""
        self._pick_mode = enabled

    # ---- 选区 ----

    def get_selection(self) -> Optional[Tuple[int, int, int, int]]:
        """获取当前选区（原始图像坐标）

        Returns:
            (x1, y1, x2, y2) 或 None（无选区）
        """
        if self._sel_rect.isNull() or self._sel_rect.isEmpty():
            return None

        if not self._pixmap:
            return None

        # 画布坐标 -> 原始图像坐标
        pw, ph = self._pixmap.width(), self._pixmap.height()
        iw, ih = self._image_size

        if pw == 0 or ph == 0:
            return None

        sx = iw / pw
        sy = ih / ph

        r = self._sel_rect.normalized()
        x1 = int(r.left() * sx)
        y1 = int(r.top() * sy)
        x2 = int(r.right() * sx)
        y2 = int(r.bottom() * sy)

        # 边界钳制
        x1 = max(0, min(x1, iw - 1))
        y1 = max(0, min(y1, ih - 1))
        x2 = max(0, min(x2, iw))
        y2 = max(0, min(y2, ih))

        if x2 <= x1 or y2 <= y1:
            return None

        return (x1, y1, x2, y2)

    def clear_selection(self):
        """清除选区"""
        self._sel_rect = QRect()
        self.selection_cleared.emit()
        self.update()

    # ---- 坐标换算 ----

    def _canvas_to_image(self, cx: int, cy: int) -> tuple[int, int]:
        """画布坐标 → 原始图像坐标"""
        if not self._pixmap:
            return (cx, cy)
        pw, ph = self._pixmap.width(), self._pixmap.height()
        iw, ih = self._image_size
        if pw == 0 or ph == 0:
            return (cx, cy)
        ix = int(cx * (iw / pw))
        iy = int(cy * (ih / ph))
        ix = max(0, min(ix, iw - 1))
        iy = max(0, min(iy, ih - 1))
        return (ix, iy)

    def _image_to_canvas(self, ix: int, iy: int) -> tuple[int, int]:
        """原始图像坐标 → 画布坐标"""
        if not self._pixmap:
            return (ix, iy)
        pw, ph = self._pixmap.width(), self._pixmap.height()
        iw, ih = self._image_size
        if iw == 0 or ih == 0:
            return (ix, iy)
        cx = int(ix * (pw / iw))
        cy = int(iy * (ph / ih))
        return (cx, cy)

    # ---- 绘制 ----

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # 背景
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        if self._pixmap:
            painter.drawPixmap(0, 0, self._pixmap)

            # 半透明遮罩（选区外变暗）
            if not self._sel_rect.isNull() and not self._sel_rect.isEmpty():
                r = self._sel_rect.normalized()
                # 遮罩
                overlay = QColor(0, 0, 0, 100)
                full = self.rect()
                # 上方
                painter.fillRect(
                    full.left(), full.top(), full.width(), r.top(), overlay
                )
                # 下方
                painter.fillRect(
                    full.left(), r.bottom(),
                    full.width(), full.bottom() - r.bottom(), overlay
                )
                # 左方
                painter.fillRect(
                    full.left(), r.top(),
                    r.left() - full.left(), r.height(), overlay
                )
                # 右方
                painter.fillRect(
                    r.right(), r.top(),
                    full.right() - r.right(), r.height(), overlay
                )

                # 选框边框
                pen = QPen(QColor(0, 180, 255), 2, Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawRect(r)

                # 四角手柄
                handle_size = 6
                handle_color = QColor(0, 180, 255)
                painter.setBrush(handle_color)
                painter.setPen(Qt.PenStyle.NoPen)
                corners = [
                    r.topLeft(), r.topRight(),
                    r.bottomLeft(), r.bottomRight(),
                ]
                for c in corners:
                    painter.drawRect(
                        c.x() - handle_size // 2,
                        c.y() - handle_size // 2,
                        handle_size, handle_size,
                    )

            # ---- 坐标标记 ----
            font = QFont("Consolas", 9)
            font.setBold(True)
            painter.setFont(font)

            for i, (mx, my) in enumerate(self._markers):
                cx, cy = self._image_to_canvas(mx, my)
                color = _MARKER_COLORS[i % len(_MARKER_COLORS)]

                # 十字准星
                cross_pen = QPen(color, 2)
                painter.setPen(cross_pen)
                size = 12
                painter.drawLine(
                    QPoint(cx - size, cy), QPoint(cx + size, cy)
                )
                painter.drawLine(
                    QPoint(cx, cy - size), QPoint(cx, cy + size)
                )

                # 中心圆点
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(QPoint(cx, cy), 4, 4)

                # 外圈
                ring_pen = QPen(color, 2)
                painter.setPen(ring_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPoint(cx, cy), 8, 8)

                # 标签
                label = f"({mx}, {my})"
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(label)

                # 默认在标记右上方
                lx = cx + 14
                ly = cy - 8
                # 右侧溢出则翻到左边
                if lx + tw > self.width():
                    lx = cx - 14 - tw
                # 上方溢出则翻到下面
                if ly - fm.ascent() < 0:
                    ly = cy + 18

                # 标签背景
                bg_rect = QRect(
                    lx - 3,
                    ly - fm.ascent() - 2,
                    tw + 6,
                    fm.height() + 4,
                )
                bg_color = QColor(color)
                bg_color.setAlpha(180)
                painter.fillRect(bg_rect, bg_color)

                # 标签文字
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(lx, ly, label)

        painter.end()

    # ---- 鼠标事件 ----

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._pixmap:
            if self._pick_mode:
                # 拾取模式：点击添加标记
                pos = event.position().toPoint()
                pw, ph = self._pixmap.width(), self._pixmap.height()
                x = max(0, min(pos.x(), pw - 1))
                y = max(0, min(pos.y(), ph - 1))
                ix, iy = self._canvas_to_image(x, y)
                self.add_marker(ix, iy)
                self.marker_added.emit(ix, iy)
            else:
                # 正常模式：开始框选
                self._selecting = True
                self._sel_start = event.position().toPoint()
                self._sel_end = self._sel_start
                self._sel_rect = QRect()
                self.update()

    def mouseMoveEvent(self, event):
        if self._selecting and self._pixmap and not self._pick_mode:
            self._sel_end = event.position().toPoint()
            # 限制在图像范围内
            pw, ph = self._pixmap.width(), self._pixmap.height()
            x = max(0, min(self._sel_end.x(), pw))
            y = max(0, min(self._sel_end.y(), ph))
            self._sel_end = QPoint(x, y)
            self._sel_rect = QRect(self._sel_start, self._sel_end).normalized()
            self.update()

            # 发射信号
            sel = self.get_selection()
            if sel:
                self.selection_changed.emit(*sel)

    def mouseReleaseEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._selecting
            and not self._pick_mode
        ):
            self._selecting = False
            self._sel_rect = QRect(self._sel_start, self._sel_end).normalized()
            # 太小的选区视为误触，清除
            if self._sel_rect.width() < 5 or self._sel_rect.height() < 5:
                self._sel_rect = QRect()
                self.selection_cleared.emit()
            self.update()

            sel = self.get_selection()
            if sel:
                self.selection_changed.emit(*sel)

    def contextMenuEvent(self, event):
        """右键菜单"""
        if self._markers:
            from PyQt6.QtWidgets import QMenu
            menu = QMenu(self)
            action = menu.addAction("清除所有标记")
            chosen = menu.exec(event.globalPosition().toPoint())
            if chosen == action:
                self.clear_markers()

    def mouseDoubleClickEvent(self, event):
        """双击清除选区"""
        self.clear_selection()


class ScreenshotDialog(QDialog):
    """截图对话框：可视化截图 + 框选裁剪 + 坐标标记 + 保存"""

    def __init__(self, device, save_dir: str = None, parent=None):
        """
        Args:
            device: ADBDevice 实例（已连接）
            save_dir: 默认保存目录
            parent: 父窗口
        """
        super().__init__(parent)
        self._device = device
        self._markers: list[tuple[int, int]] = []

        from game_platform.screenshot.manager import ScreenshotManager, DEFAULT_SAVE_DIR
        self._manager = ScreenshotManager(device, save_dir or DEFAULT_SAVE_DIR)
        # 模板图片 + templates.json 统一存放在 game_platform/screenshot/templates/
        self._templates_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "templates"
        )
        self._current_image: Optional[np.ndarray] = None  # OpenCV BGR

        self.setWindowTitle("ADB 截图工具")
        self.setMinimumSize(900, 600)
        self._init_ui()

    def _init_ui(self):
        """初始化界面"""
        main_layout = QHBoxLayout(self)

        # ---- 左侧：截图画布（可滚动） ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { background-color: #1e1e1e; }")

        self._canvas = _ScreenshotCanvas()
        self._canvas.selection_changed.connect(self._on_selection_changed)
        self._canvas.selection_cleared.connect(self._on_selection_cleared)
        self._canvas.marker_added.connect(self._on_canvas_marker_added)
        scroll.setWidget(self._canvas)

        # ---- 右侧：控制面板 ----
        right_panel = QWidget()
        right_panel.setFixedWidth(280)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)

        # 操作按钮组
        action_group = QGroupBox("操作")
        action_layout = QVBoxLayout(action_group)

        self._btn_capture = QPushButton("截取屏幕")
        self._btn_capture.setShortcut(QKeySequence("F5"))
        self._btn_capture.setStyleSheet(
            "QPushButton { padding: 8px; font-weight: bold; }"
        )
        self._btn_capture.clicked.connect(self._do_capture)
        action_layout.addWidget(self._btn_capture)

        self._btn_save_full = QPushButton("保存全图 (Ctrl+S)")
        self._btn_save_full.setShortcut(QKeySequence("Ctrl+S"))
        self._btn_save_full.setEnabled(False)
        self._btn_save_full.clicked.connect(self._do_save_full)
        action_layout.addWidget(self._btn_save_full)

        self._btn_save_crop = QPushButton("保存裁剪区域 (Ctrl+Shift+S)")
        self._btn_save_crop.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._btn_save_crop.setEnabled(False)
        self._btn_save_crop.clicked.connect(self._do_save_crop)
        action_layout.addWidget(self._btn_save_crop)

        self._btn_copy = QPushButton("复制裁剪区域到剪贴板 (Ctrl+C)")
        self._btn_copy.setShortcut(QKeySequence("Ctrl+C"))
        self._btn_copy.setEnabled(False)
        self._btn_copy.clicked.connect(self._do_copy_crop)
        action_layout.addWidget(self._btn_copy)

        self._btn_clear_sel = QPushButton("清除选区 (Esc)")
        self._btn_clear_sel.setEnabled(False)
        self._btn_clear_sel.clicked.connect(self._canvas.clear_selection)
        action_layout.addWidget(self._btn_clear_sel)

        right_layout.addWidget(action_group)

        # 选区信息组
        info_group = QGroupBox("选区信息")
        info_layout = QFormLayout(info_group)

        self._lbl_coord = QLabel("---")
        self._lbl_coord.setStyleSheet("font-family: Consolas, monospace;")
        info_layout.addRow("坐标:", self._lbl_coord)

        self._lbl_size = QLabel("---")
        self._lbl_size.setStyleSheet("font-family: Consolas, monospace;")
        info_layout.addRow("尺寸:", self._lbl_size)

        self._lbl_img_size = QLabel("---")
        self._lbl_img_size.setStyleSheet("font-family: Consolas, monospace;")
        info_layout.addRow("原图:", self._lbl_img_size)

        right_layout.addWidget(info_group)

        # ---- 坐标标记组 ----
        marker_group = QGroupBox("坐标标记")
        marker_layout = QVBoxLayout(marker_group)

        # 坐标输入行
        coord_row = QHBoxLayout()
        coord_row.addWidget(QLabel("X:"))
        self._spin_x = QSpinBox()
        self._spin_x.setRange(0, 9999)
        self._spin_x.setStyleSheet("font-family: Consolas, monospace;")
        coord_row.addWidget(self._spin_x)

        coord_row.addWidget(QLabel("Y:"))
        self._spin_y = QSpinBox()
        self._spin_y.setRange(0, 9999)
        self._spin_y.setStyleSheet("font-family: Consolas, monospace;")
        coord_row.addWidget(self._spin_y)
        marker_layout.addLayout(coord_row)

        # 操作按钮
        btn_row = QHBoxLayout()
        self._btn_add_marker = QPushButton("添加")
        self._btn_add_marker.setEnabled(False)
        self._btn_add_marker.clicked.connect(self._do_add_marker)
        btn_row.addWidget(self._btn_add_marker)

        self._btn_pick_mode = QPushButton("拾取模式")
        self._btn_pick_mode.setCheckable(True)
        self._btn_pick_mode.setEnabled(False)
        self._btn_pick_mode.toggled.connect(self._do_toggle_pick_mode)
        btn_row.addWidget(self._btn_pick_mode)
        marker_layout.addLayout(btn_row)

        # 标记列表
        self._marker_list = QListWidget()
        self._marker_list.setMaximumHeight(120)
        self._marker_list.setStyleSheet("font-family: Consolas, monospace;")
        marker_layout.addWidget(self._marker_list)

        self._btn_clear_markers = QPushButton("清除所有标记")
        self._btn_clear_markers.setEnabled(False)
        self._btn_clear_markers.clicked.connect(self._do_clear_markers)
        marker_layout.addWidget(self._btn_clear_markers)

        right_layout.addWidget(marker_group)

        # 裁剪预览组
        preview_group = QGroupBox("裁剪预览")
        preview_layout = QVBoxLayout(preview_group)

        self._preview_label = QLabel("暂无选区")
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setFixedSize(240, 160)
        self._preview_label.setStyleSheet(
            "QLabel { background-color: #2d2d2d; color: #888; border: 1px solid #555; }"
        )
        preview_layout.addWidget(self._preview_label)

        right_layout.addWidget(preview_group)

        # 保存目录
        dir_group = QGroupBox("保存目录")
        dir_layout = QVBoxLayout(dir_group)

        self._lbl_dir = QLabel(self._manager.save_dir)
        self._lbl_dir.setWordWrap(True)
        self._lbl_dir.setStyleSheet("font-size: 11px; color: #aaa;")
        dir_layout.addWidget(self._lbl_dir)

        btn_change_dir = QPushButton("更改目录...")
        btn_change_dir.clicked.connect(self._do_change_dir)
        dir_layout.addWidget(btn_change_dir)

        right_layout.addWidget(dir_group)

        right_layout.addStretch()

        # ---- 组装 ----
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(scroll)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        main_layout.addWidget(splitter)

        # 底部状态栏
        self._status = QStatusBar()
        self._status.showMessage("点击「截取屏幕」开始")
        main_layout.addWidget(self._status)

    # ---- 截图操作 ----

    def _do_capture(self):
        """执行截图"""
        try:
            self._btn_capture.setEnabled(False)
            self._btn_capture.setText("截图中...")
            QApplication.processEvents()

            img = self._manager.capture()
            self._current_image = img

            # 重置标记
            self._markers.clear()
            self._marker_list.clear()
            self._update_marker_buttons()

            # 转为 QPixmap 显示
            pixmap = self._cv_to_pixmap(img)
            h, w = img.shape[:2]
            self._canvas.set_image(pixmap, (w, h))

            # 更新坐标输入框范围
            self._spin_x.setRange(0, w - 1)
            self._spin_y.setRange(0, h - 1)

            # 更新 UI 状态
            self._btn_save_full.setEnabled(True)
            self._btn_save_crop.setEnabled(False)
            self._btn_copy.setEnabled(False)
            self._btn_clear_sel.setEnabled(False)
            self._btn_add_marker.setEnabled(True)
            self._btn_pick_mode.setEnabled(True)
            self._lbl_img_size.setText(f"{w} x {h}")
            self._on_selection_cleared()

            self._status.showMessage(
                f"截图成功: {w}x{h}", 5000
            )

        except Exception as e:
            logger.error(f"截图失败: {e}", exc_info=True)
            QMessageBox.warning(self, "截图失败", str(e))
        finally:
            self._btn_capture.setEnabled(True)
            self._btn_capture.setText("截取屏幕 (F5)")

    def _do_save_full(self):
        """保存全图"""
        if self._current_image is None:
            return

        try:
            path = self._manager.save(self._current_image)
            self._status.showMessage(f"全图已保存: {os.path.basename(path)}", 5000)
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _do_save_crop(self):
        """保存裁剪区域：弹出文件名输入框 -> 保存到 templates 目录 -> 追加 templates.json"""
        sel = self._canvas.get_selection()
        if sel is None or self._current_image is None:
            return

        # 弹出文件名输入框
        filename, ok = QInputDialog.getText(
            self, "保存模板图片",
            "请输入文件名（不含扩展名）：",
        )
        if not ok or not filename.strip():
            return
        filename = filename.strip()
        if not filename.endswith(".png"):
            filename += ".png"

        try:
            x1, y1, x2, y2 = sel
            cropped = self._manager.crop(self._current_image, x1, y1, x2, y2)
            crop_h, crop_w = cropped.shape[:2]
            orig_h, orig_w = self._current_image.shape[:2]

            # ---- templates 目录（始终使用 game_platform/screenshot/templates）----
            tpl_dir = self._templates_dir
            os.makedirs(tpl_dir, exist_ok=True)

            # ---- 保存图片 ----
            filepath = os.path.join(tpl_dir, filename)
            success, buf = cv2.imencode(".png", cropped)
            if not success:
                raise RuntimeError("PNG 编码失败")
            with open(filepath, "wb") as f:
                f.write(buf.tobytes())

            # ---- 采集关键点 RGB（BGR->RGB）----
            key_points = {
                "top_left":     (0, 0),
                "top_right":    (crop_w - 1, 0),
                "bottom_left":  (0, crop_h - 1),
                "bottom_right": (crop_w - 1, crop_h - 1),
                "center":       (crop_w // 2, crop_h // 2),
            }
            colors = {}
            for name, (cx, cy) in key_points.items():
                b, g, r = cropped[cy, cx]
                colors[name] = {"x": cx, "y": cy, "rgb": [int(r), int(g), int(b)]}

            # ---- 检查是否重名：覆盖图片和 JSON 条目 ----
            json_path = os.path.join(tpl_dir, "templates.json")
            entries = []
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        entries = json.load(f)
                except (json.JSONDecodeError, IOError):
                    entries = []

            new_entry = {
                "image_file": filename,
                "timestamp": datetime.now().isoformat(),
                "original_size": {"width": orig_w, "height": orig_h},
                "crop_region": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                "crop_size": {"width": crop_w, "height": crop_h},
                "key_colors": colors,
            }

            # 查找是否有同名条目（重名 → 替换；否则 → 追加）
            existing_idx = None
            for i, entry in enumerate(entries):
                if entry.get("image_file") == filename:
                    existing_idx = i
                    break

            if existing_idx is not None:
                entries[existing_idx] = new_entry
                self._status.showMessage(
                    f"[覆盖] {filename} 已更新，JSON 条目已替换",
                    5000,
                )
            else:
                entries.append(new_entry)
                self._status.showMessage(
                    f"模板已保存: {filename} ({crop_w}x{crop_h}) -> templates.json",
                    5000,
                )

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存模板失败: {e}", exc_info=True)
            QMessageBox.warning(self, "保存失败", str(e))

    def _do_copy_crop(self):
        """复制裁剪区域到剪贴板"""
        sel = self._canvas.get_selection()
        if sel is None or self._current_image is None:
            return

        cropped = self._manager.crop(self._current_image, *sel)
        h, w = cropped.shape[:2]
        rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(qimg)

        clipboard = QApplication.clipboard()
        clipboard.setPixmap(pixmap)

        self._status.showMessage(
            f"已复制裁剪区域到剪贴板 ({w}x{h})", 5000
        )

    def _do_change_dir(self):
        """更改保存目录"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择保存目录", self._manager.save_dir
        )
        if dir_path:
            self._manager.save_dir = dir_path
            self._lbl_dir.setText(dir_path)

    # ---- 坐标标记 ----

    def _do_add_marker(self):
        """从输入框添加坐标标记"""
        if self._current_image is None:
            return

        x = self._spin_x.value()
        y = self._spin_y.value()

        h, w = self._current_image.shape[:2]
        if x >= w or y >= h:
            self._status.showMessage(
                f"坐标 ({x}, {y}) 超出图像范围 ({w}x{h})", 3000
            )
            return

        self._markers.append((x, y))
        self._canvas.add_marker(x, y)
        self._refresh_marker_list()
        self._status.showMessage(f"已添加标记: ({x}, {y})", 3000)

    def _do_toggle_pick_mode(self, checked: bool):
        """切换拾取模式"""
        self._canvas.set_pick_mode(checked)
        if checked:
            self._btn_pick_mode.setText("拾取中... (点击取消)")
            self._btn_pick_mode.setStyleSheet(
                "QPushButton { background-color: #4a90d9; color: white; }"
            )
            self._status.showMessage(
                "拾取模式已开启 - 在截图上点击添加坐标标记", 5000
            )
        else:
            self._btn_pick_mode.setText("拾取模式")
            self._btn_pick_mode.setStyleSheet("")
            self._status.showMessage("拾取模式已关闭", 3000)

    def _do_clear_markers(self):
        """清除所有标记"""
        self._markers.clear()
        self._canvas.clear_markers()
        self._refresh_marker_list()
        self._status.showMessage("已清除所有标记", 3000)

    def _on_canvas_marker_added(self, x: int, y: int):
        """画布拾取模式添加标记回调"""
        self._markers.append((x, y))
        self._refresh_marker_list()
        self._status.showMessage(f"拾取标记: ({x}, {y})", 3000)

    def _refresh_marker_list(self):
        """刷新标记列表显示"""
        self._marker_list.clear()
        for i, (x, y) in enumerate(self._markers):
            item = QListWidgetItem(f"  #{i + 1}  ({x}, {y})")
            self._marker_list.addItem(item)
        self._update_marker_buttons()

    def _update_marker_buttons(self):
        """更新标记相关按钮状态"""
        has_markers = len(self._markers) > 0
        self._btn_clear_markers.setEnabled(has_markers)

    # ---- 选区事件 ----

    def _on_selection_changed(self, x1: int, y1: int, x2: int, y2: int):
        """选区变更"""
        w, h = x2 - x1, y2 - y1
        self._lbl_coord.setText(f"({x1}, {y1}) - ({x2}, {y2})")
        self._lbl_size.setText(f"{w} x {h}")
        self._btn_save_crop.setEnabled(True)
        self._btn_copy.setEnabled(True)
        self._btn_clear_sel.setEnabled(True)

        # 更新裁剪预览
        if self._current_image is not None and w > 0 and h > 0:
            cropped = self._manager.crop(self._current_image, x1, y1, x2, y2)
            preview = self._cv_to_pixmap(cropped)
            # 缩放到预览框大小
            scaled = preview.scaled(
                self._preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._preview_label.setPixmap(scaled)
            self._preview_label.setText("")

    def _on_selection_cleared(self):
        """选区清除"""
        self._lbl_coord.setText("---")
        self._lbl_size.setText("---")
        self._btn_save_crop.setEnabled(False)
        self._btn_copy.setEnabled(False)
        self._btn_clear_sel.setEnabled(False)
        self._preview_label.clear()
        self._preview_label.setText("暂无选区")

    # ---- 工具方法 ----

    @staticmethod
    def _cv_to_pixmap(img: np.ndarray) -> QPixmap:
        """OpenCV BGR 图像转 QPixmap"""
        h, w = img.shape[:2]
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        return QPixmap.fromImage(qimg)

    def keyPressEvent(self, event):
        """键盘快捷键"""
        if event.key() == Qt.Key.Key_Escape:
            # Esc: 如果拾取模式开着就关闭拾取，否则清除选区
            if self._btn_pick_mode.isChecked():
                self._btn_pick_mode.setChecked(False)
            else:
                self._canvas.clear_selection()
        else:
            super().keyPressEvent(event)
