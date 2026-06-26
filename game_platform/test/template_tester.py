"""
通用模板 / 坐标识别可视化测试工具

读取 templates.json + 模板图片，对模拟器实时截图执行：
    1. 模板匹配（cv2.matchTemplate）— 找到最佳匹配位置和置信度
    2. 像素颜色检测 — 在 crop_region 位置逐个检查 key_colors 采样点

结果全部标注在截图上并保存，控制台输出汇总表。

用法:
    # 实时截图（默认 localhost:5555）
    python -m game_platform.test.template_tester

    # 指定设备
    python -m game_platform.test.template_tester --host 127.0.0.1 --port 5556

    # 使用本地图片（不连 ADB）
    python -m game_platform.test.template_tester --image path/to/screen.png

    # 只测试指定模板（逗号分隔文件名）
    python -m game_platform.test.template_tester --only replace_btn.png,zdsb.png

    # 循环模式：每隔 N 秒截一次图
    python -m game_platform.test.template_tester --loop 5

    # 自定义模板目录和 json
    python -m game_platform.test.template_tester --dir path/to/templates

    # 调整匹配阈值和像素容差
    python -m game_platform.test.template_tester --threshold 0.6 --tolerance 50
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np


# ---- 数据结构 ----

@dataclass
class KeyColor:
    """采样点"""
    name: str
    rel_x: int          # 相对于 crop_region 左上角
    rel_y: int
    expected_rgb: Tuple[int, int, int]


@dataclass
class TemplateEntry:
    """templates.json 中的一条记录"""
    image_file: str
    crop_region: dict          # {x1, y1, x2, y2}
    crop_size: dict            # {width, height}
    center: Tuple[int, int]    # crop_region 中心
    key_colors: List[KeyColor]
    template_img: Optional[np.ndarray] = None  # 加载后的模板图片


@dataclass
class MatchResult:
    """单个模板的检测结果"""
    image_file: str
    # 模板匹配
    tm_confidence: float = 0.0           # 最佳匹配置信度
    tm_location: Tuple[int, int] = (0, 0)  # 最佳匹配左上角
    tm_center: Tuple[int, int] = (0, 0)    # 最佳匹配中心
    tm_passed: bool = False
    tm_brightness: float = 0.0           # 匹配区域 HSV V 通道平均亮度
    tm_saturation: float = 0.0           # 匹配区域 HSV S 通道平均饱和度
    # 像素检测
    pixel_total: int = 0
    pixel_passed: int = 0
    pixel_results: list = field(default_factory=list)  # [(name, abs_pos, expected, actual, ok)]
    pixel_all_ok: bool = False
    # crop_region 原始位置（用于画图）
    crop_region: dict = field(default_factory=dict)


# ---- 核心类 ----

class TemplateTester:
    """通用模板 / 坐标识别测试器"""

    # 标注颜色 (BGR)
    _COLOR_CROP_RECT = (0, 200, 0)       # 绿色 — crop_region 原始位置
    _COLOR_TM_MATCH = (255, 165, 0)       # 橙色 — 模板匹配最佳位置
    _COLOR_TM_HIGH = (0, 220, 0)          # 亮绿 — 高置信度匹配
    _COLOR_PIXEL_PASS = (0, 220, 0)       # 绿色 — 像素检测通过
    _COLOR_PIXEL_FAIL = (0, 0, 240)       # 红色 — 像素检测失败
    _COLOR_CENTER = (255, 255, 0)         # 青色 — 中心十字

    def __init__(
        self,
        templates_dir: str,
        threshold: float = 0.7,
        tolerance: int = 40,
        min_brightness: int = 0,
        min_saturation: int = 0,
    ):
        """
        Args:
            templates_dir: 模板目录（包含 templates.json 和 .png 文件）
            threshold: 模板匹配置信度阈值
            tolerance: 像素颜色容差（RGB 各通道）
            min_brightness: HSV V 通道最小亮度过滤（0=不过滤）
            min_saturation: HSV S 通道最小饱和度过滤（0=不过滤）
        """
        self._templates_dir = templates_dir
        self._threshold = threshold
        self._tolerance = tolerance
        self._min_brightness = min_brightness
        self._min_saturation = min_saturation
        self._entries: List[TemplateEntry] = []

    # ---- 加载 ----

    def load(self, only_files: Optional[List[str]] = None):
        """加载 templates.json 和模板图片

        Args:
            only_files: 仅加载指定文件名（如 ['zdsb.png']），None 表示全部
        """
        json_path = os.path.join(self._templates_dir, "templates.json")
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"templates.json 不存在: {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            raw_entries = json.load(f)

        # 去重：同文件多条记录只保留最新（最后一条）
        seen = {}
        for i, e in enumerate(raw_entries):
            seen[e["image_file"]] = i

        for idx in seen.values():
            e = raw_entries[idx]
            fname = e["image_file"]
            if only_files and fname not in only_files:
                continue

            cr = e["crop_region"]
            cx = (cr["x1"] + cr["x2"]) // 2
            cy = (cr["y1"] + cr["y2"]) // 2

            key_colors = []
            for name, kc in e["key_colors"].items():
                key_colors.append(KeyColor(
                    name=name,
                    rel_x=kc["x"],
                    rel_y=kc["y"],
                    expected_rgb=tuple(kc["rgb"]),
                ))

            entry = TemplateEntry(
                image_file=fname,
                crop_region=cr,
                crop_size=e["crop_size"],
                center=(cx, cy),
                key_colors=key_colors,
            )

            # 加载模板图片
            img_path = os.path.join(self._templates_dir, fname)
            if os.path.exists(img_path):
                entry.template_img = cv2.imread(img_path)

            self._entries.append(entry)

        print(f"[INFO] 加载 {len(self._entries)} 个模板 "
              f"(目录: {self._templates_dir})")

    # ---- 截图 ----

    @staticmethod
    def take_screenshot(host: str = "localhost", port: int = 5555) -> np.ndarray:
        """通过 ADB 截图并解码

        Returns:
            BGR numpy array
        """
        from game_platform.adb.device import ADBDevice
        device = ADBDevice(host, port)
        if not device.connect():
            raise ConnectionError(f"无法连接设备 {host}:{port}")
        raw = device.screenshot()
        device.disconnect()
        arr = np.frombuffer(raw, np.uint8)
        screen = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if screen is None:
            raise RuntimeError("截图解码失败")
        print(f"[INFO] 截图成功: {screen.shape[1]}x{screen.shape[0]}")
        return screen

    @staticmethod
    def load_image(path: str) -> np.ndarray:
        """从本地文件加载图片"""
        img = cv2.imread(path)
        if img is None:
            raise RuntimeError(f"图片读取失败: {path}")
        print(f"[INFO] 加载图片: {path} ({img.shape[1]}x{img.shape[0]})")
        return img

    # ---- 检测 ----

    def detect_all(self, screen: np.ndarray) -> List[MatchResult]:
        """对所有已加载模板执行检测

        Returns:
            MatchResult 列表
        """
        results = []
        for entry in self._entries:
            r = self._detect_one(screen, entry)
            results.append(r)
        return results

    def _detect_one(self, screen: np.ndarray, entry: TemplateEntry) -> MatchResult:
        """对单个模板执行模板匹配 + 像素检测"""
        r = MatchResult(
            image_file=entry.image_file,
            crop_region=entry.crop_region,
        )

        # ① 模板匹配
        if entry.template_img is not None:
            h, w = screen.shape[:2]
            screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
            tpl_gray = cv2.cvtColor(entry.template_img, cv2.COLOR_BGR2GRAY)
            match_map = cv2.matchTemplate(
                screen_gray, tpl_gray, cv2.TM_CCOEFF_NORMED
            )
            _, max_val, _, max_loc = cv2.minMaxLoc(match_map)
            th, tw = tpl_gray.shape[:2]
            r.tm_confidence = max_val
            r.tm_location = max_loc
            r.tm_center = (max_loc[0] + tw // 2, max_loc[1] + th // 2)
            r.tm_passed = max_val >= self._threshold

            # 计算匹配区域 HSV V 通道平均亮度和 S 通道平均饱和度
            bx1 = max(0, max_loc[0])
            by1 = max(0, max_loc[1])
            bx2 = min(w, max_loc[0] + tw)
            by2 = min(h, max_loc[1] + th)
            if bx2 > bx1 and by2 > by1:
                hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
                region = hsv[by1:by2, bx1:bx2]
                r.tm_brightness = float(np.mean(region[:, :, 2]))
                r.tm_saturation = float(np.mean(region[:, :, 1]))

        # ② 像素检测（在 crop_region 原始位置）
        cr = entry.crop_region
        h, w = screen.shape[:2]
        tol = self._tolerance
        r.pixel_total = len(entry.key_colors)

        for kc in entry.key_colors:
            abs_x = cr["x1"] + kc.rel_x
            abs_y = cr["y1"] + kc.rel_y

            if abs_x >= w or abs_y >= h or abs_x < 0 or abs_y < 0:
                ok = False
                actual = (0, 0, 0)
            else:
                b, g, red = screen[abs_y, abs_x]
                actual = (int(red), int(g), int(b))
                ok = all(
                    abs(a - e) <= tol
                    for a, e in zip(actual, kc.expected_rgb)
                )

            if ok:
                r.pixel_passed += 1
            r.pixel_results.append((
                kc.name, (abs_x, abs_y), kc.expected_rgb, actual, ok
            ))

        r.pixel_all_ok = (
            r.pixel_total > 0 and r.pixel_passed == r.pixel_total
        )
        return r

    # ---- 可视化标注 ----

    def draw_annotations(
        self,
        screen: np.ndarray,
        results: List[MatchResult],
    ) -> np.ndarray:
        """在截图上绘制检测结果标注

        Returns:
            标注后的图片（副本）
        """
        canvas = screen.copy()
        h, w = canvas.shape[:2]

        for r in results:
            cr = r.crop_region
            if not cr:
                continue

            # ① crop_region 绿色矩形
            x1, y1, x2, y2 = cr["x1"], cr["y1"], cr["x2"], cr["y2"]
            cv2.rectangle(canvas, (x1, y1), (x2, y2), self._COLOR_CROP_RECT, 2)

            # 中心十字
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            cross_size = 10
            cv2.line(
                canvas,
                (cx - cross_size, cy), (cx + cross_size, cy),
                self._COLOR_CENTER, 2,
            )
            cv2.line(
                canvas,
                (cx, cy - cross_size), (cx, cy + cross_size),
                self._COLOR_CENTER, 2,
            )

            # ② 模板匹配矩形（橙色 / 亮绿）
            if r.tm_passed:
                color = self._COLOR_TM_HIGH
            else:
                color = self._COLOR_TM_MATCH

            # 用模板尺寸画匹配框
            tpl_w = r.crop_region["x2"] - r.crop_region["x1"]
            tpl_h = r.crop_region["y2"] - r.crop_region["y1"]
            if r.tm_location != (0, 0) or r.tm_confidence > 0:
                mx, my = r.tm_location
                cv2.rectangle(
                    canvas,
                    (mx, my), (mx + tpl_w, my + tpl_h),
                    color, 2,
                )
                # 置信度标签
                label = f"{r.tm_confidence:.4f}"
                if r.tm_brightness > 0:
                    label += f" V={r.tm_brightness:.0f}"
                if r.tm_saturation > 0:
                    label += f" S={r.tm_saturation:.0f}"
                self._draw_label(canvas, label, (mx, my - 8), color)

            # ③ 像素检测采样点
            for name, (ax, ay), expected, actual, ok in r.pixel_results:
                dot_color = self._COLOR_PIXEL_PASS if ok else self._COLOR_PIXEL_FAIL
                cv2.circle(canvas, (ax, ay), 5, dot_color, -1)
                cv2.circle(canvas, (ax, ay), 6, (255, 255, 255), 1)

            # ④ 文件名 + 像素检测结果标签
            status = "PASS" if r.pixel_all_ok else f"{r.pixel_passed}/{r.pixel_total}"
            file_label = f"{r.image_file} [{status}]"
            label_color = (
                self._COLOR_PIXEL_PASS if r.pixel_all_ok
                else self._COLOR_PIXEL_FAIL
            )
            self._draw_label(
                canvas, file_label, (x1, y1 - 24), label_color, scale=0.5
            )

        return canvas

    @staticmethod
    def _draw_label(
        canvas: np.ndarray,
        text: str,
        pos: Tuple[int, int],
        color: Tuple[int, int, int],
        scale: float = 0.45,
    ):
        """绘制带黑色描边的文字标签"""
        font = cv2.FONT_HERSHEY_SIMPLEX
        thickness = 1
        # 黑色底边
        cv2.putText(canvas, text, pos, font, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
        # 彩色前景
        cv2.putText(canvas, text, pos, font, scale, color, thickness, cv2.LINE_AA)

    # ---- 汇总输出 ----

    @staticmethod
    def print_summary(results: List[MatchResult], threshold: float,
                      min_brightness: int = 0, min_saturation: int = 0):
        """控制台输出汇总表"""
        print()
        print("=" * 110)
        print(f"{'模板文件':<20} {'匹配置信度':>10} {'阈值':>6} {'TM':>5} "
              f"{'亮度':>6} {'亮度判定':>8} "
              f"{'饱和度':>6} {'饱和度判定':>10} "
              f"{'像素通过':>10} {'像素':>5} {'综合':>6}")
        print("-" * 110)

        for r in results:
            tm_mark = "OK" if r.tm_passed else "X"
            pixel_str = f"{r.pixel_passed}/{r.pixel_total}"
            pixel_mark = "OK" if r.pixel_all_ok else "X"

            # 亮度判定
            if min_brightness > 0:
                bright_mark = "OK" if r.tm_brightness >= min_brightness else "LOW"
            else:
                bright_mark = "-"

            # 饱和度判定
            if min_saturation > 0:
                sat_mark = "OK" if r.tm_saturation >= min_saturation else "LOW"
            else:
                sat_mark = "-"

            # 综合：模板匹配和像素检测都通过才算 OK
            both_ok = r.tm_passed and r.pixel_all_ok
            # 如果有亮度过滤，亮度也必须达标
            if min_brightness > 0 and r.tm_brightness < min_brightness:
                both_ok = False
            # 如果有饱和度过滤，饱和度也必须达标
            if min_saturation > 0 and r.tm_saturation < min_saturation:
                both_ok = False
            overall = "OK" if both_ok else "FAIL"

            print(
                f"{r.image_file:<20} {r.tm_confidence:>10.4f} "
                f"{threshold:>6.2f} {tm_mark:>5} "
                f"{r.tm_brightness:>6.0f} {bright_mark:>8} "
                f"{r.tm_saturation:>6.0f} {sat_mark:>10} "
                f"{pixel_str:>10} {pixel_mark:>5} {overall:>6}"
            )

        # 统计
        total = len(results)
        tm_ok = sum(1 for r in results if r.tm_passed)
        px_ok = sum(1 for r in results if r.pixel_all_ok)
        bright_ok = sum(
            1 for r in results
            if min_brightness <= 0 or r.tm_brightness >= min_brightness
        )
        sat_ok = sum(
            1 for r in results
            if min_saturation <= 0 or r.tm_saturation >= min_saturation
        )
        both_ok = sum(
            1 for r in results
            if r.tm_passed and r.pixel_all_ok
            and (min_brightness <= 0 or r.tm_brightness >= min_brightness)
            and (min_saturation <= 0 or r.tm_saturation >= min_saturation)
        )
        print("-" * 110)
        print(
            f"合计 {total} 个模板: "
            f"模板匹配通过 {tm_ok}, 亮度达标 {bright_ok}, "
            f"饱和度达标 {sat_ok}, "
            f"像素检测通过 {px_ok}, 全部通过 {both_ok}"
        )
        print("=" * 110)
        print()

    # ---- 全匹配调试模式 ----

    def run_match_all(
        self,
        screen: np.ndarray,
        output_dir: str = ".",
        output_prefix: str = "match_all_test",
        pixel_verify: bool = True,
    ) -> str:
        """全匹配模式：模拟程序 _match_all 的四层过滤管线

        管线：
            ① 颜色预过滤（红色 HSV 掩码）
            ② 局部极大值检测（形态学膨胀）
            ③ HSV 精细过滤（亮度 + 饱和度）
            ④ 关键点像素验证（内部红 + 角部非红）

        标注颜色：
            红色框 = 被颜色预过滤淘汰
            黄色框 = 被局部极大值淘汰
            橙色框 = 被 HSV 精细过滤淘汰
            紫色框 = 被像素验证淘汰
            绿色框 = 最终通过

        Args:
            screen: BGR 截图
            output_dir: 输出目录
            output_prefix: 输出文件名前缀
            pixel_verify: 是否启用第④层像素验证

        Returns:
            标注图片保存路径
        """
        os.makedirs(output_dir, exist_ok=True)
        canvas = screen.copy()
        h_img, w_img = screen.shape[:2]

        print()
        print("=" * 80)
        layers = "四层" if pixel_verify else "三层"
        print(f"全匹配调试模式（模拟程序 _match_all {layers}过滤）")
        print("=" * 80)

        # 像素验证采样点（11x12 菱形模板，中心 5,6）
        interior_offsets = [(0, 0), (-2, 0), (2, 0), (0, -3), (0, 3)]
        exterior_offsets = [(-5, -6), (5, -6), (-5, 5), (5, 5)]

        for entry in self._entries:
            if entry.template_img is None:
                continue

            screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
            tpl_gray = cv2.cvtColor(entry.template_img, cv2.COLOR_BGR2GRAY)
            th, tw = tpl_gray.shape[:2]

            # ── 模板匹配 ──
            result = cv2.matchTemplate(
                screen_gray, tpl_gray, cv2.TM_CCOEFF_NORMED
            )
            locations = np.where(result >= self._threshold)

            raw = [
                (int(x + tw // 2), int(y + th // 2), float(result[y, x]))
                for y, x in zip(locations[0].tolist(), locations[1].tolist())
            ]

            # ── ① 颜色预过滤 ──
            hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
            red1 = cv2.inRange(hsv, (0, 80, 120), (10, 255, 255))
            red2 = cv2.inRange(hsv, (160, 80, 120), (180, 255, 255))
            color_mask = cv2.bitwise_or(red1, red2)
            kernel = np.ones((3, 3), np.uint8)
            color_mask = cv2.morphologyEx(color_mask, cv2.MORPH_ERODE, kernel)

            after_color = [
                p for p in raw
                if 0 <= p[0] < w_img and 0 <= p[1] < h_img
                and color_mask[p[1], p[0]] > 0
            ]
            rejected_by_color = [
                p for p in raw
                if not (0 <= p[0] < w_img and 0 <= p[1] < h_img
                        and color_mask[p[1], p[0]] > 0)
            ]

            # ── ② 局部极大值 ──
            kernel_size = max(tw, th, 15)
            if kernel_size % 2 == 0:
                kernel_size += 1
            dilated = cv2.dilate(
                result, np.ones((kernel_size, kernel_size), np.uint8)
            )
            local_max_mask = (result >= dilated - 1e-6)

            after_maxima = [
                p for p in after_color
                if local_max_mask[p[1] - th // 2, p[0] - tw // 2]
            ]
            rejected_by_maxima = [
                p for p in after_color
                if not local_max_mask[p[1] - th // 2, p[0] - tw // 2]
            ]

            # ── ③ HSV 精细过滤 ──
            after_hsv = []
            rejected_by_hsv = []
            for p in after_maxima:
                bx1 = max(0, p[0] - tw // 2)
                by1 = max(0, p[1] - th // 2)
                bx2 = min(w_img, p[0] + tw // 2)
                by2 = min(h_img, p[1] + th // 2)
                if bx2 > bx1 and by2 > by1:
                    region = hsv[by1:by2, bx1:bx2]
                    mean_v = float(np.mean(region[:, :, 2]))
                    mean_s = float(np.mean(region[:, :, 1]))
                else:
                    mean_v, mean_s = 0, 0

                pass_b = (self._min_brightness <= 0
                          or mean_v >= self._min_brightness)
                pass_s = (self._min_saturation <= 0
                          or mean_s >= self._min_saturation)

                if pass_b and pass_s:
                    after_hsv.append((p, mean_v, mean_s))
                else:
                    rejected_by_hsv.append((p, mean_v, mean_s))

            # ── ④ 关键点像素验证 ──
            final = []
            rejected_by_pixels = []
            if pixel_verify:
                for p, v, s in after_hsv:
                    # 内部点：应为红色
                    int_red = 0
                    for dx, dy in interior_offsets:
                        sx, sy = p[0] + dx, p[1] + dy
                        if 0 <= sx < w_img and 0 <= sy < h_img:
                            b, g, r = (int(screen[sy, sx, 0]),
                                       int(screen[sy, sx, 1]),
                                       int(screen[sy, sx, 2]))
                            if r > 150 and g < 80 and b < 80:
                                int_red += 1

                    if int_red < len(interior_offsets) - 1:
                        rejected_by_pixels.append(
                            (p, v, s, f"int={int_red}"))
                        continue

                    # 角部点：不应全是红色
                    ext_red = 0
                    for dx, dy in exterior_offsets:
                        sx, sy = p[0] + dx, p[1] + dy
                        if 0 <= sx < w_img and 0 <= sy < h_img:
                            b, g, r = (int(screen[sy, sx, 0]),
                                       int(screen[sy, sx, 1]),
                                       int(screen[sy, sx, 2]))
                            if r > 150 and g < 80 and b < 80:
                                ext_red += 1

                    if ext_red > len(exterior_offsets) - 2:
                        rejected_by_pixels.append(
                            (p, v, s, f"ext={ext_red}"))
                        continue

                    final.append((p, v, s))
            else:
                final = after_hsv

            # ── 绘制标注 ──
            # 红色框 = 被颜色预过滤淘汰
            for p in rejected_by_color:
                cv2.rectangle(
                    canvas,
                    (p[0] - tw // 2, p[1] - th // 2),
                    (p[0] + tw // 2, p[1] + th // 2),
                    (0, 0, 240), 1,
                )
            # 黄色框 = 被局部极大值淘汰
            for p in rejected_by_maxima:
                cv2.rectangle(
                    canvas,
                    (p[0] - tw // 2, p[1] - th // 2),
                    (p[0] + tw // 2, p[1] + th // 2),
                    (0, 240, 240), 1,
                )
            # 橙色框 = 被 HSV 精细过滤淘汰
            for p, v, s in rejected_by_hsv:
                cv2.rectangle(
                    canvas,
                    (p[0] - tw // 2, p[1] - th // 2),
                    (p[0] + tw // 2, p[1] + th // 2),
                    (0, 140, 255), 2,
                )
                self._draw_label(
                    canvas,
                    f"{p[2]:.3f} V={v:.0f} S={s:.0f}",
                    (p[0] - tw // 2, p[1] - th // 2 - 8),
                    (0, 140, 255), scale=0.3,
                )
            # 紫色框 = 被像素验证淘汰
            for p, v, s, reason in rejected_by_pixels:
                cv2.rectangle(
                    canvas,
                    (p[0] - tw // 2, p[1] - th // 2),
                    (p[0] + tw // 2, p[1] + th // 2),
                    (200, 0, 200), 2,
                )
                self._draw_label(
                    canvas,
                    f"{p[2]:.3f} {reason}",
                    (p[0] - tw // 2, p[1] - th // 2 - 8),
                    (200, 0, 200), scale=0.3,
                )
            # 绿色框 = 最终通过
            for p, v, s in final:
                cv2.rectangle(
                    canvas,
                    (p[0] - tw // 2, p[1] - th // 2),
                    (p[0] + tw // 2, p[1] + th // 2),
                    (0, 220, 0), 2,
                )
                self._draw_label(
                    canvas,
                    f"{p[2]:.3f} V={v:.0f} S={s:.0f}",
                    (p[0] - tw // 2, p[1] - th // 2 - 8),
                    (0, 220, 0), scale=0.35,
                )

            print(f"\n[{entry.image_file}]")
            print(f"  原始匹配 (>= {self._threshold:.2f}):     {len(raw)} 个")
            print(f"  ① 颜色预过滤后:                          {len(after_color)} 个  "
                  f"(淘汰 {len(rejected_by_color)})")
            print(f"  ② 局部极大值后:                          {len(after_maxima)} 个  "
                  f"(淘汰 {len(rejected_by_maxima)})")
            print(f"  ③ HSV 精细过滤后:                        {len(after_hsv)} 个  "
                  f"(淘汰 {len(rejected_by_hsv)})")
            if pixel_verify:
                print(f"  ④ 像素验证后:                            {len(final)} 个  "
                      f"(淘汰 {len(rejected_by_pixels)})")
            if final:
                for p, v, s in final[:10]:
                    print(f"    ({p[0]:4d}, {p[1]:4d}) "
                          f"置信度={p[2]:.4f} V={v:.0f} S={s:.0f}")
                if len(final) > 10:
                    print(f"    ... 省略 {len(final) - 10} 个")

            legend = "  图例: 红框=颜色淘汰 黄框=极大值淘汰 橙框=HSV淘汰"
            if pixel_verify:
                legend += " 紫框=像素淘汰"
            legend += " 绿框=通过"
            print(f"\n{legend}")

        # 保存
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(output_dir, f"{output_prefix}_{ts}.png")
        cv2.imencode(".png", canvas)[1].tofile(out_path)
        print(f"\n[OUTPUT] 标注图已保存: {out_path}")
        print("=" * 80)
        print()
        return out_path

    # ---- 一键运行 ----

    def run(
        self,
        screen: np.ndarray,
        output_dir: str = ".",
        output_prefix: str = "template_test",
    ) -> str:
        """检测 + 标注 + 保存 + 打印汇总

        Args:
            screen: BGR 截图
            output_dir: 输出目录
            output_prefix: 输出文件名前缀

        Returns:
            标注图片保存路径
        """
        os.makedirs(output_dir, exist_ok=True)

        results = self.detect_all(screen)
        annotated = self.draw_annotations(screen, results)
        self.print_summary(results, self._threshold, self._min_brightness,
                           self._min_saturation)

        # 保存标注图
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(output_dir, f"{output_prefix}_{ts}.png")
        cv2.imencode(".png", annotated)[1].tofile(out_path)
        print(f"[OUTPUT] 标注图已保存: {out_path}")

        return out_path


# ---- CLI 入口 ----

def main():
    parser = argparse.ArgumentParser(
        description="通用模板/坐标识别可视化测试工具"
    )
    parser.add_argument(
        "--host", default="localhost", help="ADB 设备地址"
    )
    parser.add_argument(
        "--port", type=int, default=5555, help="ADB 端口"
    )
    parser.add_argument(
        "--image", default=None, help="使用本地图片代替实时截图"
    )
    parser.add_argument(
        "--dir", default=None,
        help="模板目录（默认 game_platform/screenshot/templates）"
    )
    parser.add_argument(
        "--only", default=None,
        help="仅测试指定模板（逗号分隔文件名，如 zdsb.png,zdsl.png）"
    )
    parser.add_argument(
        "--threshold", type=float, default=0.7,
        help="模板匹配置信度阈值（默认 0.7）"
    )
    parser.add_argument(
        "--tolerance", type=int, default=40,
        help="像素颜色容差（默认 40）"
    )
    parser.add_argument(
        "--brightness", type=int, default=0,
        help="HSV V 通道最小亮度过滤（0=不过滤，默认 0）"
    )
    parser.add_argument(
        "--saturation", type=int, default=0,
        help="HSV S 通道最小饱和度过滤（0=不过滤，默认 0）"
    )
    parser.add_argument(
        "--output", default=None, help="输出目录（默认当前目录）"
    )
    parser.add_argument(
        "--loop", type=float, default=0,
        help="循环模式：每隔 N 秒截一次图（0=单次）"
    )
    parser.add_argument(
        "--match-all", action="store_true",
        help="全匹配调试模式：显示所有超过阈值的匹配位置（模拟程序行为）"
    )
    args = parser.parse_args()

    # 模板目录
    if args.dir:
        tpl_dir = args.dir
    else:
        tpl_dir = os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "screenshot", "templates",
        ))

    # 输出目录
    output_dir = args.output or os.getcwd()

    # 初始化测试器
    tester = TemplateTester(
        templates_dir=tpl_dir,
        threshold=args.threshold,
        tolerance=args.tolerance,
        min_brightness=args.brightness,
        min_saturation=args.saturation,
    )

    only_files = None
    if args.only:
        only_files = [f.strip() for f in args.only.split(",")]

    tester.load(only_files=only_files)

    if not tester._entries:
        print("[ERROR] 没有可用的模板")
        sys.exit(1)

    # 单次 or 循环
    iteration = 0
    while True:
        iteration += 1
        if args.loop > 0 and iteration > 1:
            print(f"\n--- 第 {iteration} 轮 (等待 {args.loop} 秒) ---")
            time.sleep(args.loop)

        # 获取截图
        if args.image:
            screen = tester.load_image(args.image)
        else:
            screen = tester.take_screenshot(args.host, args.port)

        prefix = f"template_test_{iteration}" if args.loop > 0 else "template_test"

        if args.match_all:
            ma_prefix = f"match_all_{iteration}" if args.loop > 0 else "match_all"
            tester.run_match_all(screen, output_dir=output_dir,
                                 output_prefix=ma_prefix)
        else:
            tester.run(screen, output_dir=output_dir, output_prefix=prefix)

        if args.loop <= 0:
            break


if __name__ == "__main__":
    main()
