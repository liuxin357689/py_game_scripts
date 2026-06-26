"""
auto_activity_reward 集成测试

直接调用 AutoActivityReward 的真实代码，加载真实模板，
对合成测试图执行检测，验证 key_colors 多点像素对比输出，
并生成带标记的 annotated 截图保存到 tests/results/。

运行方式（从项目根目录）：
    python -m tests.test_auto_activity_reward

或从任意目录：
    python D:/game_scripts/projects/hero-afk/tests/test_auto_activity_reward.py
"""

import logging
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# ── 路径准备 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
TESTS_DIR = PROJECT_ROOT / "tests"
RESULTS_DIR = TESTS_DIR / "results"
TEMPLATES_DIR = Path(
    r"D:\game_scripts\game_platform\screenshot\templates"
)

# 将 game_scripts 加入 import path
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

# ── 日志配置 ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("test_auto_activity_reward")

RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════
#  辅助：绘制检测标记
# ══════════════════════════════════════════════════════════

def annotate_image(
    img: np.ndarray,
    detections: list[tuple[int, int]],
    title: str,
) -> np.ndarray:
    """在图上绘制检测框和标签，返回 annotated 图片。"""
    annotated = img.copy()
    color = (0, 255, 0)  # 绿色 = 检测到
    thick = 2

    for i, (cx, cy) in enumerate(detections):
        cv2.rectangle(annotated, (cx - 10, cy - 10), (cx + 10, cy + 10),
                      color, thick)
        # 画中心十字
        cv2.line(annotated, (cx - 8, cy), (cx + 8, cy), color, thick)
        cv2.line(annotated, (cx, cy - 8), (cx, cy + 8), color, thick)
        label = f"#{i + 1} ({cx},{cy})"
        cv2.putText(
            annotated, label, (cx + 12, cy - 4),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1,
        )

    # 标题栏
    status = f"{len(detections)} detected"
    full_title = f"{title} | {status}"

    bar_h = 22
    annotated[:bar_h] = cv2.addWeighted(
        annotated[:bar_h], 0.6,
        np.full_like(annotated[:bar_h], 30), 0.4, 0,
    )
    cv2.putText(
        annotated, full_title, (6, 16),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
    )
    return annotated


# ══════════════════════════════════════════════════════════
#  场景图生成
# ══════════════════════════════════════════════════════════

def make_fullscreen_background(w: int = 900, h: int = 1600) -> np.ndarray:
    """生成接近游戏风格的合成全屏背景截图。"""
    # 深色渐变背景
    bg = np.zeros((h, w, 3), dtype=np.uint8)
    bg[:, :] = [30, 30, 40]  # 深蓝灰色
    # 模拟 UI 分隔线
    cv2.rectangle(bg, (0, 250), (w, 260), (60, 60, 70), 1)
    cv2.rectangle(bg, (0, 600), (w, 602), (60, 60, 70), 1)
    return bg


def paste_badge_on_screen(
    screen: np.ndarray,
    badge_img: np.ndarray,
    cx: int,
    cy: int,
) -> np.ndarray:
    """在 screen 的 (cx, cy) 位置粘贴 badge_img（中心对齐）。"""
    scene = screen.copy()
    bh, bw = badge_img.shape[:2]
    x1 = max(0, cx - bw // 2)
    y1 = max(0, cy - bh // 2)
    x2 = min(scene.shape[1], x1 + bw)
    y2 = min(scene.shape[0], y1 + bh)
    src_x1 = x1 - (cx - bw // 2)
    src_y1 = y1 - (cy - bh // 2)
    src_x2 = src_x1 + (x2 - x1)
    src_y2 = src_y1 + (y2 - y1)
    if src_x2 <= 0 or src_y2 <= 0:
        return scene
    scene[y1:y2, x1:x2] = badge_img[src_y1:src_y2, src_x1:src_x2]
    return scene


def draw_synthetic_badge(
    scene: np.ndarray,
    cx: int,
    cy: int,
    size: int = 6,
    bgr: tuple[int, int, int] = (40, 40, 255),
) -> np.ndarray:
    """在 scene 上绘制一个红色菱形（像素级模拟角标）。"""
    canvas = scene.copy()
    half = size
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            if abs(dx) + abs(dy) <= half:
                px, py = cx + dx, cy + dy
                if 0 <= px < canvas.shape[1] and 0 <= py < canvas.shape[0]:
                    canvas[py, px] = bgr
    return canvas


# ══════════════════════════════════════════════════════════
#  测试运行器
# ══════════════════════════════════════════════════════════

def run_test(
    task,
    scene_img: np.ndarray,
    scene_name: str,
    detect_fn_name: str,
) -> list[tuple[int, int]]:
    """
    对单张场景图执行检测，记录耗时，返回检测结果。
    同时生成并保存 annotated 截图。
    """
    log.info(f"{'=' * 60}")
    log.info(f"[{scene_name}] 场景: {scene_name} | 检测方法: {detect_fn_name}")
    log.info(f"     截图尺寸: {scene_img.shape[1]}x{scene_img.shape[0]}")

    t0 = time.perf_counter()

    if detect_fn_name == "_detect_badges":
        result = task._detect_badges(scene_img)
    elif detect_fn_name == "_detect_badges_fullscreen":
        result = task._detect_badges_fullscreen(scene_img)
    else:
        raise ValueError(f"未知检测方法: {detect_fn_name}")

    elapsed = time.perf_counter() - t0

    log.info(f"[{scene_name}] 检测完成: {len(result)} 个角标 | 耗时 {elapsed:.3f}s")

    annotated = annotate_image(scene_img, result, title=f"{scene_name}/{detect_fn_name}")
    out_path = RESULTS_DIR / f"{scene_name}_annotated.png"
    cv2.imwrite(str(out_path), annotated)
    log.info(f"[{scene_name}] 标注图已保存: {out_path}")

    return result


# ══════════════════════════════════════════════════════════
#  主测试流程
# ══════════════════════════════════════════════════════════

def main():
    log.info("╔══════════════════════════════════════════════════════╗")
    log.info("║  auto_activity_reward 集成测试（key_colors 多点版）   ║")
    log.info("╚══════════════════════════════════════════════════════╝")
    log.info("结果输出目录: %s", RESULTS_DIR)

    # ── 1. 加载被测模块 ──────────────────────────────────────
    game_scripts_root = str(PROJECT_ROOT.parent.parent)
    if game_scripts_root not in sys.path:
        sys.path.insert(0, game_scripts_root)

    import importlib.util
    _task_mod_path = PROJECT_ROOT / "hero_afk" / "tasks" / "auto_activity_reward.py"
    spec = importlib.util.spec_from_file_location(
        "auto_activity_reward_mod", str(_task_mod_path)
    )
    _task_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_task_mod)  # type: ignore
    AutoActivityReward = _task_mod.AutoActivityReward

    task = AutoActivityReward(threshold=0.7)
    task._logger.setLevel(logging.DEBUG)
    for h in logging.getLogger("hero_afk").handlers:
        logging.getLogger("hero_afk").removeHandler(h)
    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG)
    sh.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                          datefmt="%H:%M:%S")
    )
    logging.getLogger("hero_afk").addHandler(sh)
    logging.getLogger("hero_afk").setLevel(logging.DEBUG)

    log.info("加载模板中...")
    task.setup()
    log.info("模板加载完成")

    # ── 2. 检查 JSON 加载状态 ────────────────────────────────
    log.info(
        "JSON 加载状态: crop_region=%s, key_colors=%s 条（每条 %s 点）",
        task._jllq_crop_region,
        len(task._badge_key_colors),
        len(task._badge_key_colors[0]) if task._badge_key_colors else 0,
    )

    if not task._badge_key_colors:
        log.error("key_colors 未加载，测试无法继续")
        sys.exit(1)

    # 打印 key_colors 详情（用于调试）
    for i, kc in enumerate(task._badge_key_colors):
        log.info("  key_colors[%s] 共 %s 点:", i, len(kc))
        for pt in kc:
            log.info(
        "    rel=(%s,%s) expected BGR=(%s,%s,%s)",
                pt["rel_x"], pt["rel_y"], pt["b"], pt["g"], pt["r"],
            )

    # ── 3. 加载 badge 模板图片 ────────────────────────────────
    badge_img = cv2.imread(str(TEMPLATES_DIR / "jllq-hb.png"))
    if badge_img is None:
        log.error("无法加载 jllq-hb.png: %s", TEMPLATES_DIR / "jllq-hb.png")
        sys.exit(1)
    badge_shape = (badge_img.shape[1], badge_img.shape[0])
    log.info("badge_template 尺寸: %sx%s", badge_shape[0], badge_shape[1])

    # ── 4. 生成测试场景（全在 900x1600 上）────────────────────
    W, H = 900, 1600
    roi_x1, roi_y1, roi_x2, roi_y2 = task._jllq_crop_region or (0, 0, W, H)

    # 场景 A: 纯背景无角标
    scene_a = make_fullscreen_background(W, H)
    log.info("场景 A: 纯背景 %sx%s", W, H)

    # 场景 B: ROI 区域内有一个角标
    roi_cx = (roi_x1 + roi_x2) // 2
    roi_cy = (roi_y1 + roi_y2) // 2
    scene_b = paste_badge_on_screen(
        make_fullscreen_background(W, H), badge_img, roi_cx, roi_cy,
    )
    log.info("场景 B: ROI中心单角标 (%s,%s)", roi_cx, roi_cy)

    # 场景 C: ROI 区域内有多个角标
    scene_c = make_fullscreen_background(W, H)
    multi_pos = [
        (roi_x1 + 30, roi_y1 + 30),
        (roi_x2 - 30, roi_y1 + 50),
        (roi_cx, roi_y2 - 30),
    ]
    for cx, cy in multi_pos:
        scene_c = paste_badge_on_screen(scene_c, badge_img, cx, cy)
    log.info("场景 C: ROI多角标 %s", multi_pos)

    # 场景 D: 全屏任意位置有角标（测试全屏检测）
    scene_d = make_fullscreen_background(W, H)
    scene_d = paste_badge_on_screen(scene_d, badge_img, 200, 300)
    scene_d = paste_badge_on_screen(scene_d, badge_img, 700, 500)
    log.info("场景 D: 全屏任意位置多角标")

    # 场景 E: 背景中混入暗红色干扰（模拟误匹配场景）
    scene_e = make_fullscreen_background(W, H)
    # 绘制暗红色块（不是角标，应被过滤）
    cv2.rectangle(scene_e, (100, 100), (130, 130), (20, 20, 80), -1)  # 暗红
    # 绘制一个接近但不完全正确的菱形
    scene_e = draw_synthetic_badge(scene_e, 450, 800, size=6)
    log.info("场景 E: 含干扰色的背景（无真实角标）")

    # ── 5. 逐场景运行检测 ────────────────────────────────────
    results: dict[str, list[tuple[int, int]]] = {}

    tests = [
        # 场景名, 检测方法
        ("A_bg_fullscreen",   "_detect_badges_fullscreen"),
        ("A_bg_roi",          "_detect_badges"),
        ("B_single_roi",     "_detect_badges"),
        ("B_single_fullscreen", "_detect_badges_fullscreen"),
        ("C_multi_roi",       "_detect_badges"),
        ("C_multi_fullscreen", "_detect_badges_fullscreen"),
        ("D_scattered_fullscreen", "_detect_badges_fullscreen"),
        ("E_noise_fullscreen", "_detect_badges_fullscreen"),
    ]

    scenes = {
        "A_bg_fullscreen": scene_a,
        "A_bg_roi": scene_a,
        "B_single_roi": scene_b,
        "B_single_fullscreen": scene_b,
        "C_multi_roi": scene_c,
        "C_multi_fullscreen": scene_c,
        "D_scattered_fullscreen": scene_d,
        "E_noise_fullscreen": scene_e,
    }

    for name, fn_name in tests:
        results[name] = run_test(task, scenes[name], name, fn_name)

    # ── 6. 汇总报告 ──────────────────────────────────────────
    log.info("")
    log.info("╔══════════════════════════════════════════════════════╗")
    log.info("║                    测试结果汇总                      ║")
    log.info("╠══════════════════════════════════════════════════════╣")
    for name, detections in results.items():
        status = "✓ PASS" if detections else "✗ 0检测"
        log.info("  %-30s %s  →  %s 个角标",
                 name, status, len(detections))
    log.info("╚══════════════════════════════════════════════════════╝")

    # 保存汇总图
    summary = make_summary_image(results, scene_a)
    summary_path = RESULTS_DIR / "summary_all_scenes.png"
    cv2.imwrite(str(summary_path), summary)
    log.info("汇总图已保存: %s", summary_path)

    task.teardown()
    log.info("测试完成")


def make_summary_image(
    results: dict[str, list[tuple[int, int]]],
    ref_img: np.ndarray,
) -> np.ndarray:
    """将所有 annotated 场景拼成一张总览图。"""
    cols = 3
    rows = (len(results) + cols - 1) // cols
    thumb_w = 320
    thumb_h = int(thumb_w * ref_img.shape[0] / ref_img.shape[1])

    summary_h = rows * thumb_h + 30
    summary_w = cols * thumb_w
    summary = np.full((summary_h, summary_w, 3), 25, dtype=np.uint8)

    cv2.putText(
        summary, "auto_activity_reward 集成测试结果汇总",
        (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1,
    )

    for i, (name, detections) in enumerate(results.items()):
        row, col = divmod(i, cols)
        x_off = col * thumb_w
        y_off = row * thumb_h + 30

        annotated = annotate_image(ref_img.copy(), detections, title=name)
        thumb = cv2.resize(annotated, (thumb_w, thumb_h))
        summary[y_off:y_off + thumb_h, x_off:x_off + thumb_w] = thumb

    return summary


if __name__ == "__main__":
    main()
