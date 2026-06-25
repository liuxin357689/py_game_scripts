"""
暗能秘境任务（帧任务版）

截图共享架构：不自行截图，由 ScreenshotService 推送帧画面。
只实现 on_frame(screen) 返回 TapAction 或 None。

状态机：
    LOOKING_CHALLENGE  → 检测挑战按钮 → 点击 → IN_BATTLE
    IN_BATTLE          → 持续检测光球(点击) + 战斗结果(结束战斗)
                         └─ 战斗结束（无论胜/负）→ 关闭结算 → CHECKING_NEW_LEVEL
    CHECKING_NEW_LEVEL → 连续检测15帧 → 点击新关卡(有) / 回挑战按钮(无)

核心设计：
    IN_BATTLE 状态中，每帧同时检测星级光圈和战斗结果。
    光圈出现就点，不切换到其他状态，直到战斗结束。
    战斗结束后，无论胜利还是失败，统一流程：关闭 → 连续检测15帧新关卡 → 有则点，无则回挑战按钮。

模板来源: game_platform/screenshot/templates/
坐标数据: game_platform/screenshot/templates/templates.json
"""

import json
import logging
import os
from enum import Enum, auto

import cv2
import numpy as np

from game_platform.task.frame_task import FrameTask, TapAction
from hero_afk.core.battle_detector import battle_detector

logger = logging.getLogger(__name__)

# 模板资源目录
_TEMPLATES_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..", "game_platform", "screenshot", "templates",
))


class _State(Enum):
    """暗能秘境内部状态"""
    LOOKING_CHALLENGE = auto()
    IN_BATTLE = auto()
    CHECKING_NEW_LEVEL = auto()


class AutoDarkRealm(FrameTask):
    """暗能秘境 — 帧任务版

    星星计数 + 模板匹配 + 像素点检测，
    所有截图由 ScreenshotService 推送。
    """

    # 模板匹配目标
    TEMPLATE_CHALLENGE = "anmj-tz.png"   # 挑战按钮
    TEMPLATE_STAR = "anmj-xing.png"      # 单颗星星
    TEMPLATE_REVIVE = "anmj-fh.png"      # 复活按钮

    # 像素检测目标（从 templates.json 加载）— 仅保留仍需像素检测的
    _PIXEL_TARGETS = {
        "new_level": {
            "file": "anmj-new.png",
            "description": "新关卡提示",
        },
    }

    # 光球点击的 y 坐标
    _ORB_CLICK_Y = 650

    # 星星聚类 x 方向最大间距
    _STAR_GROUP_GAP = 200

    # 星星匹配最小间距（NMS 去重）
    _STAR_MIN_DIST = 25

    # 星星检测 ROI
    _STAR_ROI = {"x1": 156, "y1": 477, "x2": 788, "y2": 550}

    # 新关卡检测：连续15帧未发现则回挑战按钮
    _NEW_LEVEL_CHECK_COUNT = 15

    # 星星位置确认：连续2帧位置一致（±tolerance）才点击
    _STAR_POS_TOLERANCE = 10
    _STAR_CONFIRM_FRAMES = 2

    def __init__(
        self,
        threshold: float = 0.7,
        star_threshold: float = 0.70,
        pixel_tolerance: int = 40,
    ):
        """
        Args:
            threshold: 模板匹配置信度阈值（挑战按钮等常规模板）
            star_threshold: 星星模板阈值，模板小且背景不固定
            pixel_tolerance: 像素颜色容差
        """
        super().__init__(name="暗能秘境", priority=20)
        self._threshold = threshold
        self._star_threshold = star_threshold
        self._pixel_tolerance = pixel_tolerance

        # 模板和配置
        self._tpl_challenge = None
        self._tpl_star = None
        self._tpl_revive = None
        self._pixel_config: dict = {}

        # 状态机
        self._state = _State.LOOKING_CHALLENGE
        self._pending_state = None  # 动作执行后才切换的下一个状态
        self._click_count = 0

        # 等待帧计数（超时保护）
        self._wait_frames = 0
        # 新关卡检测帧计数（连续检测）
        self._new_level_check_count = 0
        self._MAX_WAIT = 180  # 120帧超时

        # 星星位置确认（连续2帧位置一致才点击）
        self._pending_star_x = None
        self._star_confirm_count = 0

    def activate(self):
        """激活任务 — 重置状态机，确保重启后从初始状态开始"""
        super().activate()
        self._state = _State.LOOKING_CHALLENGE
        self._pending_state = None
        self._wait_frames = 0
        self._new_level_check_count = 0
        self._pending_star_x = None
        self._star_confirm_count = 0
        self._logger.info("状态已重置 -> LOOKING_CHALLENGE")

    # ---- 生命周期 ----

    def setup(self):
        """加载模板和像素检测配置"""
        self._load_templates()
        self._load_pixel_config()
        battle_detector.setup()

    def teardown(self):
        """清理"""
        self._logger.info(
            f"暗能秘境结束, 累计点击 {self._click_count} 次"
        )

    # ---- 帧处理 ----

    def on_frame(self, screen: np.ndarray):
        """处理一帧：根据当前状态执行对应检测

        Returns:
            TapAction 或 None
        """
        if self._state == _State.LOOKING_CHALLENGE:
            return self._handle_challenge(screen)

        elif self._state == _State.IN_BATTLE:
            return self._handle_battle(screen)

        elif self._state == _State.CHECKING_NEW_LEVEL:
            return self._handle_new_level(screen)

        return None

    def on_action_executed(self, action):
        """动作执行后：应用挂起的状态切换 + 更新计数

        状态切换在动作执行后才生效，确保屏幕已响应点击。
        """
        self._click_count += 1
        if self._pending_state is not None:
            old = self._state
            self._state = self._pending_state
            self._pending_state = None
            self._wait_frames = 0
            # 进入战斗状态时重置星星确认
            if self._state == _State.IN_BATTLE:
                self._pending_star_x = None
                self._star_confirm_count = 0
            self._logger.info(
                f"动作已执行, 状态切换: {old.name} -> {self._state.name}"
            )

    def _on_state_transition(self, new_state: _State):
        """登记状态切换，在动作执行后生效

        状态不在 on_frame 中直接切换，而是在 on_action_executed 中
        应用，确保屏幕已响应点击后再进入下一个状态。
        """
        self._pending_state = new_state

    # ---- 状态处理 ----

    def _handle_challenge(self, screen: np.ndarray):
        """检测挑战按钮 → 点击进入战斗"""
        hit, pos = self._detect_challenge_btn(screen)
        if hit:
            self._logger.info(f"检测到挑战按钮: {pos}, 准备进入战斗")
            self._on_state_transition(_State.IN_BATTLE)
            return TapAction(pos[0], pos[1], description="点击挑战按钮")
        return None

    def _handle_battle(self, screen: np.ndarray):
        """战斗状态 — 每帧同时检测复活按钮、光球和战斗结果

        核心逻辑：
            1. 优先检测战斗结果（胜利/失败）→ 结束战斗
            2. 检测复活按钮 → 点击（不限次数，留在 IN_BATTLE）
            3. 否则检测星级光圈 → 点击最多星的光球（不切换状态，继续留在 IN_BATTLE）
            4. 都没检测到 → 等待下一帧

        超时保护：超过 _MAX_WAIT 帧无任何操作，回退到挑战按钮。
        """
        # ① 检测战斗结果（优先级高于光球 — 战斗结束立即退出）
        result = battle_detector.detect(screen)
        if result:
            return self._process_battle_result(result)

        # ② 检测复活按钮（出现就点，不限次数，留在 IN_BATTLE）
        hit, pos = self._detect_revive_btn(screen)
        if hit:
            self._logger.info(f"检测到复活按钮: {pos}")
            self._wait_frames = 0
            return TapAction(pos[0], pos[1], description="点击复活按钮")

        # ③ 检测星级光圈（战斗中持续检测，连续2帧位置一致才点击）
        groups = self._detect_and_group_stars(screen)
        if groups:
            best = groups[0]
            click_x = best["center_x"]
            click_y = self._ORB_CLICK_Y

            if self._pending_star_x is not None:
                # 已有记录，对比位置
                if abs(click_x - self._pending_star_x) <= self._STAR_POS_TOLERANCE:
                    self._star_confirm_count += 1
                    if self._star_confirm_count >= self._STAR_CONFIRM_FRAMES:
                        self._logger.info(
                            "确认通过，点击 %s 星光球(x=%s)",
                            best["count"], click_x,
                        )
                        self._pending_star_x = None
                        self._star_confirm_count = 0
                        self._wait_frames = 0
                        return TapAction(click_x, click_y, description="点击光球")
                else:
                    self._pending_star_x = click_x
                    self._star_confirm_count = 1
            else:
                # 第一帧记录位置
                self._pending_star_x = click_x
                self._star_confirm_count = 1
                self._logger.info(
                    "[星星确认] 第1帧，位置(x=%s)，等待下一帧确认", click_x
                )
            self._wait_frames = 0
            return None  # 未确认完成，不点击

        # ④ 都没检测到，累加超时计数
        self._wait_frames += 1
        if self._wait_frames > self._MAX_WAIT:
            self._logger.warning(
                f"战斗状态超时 ({self._wait_frames} 帧)，"
                f"回退到挑战按钮"
            )
            self._state = _State.LOOKING_CHALLENGE
            self._wait_frames = 0

        return None

    def _process_battle_result(self, result: str):
        """处理战斗结果 — 退出战斗状态（胜/负统一流程）"""
        self._logger.info("战斗结束: %s, 关闭结算", result)
        # 重置星星确认变量
        self._pending_star_x = None
        self._star_confirm_count = 0
        cx, cy = battle_detector.CLOSE_TAP_POS
        self._new_level_check_count = 0
        self._on_state_transition(_State.CHECKING_NEW_LEVEL)
        return TapAction(cx, cy, description="关闭结算")

    def _handle_new_level(self, screen: np.ndarray):
        """检测新关卡

        连续检测15帧 → 有则点击，无则回挑战按钮
        """
        hit = self._detect_target(screen, "new_level")
        self._logger.info(
            "[新关卡] %s/%s %s",
            self._new_level_check_count + 1, self._NEW_LEVEL_CHECK_COUNT,
            "检测到!" if hit else "未检测到",
        )

        if hit:
            cfg = self._pixel_config["new_level"]
            cx, cy = cfg["center"]
            self._logger.info(f"检测到新关卡，点击: ({cx}, {cy})")
            self._new_level_check_count = 0
            return TapAction(cx, cy, description="点击新关卡")

        self._new_level_check_count += 1
        if self._new_level_check_count >= self._NEW_LEVEL_CHECK_COUNT:
            self._logger.info("新关卡未发现，回到挑战按钮")
            self._state = _State.LOOKING_CHALLENGE
            self._new_level_check_count = 0

        return None

    # ---- 模板匹配 ----

    def _detect_challenge_btn(self, screen: np.ndarray):
        """模板匹配挑战按钮

        Returns:
            (hit: bool, pos: tuple|None)
        """
        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.cvtColor(self._tpl_challenge, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(
            screen_gray, tpl_gray, cv2.TM_CCOEFF_NORMED
        )
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= self._threshold:
            th, tw = tpl_gray.shape[:2]
            cx = max_loc[0] + tw // 2
            cy = max_loc[1] + th // 2
            return True, (cx, cy)
        return False, None

    def _detect_revive_btn(self, screen: np.ndarray):
        """模板匹配复活按钮（全图扫描）

        Returns:
            (hit: bool, pos: tuple|None)
        """
        if self._tpl_revive is None:
            return False, None
        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.cvtColor(self._tpl_revive, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(
            screen_gray, tpl_gray, cv2.TM_CCOEFF_NORMED
        )
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= self._threshold:
            th, tw = tpl_gray.shape[:2]
            cx = max_loc[0] + tw // 2
            cy = max_loc[1] + th // 2
            return True, (cx, cy)
        return False, None

    def _detect_and_group_stars(self, screen: np.ndarray) -> list:
        """检测 ROI 区域内的星星并按 x 坐标聚类分组"""
        roi = self._STAR_ROI
        x1, y1, x2, y2 = roi["x1"], roi["y1"], roi["x2"], roi["y2"]

        h, w = screen.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        if x2 <= x1 or y2 <= y1:
            return []

        roi_img = screen[y1:y2, x1:x2]
        roi_gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.cvtColor(self._tpl_star, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(
            roi_gray, tpl_gray, cv2.TM_CCOEFF_NORMED
        )

        locations = np.where(result >= self._star_threshold)
        if len(locations[0]) == 0:
            return []

        raw_positions = [
            (int(x + x1), int(y + y1), float(result[y, x]))
            for y, x in zip(locations[0].tolist(), locations[1].tolist())
        ]
        positions = self._non_max_suppression(raw_positions)

        if not positions:
            return []

        positions.sort(key=lambda p: p[0])

        groups = []
        current_group = [positions[0]]
        for i in range(1, len(positions)):
            if positions[i][0] - current_group[-1][0] > self._STAR_GROUP_GAP:
                groups.append(current_group)
                current_group = [positions[i]]
            else:
                current_group.append(positions[i])
        groups.append(current_group)

        result_groups = []
        for g in groups:
            xs = [p[0] for p in g]
            center_x = sum(xs) // len(xs)
            result_groups.append({
                "count": len(g),
                "center_x": center_x,
                "positions": g,
            })

        result_groups.sort(key=lambda g: g["count"], reverse=True)
        return result_groups

    def _non_max_suppression(self, positions: list) -> list:
        """基于置信度的非极大值抑制"""
        if not positions:
            return []
        positions.sort(key=lambda p: p[2], reverse=True)
        filtered = []
        for p in positions:
            too_close = False
            for f in filtered:
                dist = ((p[0] - f[0]) ** 2 + (p[1] - f[1]) ** 2) ** 0.5
                if dist < self._STAR_MIN_DIST:
                    too_close = True
                    break
            if not too_close:
                filtered.append(p)
        return filtered

    # ---- 像素检测 ----

    def _detect_target(self, screen: np.ndarray, key: str) -> bool:
        """多点像素检测指定目标"""
        cfg = self._pixel_config.get(key)
        if not cfg:
            return False

        h, w = screen.shape[:2]
        tol = self._pixel_tolerance

        for sp in cfg["sample_points"]:
            sx, sy = sp["abs_pos"]
            if sx >= w or sy >= h:
                return False
            b, g, r = screen[sy, sx]
            actual = (int(r), int(g), int(b))
            expected = sp["expected_rgb"]
            if not all(abs(a - e) <= tol for a, e in zip(actual, expected)):
                return False
        return True

    def annotate_detection(
        self,
        screen: np.ndarray,
        action,
    ) -> np.ndarray:
        """绘制暗能秘境检测标注"""
        canvas = screen.copy()

        # 调用基类绘制任务名和动作
        canvas = super().annotate_detection(screen, action)

        h, w = canvas.shape[:2]

        # 绘制状态标签
        state_text = f"状态: {self._state.name}"
        if self._state == _State.IN_BATTLE:
            state_color = (100, 200, 255)  # 蓝色
        elif self._state == _State.CHECKING_NEW_LEVEL:
            state_color = (0, 200, 200)  # 青色
        else:
            state_color = (200, 200, 100)  # 黄色
        cv2.putText(canvas, state_text, (8, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    state_color, 1, cv2.LINE_AA)

        # 绘制星星检测 ROI（绿色矩形）
        roi = self._STAR_ROI
        cv2.rectangle(canvas,
                      (roi["x1"], roi["y1"]),
                      (roi["x2"], roi["y2"]),
                      (0, 255, 0), 1)
        cv2.putText(canvas, "星星ROI", (roi["x1"], roi["y1"] - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (0, 255, 0), 1, cv2.LINE_AA)

        # 绘制新关卡检测区域（青色）
        if "new_level" in self._pixel_config:
            cfg = self._pixel_config["new_level"]
            cx, cy = cfg["center"]
            cv2.rectangle(canvas,
                          (cx - 30, cy - 30),
                          (cx + 30, cy + 30),
                          (0, 200, 200), 1)
            cv2.putText(canvas, "新关卡", (cx - 30, cy - 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                        (0, 200, 200), 1, cv2.LINE_AA)

        # 在 IN_BATTLE 状态绘制星星确认状态
        if self._state == _State.IN_BATTLE:
            if self._pending_star_x is not None:
                confirm_text = (
                    f"星星确认: {self._star_confirm_count}/{self._STAR_CONFIRM_FRAMES} "
                    f"位置x={self._pending_star_x}"
                )
            else:
                confirm_text = "星星: 等待检测"
            cv2.putText(canvas, confirm_text, (8, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (200, 150, 255), 1, cv2.LINE_AA)

        # 在 CHECKING_NEW_LEVEL 状态绘制检测进度
        if self._state == _State.CHECKING_NEW_LEVEL:
            progress_text = (
                f"新关卡检测: {self._new_level_check_count}/{self._NEW_LEVEL_CHECK_COUNT}"
            )
            cv2.putText(canvas, progress_text, (8, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (0, 200, 200), 1, cv2.LINE_AA)

        # 绘制复活按钮区域（如果有模板）
        if self._tpl_revive is not None:
            cv2.putText(canvas, "复活按钮: 全图检测",
                        (w - 180, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                        (150, 150, 150), 1, cv2.LINE_AA)

        return canvas

    # ---- 内部方法 ----

    def _load_templates(self):
        """加载模板图片"""
        template_map = {
            "challenge": self.TEMPLATE_CHALLENGE,
            "star": self.TEMPLATE_STAR,
            "revive": self.TEMPLATE_REVIVE,
        }
        for name, filename in template_map.items():
            path = os.path.join(_TEMPLATES_DIR, filename)
            if not os.path.exists(path):
                raise FileNotFoundError(f"模板图片不存在: {path}")
            img = cv2.imread(path)
            if img is None:
                raise RuntimeError(f"模板图片读取失败: {path}")
            h, w = img.shape[:2]
            self._logger.info(f"模板已加载: {filename} ({w}x{h})")
            if name == "challenge":
                self._tpl_challenge = img
            elif name == "star":
                self._tpl_star = img
            else:
                self._tpl_revive = img

    def _load_pixel_config(self):
        """从 templates.json 加载像素检测配置"""
        json_path = os.path.join(_TEMPLATES_DIR, "templates.json")
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"templates.json 不存在: {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            entries = json.load(f)

        by_file = {e["image_file"]: e for e in entries}

        for key, target in self._PIXEL_TARGETS.items():
            entry = by_file.get(target["file"])
            if not entry:
                raise RuntimeError(
                    f"templates.json 中未找到 "
                    f"{target['file']}（{target['description']}）"
                )
            cr = entry["crop_region"]
            cx = (cr["x1"] + cr["x2"]) // 2
            cy = (cr["y1"] + cr["y2"]) // 2

            sample_points = []
            for name, kc in entry["key_colors"].items():
                abs_x = cr["x1"] + kc["x"]
                abs_y = cr["y1"] + kc["y"]
                sample_points.append({
                    "name": name,
                    "abs_pos": (abs_x, abs_y),
                    "expected_rgb": tuple(kc["rgb"]),
                })

            self._pixel_config[key] = {
                "center": (cx, cy),
                "sample_points": sample_points,
                "description": target["description"],
            }
            self._logger.info(
                f"[{key}] {target['description']}: "
                f"中心 ({cx}, {cy}), {len(sample_points)} 个采样点"
            )
