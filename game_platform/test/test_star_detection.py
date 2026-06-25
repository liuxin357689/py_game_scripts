"""
星星检测调试测试工具

连接 ADB 设备截图，运行暗能秘境的星星检测算法，
将 ROI 区域、检测到的星星位置、分组结果、点击位置
全部标注在截图上并保存为图片。同时输出匹配热力图。

用法:
    python -m game_platform.test.test_star_detection
    python -m game_platform.test.test_star_detection --host 127.0.0.1 --port 5555
    python -m game_platform.test.test_star_detection --image path/to/screenshot.png
    python -m game_platform.test.test_star_detection --delay 10
"""

import argparse
import os
import sys

import cv2
import numpy as np


# ---- 检测参数（与 AutoDarkRealm 保持一致）----

STAR_ROI = {"x1": 156, "y1": 477, "x2": 788, "y2": 550}
STAR_GROUP_GAP = 200
STAR_MIN_DIST = 25
STAR_THRESHOLD = 0.70
ORB_CLICK_Y = 650

TEMPLATES_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "screenshot", "templates",
))


def load_star_template() -> np.ndarray:
    """加载星星模板"""
    path = os.path.join(TEMPLATES_DIR, "anmj-xing.png")
    if not os.path.exists(path):
        print(f"[ERROR] 模板不存在: {path}")
        sys.exit(1)
    img = cv2.imread(path)
    if img is None:
        print(f"[ERROR] 模板读取失败: {path}")
        sys.exit(1)
    h, w = img.shape[:2]
    print(f"[INFO] 星星模板: {w}x{h}")
    return img


def non_max_suppression_with_conf(positions: list, min_dist: int) -> list:
    """基于置信度的非极大值抑制

    按置信度从高到低排序，每次保留最高置信度的匹配，
    然后移除其邻域内（距离 < min_dist）的所有低置信度匹配。

    Args:
        positions: [(x, y, confidence), ...]
        min_dist: 最小距离阈值

    Returns:
        [(x, y, confidence), ...] 去重后的结果
    """
    if not positions:
        return []

    # 按置信度从高到低排序
    positions.sort(key=lambda p: p[2], reverse=True)
    filtered = []

    for p in positions:
        # 检查是否与已保留的某个点距离太近
        too_close = False
        for f in filtered:
            dist = ((p[0] - f[0]) ** 2 + (p[1] - f[1]) ** 2) ** 0.5
            if dist < min_dist:
                too_close = True
                break
        if not too_close:
            filtered.append(p)

    return filtered


def detect_stars(screen: np.ndarray, tpl: np.ndarray, threshold: float) -> dict:
    """在 ROI 区域内检测星星并分组

    Returns:
        {
            "screen_size": (w, h),
            "roi": (x1, y1, x2, y2),
            "max_confidence": float,
            "raw_count": int,
            "low_threshold_count": int,
            "match_result": np.ndarray,  # 匹配热力图
            "positions": [(x, y), ...],  # NMS 后的绝对坐标
            "positions_with_conf": [(x, y, conf), ...],
            "groups": [{"count", "center_x", "positions"}, ...],
        }
    """
    h, w = screen.shape[:2]
    x1 = max(0, STAR_ROI["x1"])
    y1 = max(0, STAR_ROI["y1"])
    x2 = min(w, STAR_ROI["x2"])
    y2 = min(h, STAR_ROI["y2"])

    result_info = {
        "screen_size": (w, h),
        "roi": (x1, y1, x2, y2),
        "max_confidence": 0.0,
        "raw_count": 0,
        "low_threshold_count": 0,
        "match_result": None,
        "positions": [],
        "positions_with_conf": [],
        "groups": [],
    }

    if x2 <= x1 or y2 <= y1:
        print(f"[WARN] ROI 无效: ({x1},{y1})-({x2},{y2}), 屏幕 {w}x{h}")
        return result_info

    # 裁剪 ROI
    roi_img = screen[y1:y2, x1:x2]
    roi_gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
    match_result = cv2.matchTemplate(roi_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)

    _, max_val, _, max_loc = cv2.minMaxLoc(match_result)
    result_info["max_confidence"] = float(max_val)
    result_info["match_result"] = match_result
    result_info["max_loc_in_roi"] = (int(max_loc[0]), int(max_loc[1]))

    locations = np.where(match_result >= threshold)
    raw_count = len(locations[0])
    result_info["raw_count"] = raw_count

    # 同时用低阈值(0.70)看有多少候选
    low_threshold = 0.70
    low_locs = np.where(match_result >= low_threshold)
    result_info["low_threshold_count"] = len(low_locs[0])

    # 打印所有超过低阈值的匹配详情（用于调试）
    print(f"[INFO] 屏幕尺寸: {w}x{h}")
    print(f"[INFO] ROI: ({x1},{y1})-({x2},{y2}), 大小 {x2-x1}x{y2-y1}")
    print(f"[INFO] 阈值: {threshold}")
    print(f"[INFO] 最高置信度: {max_val:.4f} (ROI 内位置: {max_loc})")
    print(f"[INFO] 原始匹配数 (阈值{threshold}): {raw_count}")
    print(f"[INFO] 原始匹配数 (阈值{low_threshold}): {result_info['low_threshold_count']}")

    # 显示低阈值下的所有匹配位置（帮助发现遗漏的星星）
    if result_info["low_threshold_count"] > 0 and result_info["low_threshold_count"] <= 50:
        print(f"[DEBUG] 低阈值({low_threshold})匹配详情:")
        low_positions = []
        for y, x in zip(low_locs[0].tolist(), low_locs[1].tolist()):
            conf = float(match_result[y, x])
            abs_x, abs_y = int(x + x1), int(y + y1)
            low_positions.append((abs_x, abs_y, conf))
        # 按 x 排序
        low_positions.sort(key=lambda p: p[0])
        for i, (ax, ay, c) in enumerate(low_positions):
            print(f"  [{i}] ({ax}, {ay}) conf={c:.4f}")
    elif result_info["low_threshold_count"] == 0:
        print(f"[WARN] 低阈值({low_threshold})也无任何匹配！模板可能与当前画面不匹配")
        print(f"[WARN] 最高置信度仅 {max_val:.4f}，请检查诊断对比图 star_debug_diagnostic.png")

    if raw_count == 0:
        result_info["positions"] = []
        return result_info

    # 转绝对坐标 + 带置信度的 NMS
    raw_positions = []
    for y, x in zip(locations[0].tolist(), locations[1].tolist()):
        conf = float(match_result[y, x])
        raw_positions.append((int(x + x1), int(y + y1), conf))
    positions = non_max_suppression_with_conf(raw_positions, STAR_MIN_DIST)
    result_info["positions"] = [(p[0], p[1]) for p in positions]
    result_info["positions_with_conf"] = positions

    print(f"[INFO] NMS 去重后: {len(positions)} 个")
    for i, p in enumerate(positions):
        print(f"  [{i}] ({p[0]}, {p[1]}) conf={p[2]:.4f}")

    if not positions:
        return result_info

    # 按 x 坐标排序
    positions.sort(key=lambda p: p[0])

    # 聚类：相邻星星 x 间距超过阈值则分为不同组
    groups_raw = []
    current = [positions[0]]
    for i in range(1, len(positions)):
        if positions[i][0] - current[-1][0] > STAR_GROUP_GAP:
            groups_raw.append(current)
            current = [positions[i]]
        else:
            current.append(positions[i])
    groups_raw.append(current)

    # 构建结果：按星星数量降序排列
    result_groups = []
    for g in groups_raw:
        xs = [p[0] for p in g]
        center_x = sum(xs) // len(xs)
        result_groups.append({
            "count": len(g),
            "center_x": center_x,
            "positions": [(p[0], p[1]) for p in g],
        })
    result_groups.sort(key=lambda g: g["count"], reverse=True)
    result_info["groups"] = result_groups

    print(f"[INFO] 分组结果: {len(result_groups)} 组")
    for g in result_groups:
        print(
            f"  {g['count']}星, center_x={g['center_x']}, "
            f"点击位置=({g['center_x']}, {ORB_CLICK_Y})"
        )

    return result_info


def save_heatmap(info: dict, output_path: str):
    """保存匹配热力图"""
    match_result = info.get("match_result")
    if match_result is None:
        print("[WARN] 无匹配结果数据，跳过热力图")
        return

    # 归一化到 0-255
    heatmap = match_result.copy()
    hmin, hmax = heatmap.min(), heatmap.max()
    if hmax - hmin > 0:
        heatmap = ((heatmap - hmin) / (hmax - hmin) * 255).astype(np.uint8)
    else:
        heatmap = np.zeros_like(heatmap, dtype=np.uint8)

    # 应用 colormap
    heatmap_color = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)

    # 放大 4 倍便于查看
    heatmap_color = cv2.resize(
        heatmap_color, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST
    )

    # 添加文字标注
    cv2.putText(
        heatmap_color,
        f"Match Heatmap (max={info['max_confidence']:.4f})",
        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1,
    )

    hm_path = output_path.replace(".png", "_heatmap.png")
    cv2.imwrite(hm_path, heatmap_color)
    print(f"[OK] 热力图已保存: {hm_path}")


def save_diagnostic(screen: np.ndarray, tpl: np.ndarray, info: dict, output_path: str):
    """保存诊断对比图：模板 vs ROI 裁剪 vs 最佳匹配区域 vs 全屏搜索

    帮助判断模板匹配失败的根本原因：
    - ROI 位置不对？
    - 模板和实际星星长得不一样？
    - 模板在全屏其他地方匹配更好？
    """
    x1, y1, x2, y2 = info["roi"]
    th, tw = tpl.shape[:2]

    # 1. 全屏搜索模板（不限制 ROI）
    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
    full_result = cv2.matchTemplate(screen_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
    _, full_max, _, full_max_loc = cv2.minMaxLoc(full_result)
    print(f"[DIAG] 全屏搜索最高置信度: {full_max:.4f} 位置: {full_max_loc}")

    # 2. 裁剪最佳匹配区域（从屏幕中取出和模板等大的区域）
    best_x, best_y = info.get("max_loc_in_roi", (0, 0))
    abs_bx, abs_by = best_x + x1, best_y + y1
    roi_best_patch = screen[abs_by:abs_by+th, abs_bx:abs_bx+tw]

    # 全屏最佳匹配区域
    fx, fy = full_max_loc
    full_best_patch = screen[fy:fy+th, fx:fx+tw]

    # 3. 构建对比图（放大到统一尺寸）
    scale = 6  # 放大倍数
    tpl_big = cv2.resize(tpl, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    roi_patch_big = cv2.resize(roi_best_patch, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST) if roi_best_patch.size > 0 else np.zeros_like(tpl_big)
    full_patch_big = cv2.resize(full_best_patch, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST) if full_best_patch.size > 0 else np.zeros_like(tpl_big)

    # ROI 裁剪图
    roi_crop = screen[y1:y2, x1:x2]
    roi_crop_big = cv2.resize(roi_crop, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)

    # 拼成一行：模板 | ROI最佳 | 全屏最佳
    top_row = np.hstack([tpl_big, roi_patch_big, full_patch_big])

    # 添加标签
    label_y = 18
    cv2.putText(top_row, "Template", (5, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    cv2.putText(top_row, f"ROI best ({info['max_confidence']:.3f})", (tw*scale + 5, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    cv2.putText(top_row, f"FullScreen best ({full_max:.3f})", (tw*scale*2 + 5, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    # 4. 在全屏缩略图上标注 ROI 和最佳匹配位置
    thumb = cv2.resize(screen, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    # ROI 矩形
    cv2.rectangle(thumb, (x1//2, y1//2), (x2//2, y2//2), (0, 255, 0), 2)
    # 全屏最佳匹配位置
    cv2.rectangle(thumb, (fx//2, fy//2), ((fx+tw)//2, (fy+th)//2), (0, 0, 255), 2)
    cv2.putText(thumb, f"FullBest({full_max:.3f})", (fx//2, fy//2 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

    # 5. ROI 裁剪图放大
    roi_crop = screen[y1:y2, x1:x2]
    roi_crop_big = cv2.resize(roi_crop, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)

    # 上下拼接：先 top_row，再 thumb，最后 roi_crop（分开放避免高度不一致）
    diag_path = output_path.replace(".png", "_diagnostic.png")

    # 保存 top_row（模板对比）
    cv2.imwrite(diag_path, top_row)

    # 保存缩略图（带标注）
    thumb_path = output_path.replace(".png", "_thumb.png")
    cv2.imwrite(thumb_path, thumb)

    # 保存 ROI 裁剪图
    roi_diag_path = output_path.replace(".png", "_roi_diag.png")
    cv2.imwrite(roi_diag_path, roi_crop_big)

    print(f"[OK] 诊断对比图已保存: {diag_path} (模板对比)")
    print(f"[OK] 全屏缩略图已保存: {thumb_path} (ROI绿框 + 全屏最佳红框)")


def draw_annotations(screen: np.ndarray, info: dict) -> np.ndarray:
    """在截图上标注检测结果"""
    canvas = screen.copy()
    x1, y1, x2, y2 = info["roi"]

    # 1. 画 ROI 区域（绿色矩形）
    cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(
        canvas, f"ROI ({x1},{y1})-({x2},{y2})",
        (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1,
    )

    # 1.5 始终标注最佳匹配位置（即使低于阈值）
    max_loc_roi = info.get("max_loc_in_roi")
    if max_loc_roi:
        best_x = max_loc_roi[0] + x1
        best_y = max_loc_roi[1] + y1
        cv2.rectangle(
            canvas,
            (best_x - 2, best_y - 2), (best_x + 22, best_y + 22),
            (0, 255, 255), 2,
        )
        cv2.putText(
            canvas, f"best({info['max_confidence']:.3f})",
            (best_x + 25, best_y + 12),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1,
        )

    # 2. 画每个检测到的星星（蓝色实心 + 置信度）
    for p in info.get("positions_with_conf", []):
        px, py, conf = int(p[0]), int(p[1]), p[2]
        cv2.circle(canvas, (px, py), 5, (255, 0, 0), -1)
        cv2.putText(
            canvas, f"{conf:.3f}",
            (px + 8, py - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 0), 1,
        )

    # 3. 画分组 + 标注
    colors = [
        (0, 0, 255),     # 红色 - 最高星组
        (0, 165, 255),   # 橙色 - 第二组
        (0, 255, 255),   # 黄色 - 第三组
        (255, 0, 255),   # 紫色 - 第四组
    ]

    for i, g in enumerate(info["groups"]):
        color = colors[i % len(colors)]
        # 标记组内每颗星
        for p in g["positions"]:
            cv2.circle(canvas, (int(p[0]), int(p[1])), 12, color, 2)

        # 组标签：X星
        cx = g["center_x"]
        label = f"{g['count']}star"
        cv2.putText(
            canvas, label,
            (cx - 30, y1 - 25),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2,
        )

        # 画光球点击位置（红色十字）
        click_x, click_y = cx, ORB_CLICK_Y
        cv2.drawMarker(
            canvas, (click_x, click_y), (0, 0, 255),
            cv2.MARKER_CROSS, 30, 3,
        )
        cv2.putText(
            canvas, f"click({click_x},{click_y})",
            (click_x - 60, click_y + 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1,
        )

    # 4. 顶部信息栏
    info_text = (
        f"Screen:{info['screen_size'][0]}x{info['screen_size'][1]}  "
        f"MaxConf:{info['max_confidence']:.4f}  "
        f"Raw:{info['raw_count']}  "
        f"LowTh({info.get('low_threshold_count', '?')})  "
        f"NMS:{len(info['positions'])}  "
        f"Groups:{len(info['groups'])}  "
        f"Threshold:{STAR_THRESHOLD}"
    )
    cv2.rectangle(canvas, (0, 0), (info["screen_size"][0], 30), (0, 0, 0), -1)
    cv2.putText(
        canvas, info_text,
        (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1,
    )

    return canvas


def take_screenshot(host: str, port: int) -> np.ndarray:
    """通过 ADB 截图"""
    from game_platform.adb.device import ADBDevice
    device = ADBDevice(host, port)
    print(f"[INFO] 连接设备 {host}:{port}...")
    if not device.connect():
        print(f"[ERROR] 无法连接 {host}:{port}")
        sys.exit(1)
    print("[INFO] 截图...")
    raw = device.screenshot()
    device.disconnect()
    arr = np.frombuffer(raw, np.uint8)
    screen = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if screen is None:
        print("[ERROR] 截图解码失败")
        sys.exit(1)
    return screen


def main():
    parser = argparse.ArgumentParser(description="星星检测调试工具")
    parser.add_argument("--host", default="localhost", help="ADB 主机地址")
    parser.add_argument("--port", type=int, default=5555, help="ADB 端口")
    parser.add_argument("--image", help="直接加载本地图片（跳过 ADB 截图）")
    parser.add_argument(
        "--threshold", type=float, default=STAR_THRESHOLD,
        help=f"匹配置信度阈值 (默认 {STAR_THRESHOLD})",
    )
    parser.add_argument(
        "--output", default=None,
        help="标注图片保存路径（默认: 同目录下 star_debug.png）",
    )
    parser.add_argument(
        "--delay", type=int, default=0,
        help="截图前等待秒数，用于切换到战斗画面（默认 0）",
    )
    args = parser.parse_args()

    # 加载模板
    tpl = load_star_template()

    # 获取截图
    if args.image:
        print(f"[INFO] 加载本地图片: {args.image}")
        screen = cv2.imread(args.image)
        if screen is None:
            print(f"[ERROR] 图片读取失败: {args.image}")
            sys.exit(1)
    else:
        if args.delay > 0:
            print(f"[INFO] 等待 {args.delay} 秒，请切换到暗能秘境战斗画面...")
            import time
            for i in range(args.delay, 0, -1):
                print(f"  {i}...")
                time.sleep(1)
            print("[INFO] 开始截图")
        screen = take_screenshot(args.host, args.port)

    print(f"[INFO] 截图尺寸: {screen.shape[1]}x{screen.shape[0]}")

    # 运行检测
    info = detect_stars(screen, tpl, args.threshold)

    # 画标注
    annotated = draw_annotations(screen, info)

    # 保存
    output_path = args.output or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "star_debug.png"
    )
    cv2.imwrite(output_path, annotated)
    print(f"\n[OK] 标注图片已保存: {output_path}")

    # 保存热力图
    save_heatmap(info, output_path)

    # 保存诊断对比图（模板 vs ROI最佳 vs 全屏最佳）
    save_diagnostic(screen, tpl, info, output_path)

    # 保存原始截图
    raw_path = output_path.replace(".png", "_raw.png")
    cv2.imwrite(raw_path, screen)
    print(f"[OK] 原始截图已保存: {raw_path}")

    # 保存 ROI 裁剪图
    x1, y1, x2, y2 = info["roi"]
    if x2 > x1 and y2 > y1:
        roi_crop = screen[y1:y2, x1:x2]
        roi_path = output_path.replace(".png", "_roi.png")
        cv2.imwrite(roi_path, roi_crop)
        print(f"[OK] ROI 裁剪图已保存: {roi_path}")


if __name__ == "__main__":
    main()
