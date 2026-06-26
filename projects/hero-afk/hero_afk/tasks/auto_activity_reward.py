"""
自动领取活动奖励任务（帧任务版）

状态机：
    LOOKING_ACTIVITY  → 扫描活动列表中带有奖励角标的图标 → 点击第一个 → CLAIMING_REWARD
    CLAIMING_REWARD   → 在奖励详情页中检测角标并点击领取 → 领完 → CLOSING
    CLOSING           → 按优先级关闭页面(close2>close3>坐标>back) → LOOKING_ACTIVITY
    DONE              → 所有奖励已领完（终止）

核心设计：
    每次从详情页返回后重新扫描活动列表（页面可能刷新），
    只处理当前第一个带角标的活动，直到所有角标消失。

截图共享架构：不自行截图，由 ScreenshotService 推送帧画面。

模板来源: game_platform/screenshot/templates/
"""

import json
import logging
import os
from enum import Enum, auto

import cv2
import numpy as np

from game_platform.task.frame_task import FrameTask, TapAction

logger = logging.getLogger(__name__)

# 模板资源目录
_TEMPLATES_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..", "game_platform", "screenshot", "templates",
))
# templates.json 文件路径
_TEMPLATES_JSON = os.path.join(_TEMPLATES_DIR, "templates.json")


class _State(Enum):
    LOOKING_ACTIVITY = auto()
    CLAIMING_REWARD = auto()
    CLOSING = auto()
    DONE = auto()


class AutoActivityReward(FrameTask):
    """自动领取活动奖励 — 帧任务版

    key_colors 多点像素对比检测奖励角标 + 模板匹配检测关闭按钮，
    所有截图由 ScreenshotService 推送。
    """

    # 关闭按钮模板文件
    TEMPLATE_CLOSE2 = "close2.png"     # 关闭按钮 v2
    TEMPLATE_CLOSE3 = "close3.png"     # 关闭按钮 v3
    TEMPLATE_BACK = "back.png"         # 返回按钮
    TEMPLATE_BADGE = "jllq-hb.png"     # 奖励角标

    # 关闭页面的坐标兜底
    _CLOSE_FALLBACK_POS = (200, 1500)

    # 超时保护
    _MAX_WAIT = 120

    def __init__(
        self,
        threshold: float = 0.7,
    ):
        """
        Args:
            threshold: 模板匹配置信度阈值（关闭按钮等）
        """
        super().__init__(name="自动领取活动奖励", priority=25)
        self._threshold = threshold

        # 关闭按钮模板
        self._tpl_close2 = None
        self._tpl_close3 = None
        self._tpl_back = None
        self._tpl_badge = None

        # templates.json 解析结果
        # jllq.png crop_region: (x1, y1, x2, y2) 活动列表区域
        self._jllq_crop_region: tuple[int, int, int, int] | None = None
        # jllq-hb.png key_colors: [{rel_x, rel_y, b, g, r}, ...] 角标多点像素验证
        self._badge_key_colors: list[dict] = []

        # 状态机
        self._state = _State.LOOKING_ACTIVITY
        self._pending_state = None
        self._click_count = 0

        # 等待帧计数（超时保护）
        self._wait_frames = 0

    def activate(self):
        """激活任务 — 重置状态机"""
        super().activate()
        self._state = _State.LOOKING_ACTIVITY
        self._pending_state = None
        self._wait_frames = 0
        self._click_count = 0
        self._logger.info("activate: 状态已重置 -> LOOKING_ACTIVITY")

    # ---- 生命周期 ----

    def setup(self):
        """加载模板"""
        self._logger.debug("setup: 开始加载模板...")
        self._load_templates()
        self._load_templates_from_json()

    def teardown(self):
        """清理"""
        self._logger.info(
            "teardown: 自动领取活动奖励结束, 累计点击 %s 次", self._click_count
        )

    # ---- 帧处理 ----

    def on_frame(self, screen: np.ndarray):
        if self._state == _State.DONE:
            return None

        if self._state == _State.LOOKING_ACTIVITY:
            return self._handle_looking_activity(screen)

        elif self._state == _State.CLAIMING_REWARD:
            return self._handle_claiming(screen)

        elif self._state == _State.CLOSING:
            return self._handle_closing(screen)

        return None

    def on_action_executed(self, action):
        """动作执行后：应用挂起的状态切换 + 更新计数"""
        self._click_count += 1
        if self._pending_state is not None:
            old = self._state
            self._state = self._pending_state
            self._pending_state = None
            self._wait_frames = 0
            self._logger.info(
                "on_action_executed: 动作已执行, 状态切换: %s -> %s",
                old.name, self._state.name,
            )

    def _on_state_transition(self, new_state: _State):
        """登记状态切换，在动作执行后生效"""
        self._logger.debug(
            "_on_state_transition: %s -> %s (待执行动作后生效)",
            self._state.name, new_state.name,
        )
        self._pending_state = new_state

    # ---- 状态处理 ----

    def _handle_looking_activity(self, screen: np.ndarray):
        """扫描活动列表，检测带角标的活动并点击第一个

        每次重新扫描排序，不缓存位置（页面可能刷新）。
        """
        badges = self._detect_badges(screen)
        if badges:
            # 按位置排序：上→下，左→右
            badges.sort(key=lambda b: (b[1], b[0]))
            first = badges[0]
            self._logger.info(
                "[LOOKING] 检测到 %s 个奖励角标, 点击第一个: (%s, %s)",
                len(badges), first[0], first[1],
            )
            self._on_state_transition(_State.CLAIMING_REWARD)
            self._wait_frames = 0
            return TapAction(first[0], first[1], description="点击活动(有奖励)")

        # 没有角标 — 等待几帧确认（防止页面还没加载完）
        self._wait_frames += 1
        if self._wait_frames % 10 == 1 or self._wait_frames > 25:
            self._logger.debug(
                "[LOOKING] 等待中 %s/%s 帧", self._wait_frames, 30
            )
        if self._wait_frames > 30:
            self._logger.warning(
                "[LOOKING] 超时 %s 帧未检测到角标，任务结束", self._wait_frames
            )
            self._state = _State.DONE
            self._wait_frames = 0

        return None

    def _handle_claiming(self, screen: np.ndarray):
        """在奖励详情页中检测角标并点击领取

        奖励详情页没有 jllq.png 活动列表，使用全屏检测。
        有角标 → 点击领取（留在 CLAIMING_REWARD，下次继续检测）
        无角标 → 进入 CLOSING
        """
        badges = self._detect_badges_fullscreen(screen)
        if badges:
            badges.sort(key=lambda b: (b[1], b[0]))
            first = badges[0]
            self._logger.info(
                "[CLAIMING] 奖励页检测到 %s 个角标, 点击: (%s, %s)",
                len(badges), first[0], first[1],
            )
            self._wait_frames = 0
            # 不切换状态，点击后留在 CLAIMING_REWARD 继续检测
            return TapAction(first[0], first[1], description="领取奖励")

        # 没有角标 — 等待几帧确认
        self._wait_frames += 1
        if self._wait_frames % 5 == 1:
            self._logger.debug(
                "[CLAIMING] 等待中 %s/%s 帧", self._wait_frames, 15
            )
        if self._wait_frames > 15:
            self._logger.warning(
                "[CLAIMING] 超时 %s 帧无角标，准备关闭页面", self._wait_frames
            )
            self._state = _State.CLOSING
            self._wait_frames = 0

        return None

    def _handle_closing(self, screen: np.ndarray):
        """关闭奖励页面，按优先级尝试：
        close2.png > close3.png > 坐标(200,1500) > back.png
        """
        # ① close2.png
        self._logger.debug("[CLOSING] 尝试 close2 (阈值 %.2f)", self._threshold)
        hit, pos = self._match_template(screen, self._tpl_close2)
        if hit:
            self._logger.info("关闭页面: close2 -> %s", pos)
            self._on_state_transition(_State.LOOKING_ACTIVITY)
            return TapAction(pos[0], pos[1], description="关闭(close2)")

        # ② close3.png
        self._logger.debug("[CLOSING] 尝试 close3 (阈值 %.2f)", self._threshold)
        hit, pos = self._match_template(screen, self._tpl_close3)
        if hit:
            self._logger.info("关闭页面: close3 -> %s", pos)
            self._on_state_transition(_State.LOOKING_ACTIVITY)
            return TapAction(pos[0], pos[1], description="关闭(close3)")

        # ③ 坐标兜底 (200, 1500)
        cx, cy = self._CLOSE_FALLBACK_POS
        self._logger.warning(
            "[CLOSING] close2/close3 均未命中，使用坐标兜底 -> (%s, %s)",
            cx, cy,
        )
        self._on_state_transition(_State.LOOKING_ACTIVITY)
        return TapAction(cx, cy, description="关闭(坐标兜底)")

    # ---- 角标检测（模板匹配）----

    def _match_badge_in_roi(self, screen: np.ndarray) -> list[tuple[int, int]]:
        """在 jllq.png 活动列表区域内用模板匹配检测奖励角标

        在 jllq.png 的 crop_region ROI 内执行 cv2.matchTemplate，
        用非极大值抑制（NMS）去重，找出所有有效匹配位置，返回全屏坐标列表。

        Returns:
            [(cx, cy), ...] 角标中心坐标列表（全屏坐标）
        """
        if self._tpl_badge is None:
            self._logger.debug("[角标检测] jllq-hb.png 模板未加载")
            return []

        if not self._jllq_crop_region:
            self._logger.debug("[角标检测] jllq.png crop_region 未定义")
            return []

        # 取 ROI
        x1, y1, x2, y2 = self._jllq_crop_region
        h_s, w_s = screen.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w_s, x2), min(h_s, y2)
        if x2 <= x1 or y2 <= y1:
            return []

        roi = screen[y1:y2, x1:x2]
        roi_h, roi_w = roi.shape[:2]

        # 模板匹配
        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.cvtColor(self._tpl_badge, cv2.COLOR_BGR2GRAY)
        th, tw = tpl_gray.shape[:2]

        if th > roi_h or tw > roi_w:
            self._logger.debug(
                "[角标检测] 模板(%sx%s) 大于 ROI(%sx%s)",
                tw, th, roi_w, roi_h,
            )
            return []

        result = cv2.matchTemplate(roi_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        self._logger.info(
            "[角标检测] ROI尺寸=%sx%s 模板=%sx%s 最高置信度=%.4f 阈值=%.2f",
            roi_w, roi_h, tw, th, max_val, self._threshold,
        )

        if max_val < self._threshold:
            self._logger.debug("[角标检测] 最高置信度 %.4f < 阈值 %.2f，无匹配", max_val, self._threshold)
            return []

        # 收集所有超过阈值的匹配（含置信度）
        raw_matches = []
        locations = np.where(result >= self._threshold)
        for ry, rx in zip(locations[0].tolist(), locations[1].tolist()):
            conf = float(result[ry, rx])
            cx_roi = rx + tw // 2
            cy_roi = ry + th // 2
            raw_matches.append((cx_roi, cy_roi, conf))

        if not raw_matches:
            return []

        # NMS 去重（按置信度降序，保留不重叠的）
        nms_dist = max(tw, th) // 2
        kept = []
        for item in sorted(raw_matches, key=lambda m: m[2], reverse=True):
            cx, cy, conf = item
            is_dup = any(
                abs(cx - k[0]) <= nms_dist and abs(cy - k[1]) <= nms_dist
                for k in kept
            )
            if not is_dup:
                kept.append(item)
                self._logger.debug(
                    "[角标检测] 保留匹配: ROI坐标(%s,%s) 置信度=%.4f",
                    cx, cy, conf,
                )

        # 转换到全屏坐标
        matches = [(cx + x1, cy + y1) for cx, cy, _ in kept]

        self._logger.info(
            "[角标检测] ROI(%s,%s,%s,%s) 内找到 %s 个有效匹配（去重后）",
            x1, y1, x2, y2, len(matches),
        )
        return matches

    # ---- 角标检测（已废弃，保留兼容）----

    def _detect_badges(self, screen: np.ndarray) -> list[tuple[int, int]]:
        """在活动列表区域检测奖励角标（兼容接口，内部调用模板匹配）

        从 templates.json 读 jllq.png crop_region 作为 ROI，
        在 ROI 内用 jllq-hb.png 模板匹配找角标。

        Returns:
            [(cx, cy), ...] 角标中心坐标列表（全屏坐标）
        """
        return self._match_badge_in_roi(screen)

    def _detect_badges_fullscreen(self, screen: np.ndarray) -> list[tuple[int, int]]:
        """全屏检测奖励角标（用于奖励详情页）

        不依赖 jllq.png ROI，直接在整张截图中扫描红色像素，
        用 key_colors 多点像素对比定位角标。

        Returns:
            [(cx, cy), ...] 角标中心坐标列表（全屏坐标）
        """
        h, w = screen.shape[:2]
        if not self._badge_key_colors:
            self._logger.debug("[全屏检测] key_colors 未加载")
            return []

        key_colors = self._badge_key_colors[0]
        n_pts = len(key_colors)
        min_pass = max(3, int(n_pts * 0.6))
        tolerance = 35

        self._logger.info(
            "[全屏检测] 截图=%sx%s key_colors=%s点 需通过>=%s点",
            w, h, n_pts, min_pass,
        )

        # 红色预过滤
        r_ch = screen[:, :, 2].astype(np.int16)
        g_ch = screen[:, :, 1].astype(np.int16)
        b_ch = screen[:, :, 0].astype(np.int16)
        red_mask = (r_ch > 150) & (g_ch < 80) & (b_ch < 80)
        red_positions = np.where(red_mask)
        red_count = len(red_positions[0])

        self._logger.debug("[全屏检测] 红色预过滤: %s 个红色像素", red_count)
        if red_count == 0:
            return []

        matches: list[tuple[int, int]] = []
        checked = 0
        for ry, rx in zip(red_positions[0].tolist(),
                          red_positions[1].tolist()):
            cx, cy = rx, ry

            passed = 0
            for pt in key_colors:
                px = cx + pt["rel_x"]
                py = cy + pt["rel_y"]
                if 0 <= px < w and 0 <= py < h:
                    b = int(screen[py, px, 0])
                    g = int(screen[py, px, 1])
                    r = int(screen[py, px, 2])
                    if (abs(b - pt["b"]) <= tolerance
                            and abs(g - pt["g"]) <= tolerance
                            and abs(r - pt["r"]) <= tolerance):
                        passed += 1

            checked += 1
            if passed >= min_pass:
                matches.append((cx, cy))
                self._logger.debug(
                    "[全屏检测] 角标候选: (%s,%s) 通过 %s/%s 点",
                    cx, cy, passed, n_pts,
                )

        # 去重
        if len(matches) > 1:
            deduped: list[tuple[int, int]] = []
            for m in matches:
                is_dup = any(
                    abs(m[0] - d[0]) <= 10 and abs(m[1] - d[1]) <= 10
                    for d in deduped
                )
                if not is_dup:
                    deduped.append(m)
            matches = deduped

        self._logger.info(
            "[全屏检测] 扫描完成: 检查 %s 个红色像素, 找到 %s 个角标",
            checked, len(matches),
        )
        return matches

    # ---- 关闭按钮模板匹配 ----

    def _match_template(self, screen: np.ndarray, template):
        """单模板匹配（返回最佳命中）

        Returns:
            (hit: bool, pos: tuple|None)
        """
        if template is None:
            self._logger.debug("[模板匹配] 模板为 None，跳过")
            return False, None

        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        th_t, tw_t = tpl_gray.shape[:2]
        result = cv2.matchTemplate(
            screen_gray, tpl_gray, cv2.TM_CCOEFF_NORMED
        )
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        self._logger.debug(
            "[模板匹配] 模板%dx%d 置信度=%.4f 阈值=%.2f 命中=%s",
            tw_t, th_t, max_val, self._threshold, max_val >= self._threshold,
        )
        if max_val >= self._threshold:
            cx = max_loc[0] + tw_t // 2
            cy = max_loc[1] + th_t // 2
            return True, (cx, cy)
        return False, None

    # ---- 模板加载 ----

    def _load_templates(self):
        """加载关闭按钮和角标模板图片"""
        template_map = {
            "close2": self.TEMPLATE_CLOSE2,
            "close3": self.TEMPLATE_CLOSE3,
            "back": self.TEMPLATE_BACK,
            "badge": self.TEMPLATE_BADGE,
        }
        for name, filename in template_map.items():
            path = os.path.join(_TEMPLATES_DIR, filename)
            if not os.path.exists(path):
                raise FileNotFoundError(f"模板图片不存在: {path}")
            img = cv2.imread(path)
            if img is None:
                raise RuntimeError(f"模板图片读取失败: {path}")
            h, w = img.shape[:2]
            self._logger.info(
                "setup: 模板已加载: %s (%sx%s)", filename, w, h,
            )
            if name == "close2":
                self._tpl_close2 = img
            elif name == "close3":
                self._tpl_close3 = img
            elif name == "back":
                self._tpl_back = img
            else:
                self._tpl_badge = img

    def _load_templates_from_json(self):
        """从 templates.json 读取 jllq.png crop_region 和 jllq-hb.png key_colors。

        jllq.png：读取 crop_region 定位活动列表 ROI。
        jllq-hb.png：读取 key_colors（相对偏移+期望BGR）在 ROI 内多点像素对比找角标。
        """
        if not os.path.exists(_TEMPLATES_JSON):
            self._logger.warning(
                "templates.json 不存在: %s", _TEMPLATES_JSON,
            )
            return

        with open(_TEMPLATES_JSON, encoding="utf-8") as f:
            templates = json.load(f)

        # ── 读 jllq.png crop_region ──────────────────────────
        for entry in templates:
            if entry.get("image_file") == "jllq.png":
                crop = entry["crop_region"]
                self._jllq_crop_region = (
                    crop["x1"], crop["y1"], crop["x2"], crop["y2"],
                )
                self._logger.info(
                    "setup: jllq.png crop_region = %s", self._jllq_crop_region,
                )
                break

        if self._jllq_crop_region is None:
            self._logger.warning(
                "templates.json 中未找到 jllq.png 条目",
            )

        # ── 读 jllq-hb.png key_colors（多点像素验证用）────
        # key_colors 中的 (x, y) 是相对于角标模板图片的偏移
        # rgb 存的是 [R, G, B]，转 cv2 的 BGR 顺序
        self._badge_key_colors: list[dict] = []
        for entry in templates:
            if entry.get("image_file") == "jllq-hb.png":
                kc = entry.get("key_colors", {})
                points = []
                for pt_name in ("top_left", "top_right",
                               "bottom_left", "bottom_right", "center"):
                    if pt_name not in kc:
                        continue
                    p = kc[pt_name]
                    points.append({
                        "rel_x": int(p["x"]),
                        "rel_y": int(p["y"]),
                        # rgb -> bgr
                        "b": int(p["rgb"][2]),
                        "g": int(p["rgb"][1]),
                        "r": int(p["rgb"][0]),
                    })
                if points:
                    self._badge_key_colors.append(points)
                    self._logger.info(
                        "setup: jllq-hb.png key_colors 加载 %s 点", len(points),
                    )

        if not self._badge_key_colors:
            self._logger.warning(
                "templates.json 中未找到 jllq-hb.png 条目",
            )

    def annotate_detection(
        self,
        screen: np.ndarray,
        action,
    ) -> np.ndarray:
        """绘制自动领取奖励检测标注"""
        canvas = screen.copy()

        # 调用基类绘制任务名和动作
        canvas = super().annotate_detection(screen, action)

        h, w = canvas.shape[:2]

        # 绘制状态标签
        state_text = f"状态: {self._state.name}"
        if self._state == _State.CLAIMING_REWARD:
            state_color = (100, 200, 255)  # 蓝色
        elif self._state == _State.CLOSING:
            state_color = (0, 200, 200)  # 青色
        elif self._state == _State.DONE:
            state_color = (150, 150, 150)  # 灰色
        else:
            state_color = (200, 200, 100)  # 黄色
        cv2.putText(canvas, state_text, (8, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    state_color, 1, cv2.LINE_AA)

        # 绘制活动列表 ROI（jllq.png 区域，绿色矩形）
        if self._jllq_crop_region:
            x1, y1, x2, y2 = self._jllq_crop_region
            cv2.rectangle(canvas,
                          (x1, y1), (x2, y2),
                          (0, 255, 0), 1)
            cv2.putText(canvas, "活动列表ROI", (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                        (0, 255, 0), 1, cv2.LINE_AA)

        # 绘制角标模板尺寸（如果有）
        if self._tpl_badge is not None:
            tpl_h, tpl_w = self._tpl_badge.shape[:2]
            cv2.putText(canvas,
                        f"角标模板: {tpl_w}x{tpl_h}",
                        (w - 180, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                        (200, 200, 200), 1, cv2.LINE_AA)

        # 绘制关闭按钮位置提示
        cv2.putText(canvas,
                    "关闭按钮: close2/close3 全图检测",
                    (w - 280, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                    (150, 150, 150), 1, cv2.LINE_AA)

        return canvas
