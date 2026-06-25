"""
OCR 识别器

职责:
    - 图像模板匹配
    - 文字识别（OCR）— 基于 PaddleOCR
    - 颜色检测
    - 图像预处理

OCR 功能说明:
    - 首次调用 OCR 方法时自动加载 PaddleOCR 引擎（约 1-2 秒）
    - 引擎实例会被缓存，后续调用无额外加载开销
    - 默认使用中文模型（ch），支持中英文混合识别
    - CPU 模式，无需 GPU
"""

import logging
import re
import time
import cv2
import numpy as np
from typing import Optional, Tuple, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    """OCR 识别结果"""
    text: str                           # 识别出的文字
    confidence: float                   # 置信度 (0-1)
    box: Tuple[int, int, int, int]      # 文字边界框 (x, y, w, h)
    center: Tuple[int, int]             # 文字中心点 (cx, cy)

    def __repr__(self):
        return f'OCRResult(text="{self.text}", conf={self.confidence:.2f}, box={self.box})'


class Recognizer:
    """图像识别器，提供模板匹配和 OCR 功能"""

    def __init__(self, cache_ttl: float = 1800, ocr_lang: str = "ch"):
        """初始化识别器

        Args:
            cache_ttl: 模板缓存过期时间（秒），默认 30 分钟
            ocr_lang: OCR 识别语言，默认 "ch"（中英文混合）
                      可选: "en"（纯英文）, "ch"（中英文）等
        """
        self._templates_cache: dict[str, Tuple[np.ndarray, float]] = {}
        self._grayscale_templates_cache: dict[str, Tuple[np.ndarray, float]] = {}
        self._cache_ttl = cache_ttl
        self._ocr_engine = None          # PaddleOCR 实例（懒加载）
        self._ocr_lang = ocr_lang

    def _load_image(self, image_data) -> np.ndarray:
        """统一加载图片为 numpy array

        Args:
            image_data: 可以是 bytes、numpy array 或文件路径字符串

        Returns:
            BGR 格式的 numpy array
        """
        if isinstance(image_data, np.ndarray):
            return image_data
        elif isinstance(image_data, bytes):
            arr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError("无法解码图片数据")
            return img
        elif isinstance(image_data, str):
            img = cv2.imread(image_data)
            if img is None:
                raise FileNotFoundError(f"找不到图片文件: {image_data}")
            return img
        else:
            raise TypeError(f"不支持的图片数据类型: {type(image_data)}")

    def _load_template(self, template_path: str) -> np.ndarray:
        """加载并缓存模板图片（带 TTL 过期）

        Args:
            template_path: 模板图片路径

        Returns:
            BGR 格式的 numpy array
        """
        now = time.time()
        cached = self._templates_cache.get(template_path)
        if cached is not None:
            img, ts = cached
            if now - ts < self._cache_ttl:
                return img
            # 过期，删除旧缓存
            del self._templates_cache[template_path]

        img = cv2.imread(template_path)
        if img is None:
            raise FileNotFoundError(f"找不到模板文件: {template_path}")
        self._templates_cache[template_path] = (img, now)
        return img

    def find_template(
        self,
        screenshot,
        template_path: str,
        threshold: float = 0.8,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> Optional[Tuple[int, int, int, int]]:
        """在截图中查找模板图像

        Args:
            screenshot: 截图数据（bytes、numpy array 或文件路径）
            template_path: 模板图片路径
            threshold: 匹配阈值（0-1），越高越严格
            region: 搜索区域 (x, y, w, h)，None 表示全图

        Returns:
            匹配位置 (x, y, w, h) 或 None
        """
        try:
            screen_img = self._load_image(screenshot)
            template_img = self._load_template(template_path)

            # 如果指定了区域，裁剪截图并记录偏移
            offset_x = 0
            offset_y = 0
            if region is not None:
                rx, ry, rw, rh = region
                offset_x = rx
                offset_y = ry
                screen_img = screen_img[ry : ry + rh, rx : rx + rw]

            # 检查模板尺寸是否超过截图
            if (
                template_img.shape[0] > screen_img.shape[0]
                or template_img.shape[1] > screen_img.shape[1]
            ):
                logger.warning(f"模板尺寸大于截图，无法匹配")
                return None

            # 模板匹配
            result = cv2.matchTemplate(screen_img, template_img, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            if max_val >= threshold:
                th, tw = template_img.shape[:2]
                # 加上区域偏移量
                final_x = max_loc[0] + offset_x
                final_y = max_loc[1] + offset_y
                return (final_x, final_y, tw, th)
            else:
                return None

        except Exception as e:
            logger.error(f"模板匹配异常: {e}", exc_info=True)
            return None

    def find_all_templates(
        self,
        screenshot,
        template_path: str,
        threshold: float = 0.8,
        overlap_threshold: float = 0.5,
    ) -> List[Tuple[int, int, int, int]]:
        """在截图中查找所有匹配的模板图像

        Args:
            screenshot: 截图数据
            template_path: 模板图片路径
            threshold: 匹配阈值
            overlap_threshold: 重叠度阈值，过滤重复结果

        Returns:
            匹配位置列表 [(x, y, w, h), ...]
        """
        try:
            screen_img = self._load_image(screenshot)
            template_img = self._load_template(template_path)

            result = cv2.matchTemplate(screen_img, template_img, cv2.TM_CCOEFF_NORMED)
            locations = np.where(result >= threshold)

            points = []
            th, tw = template_img.shape[:2]
            for pt in zip(*locations[::-1]):
                x, y = pt
                # 简单去重：检查是否与已有结果重叠过多
                is_duplicate = False
                for px, py, pw, ph in points:
                    # 计算重叠面积比例
                    if (
                        abs(x - px) < tw * overlap_threshold
                        and abs(y - py) < th * overlap_threshold
                    ):
                        is_duplicate = True
                        break
                if not is_duplicate:
                    points.append((x, y, tw, th))

            return points

        except Exception as e:
            logger.error(f"多目标模板匹配异常: {e}", exc_info=True)
            return []

    def _load_grayscale_template(self, template_path: str) -> np.ndarray:
        """加载并缓存灰度模板图片（带 TTL 过期）

        Args:
            template_path: 模板图片路径

        Returns:
            灰度格式的 numpy array
        """
        now = time.time()
        cached = self._grayscale_templates_cache.get(template_path)
        if cached is not None:
            img, ts = cached
            if now - ts < self._cache_ttl:
                return img
            del self._grayscale_templates_cache[template_path]

        img = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise FileNotFoundError(f"找不到模板文件: {template_path}")
        self._grayscale_templates_cache[template_path] = (img, now)
        return img

    def find_template_grayscale(
        self,
        screen_gray: np.ndarray,
        template_path: str,
        threshold: float = 0.8,
    ) -> Optional[Tuple[int, int, int, int]]:
        """使用灰度图查找模板（更快，适用于 UI 按钮等形状匹配场景）

        Args:
            screen_gray: 灰度格式的截图 (numpy array)
            template_path: 模板图片路径
            threshold: 匹配阈值（0-1）

        Returns:
            匹配位置 (x, y, w, h) 或 None
        """
        try:
            template_gray = self._load_grayscale_template(template_path)

            if (template_gray.shape[0] > screen_gray.shape[0]
                    or template_gray.shape[1] > screen_gray.shape[1]):
                return None

            result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            if max_val >= threshold:
                th, tw = template_gray.shape[:2]
                return (max_loc[0], max_loc[1], tw, th)
            return None

        except Exception as e:
            logger.error(f"灰度模板匹配异常: {e}", exc_info=True)
            return None

    def clear_cache(self):
        """手动清除所有模板缓存"""
        self._templates_cache.clear()
        self._grayscale_templates_cache.clear()
        logger.debug("模板缓存已清除")

    # ================================================================
    # OCR 文字识别（基于 PaddleOCR）
    # ================================================================

    def _get_ocr_engine(self):
        """获取 PaddleOCR 引擎实例（懒加载，首次调用时初始化）

        Returns:
            PaddleOCR 实例

        Raises:
            ImportError: PaddleOCR 未安装
        """
        if self._ocr_engine is not None:
            return self._ocr_engine

        try:
            from paddleocr import PaddleOCR

            logger.info(f"正在初始化 PaddleOCR 引擎 (lang={self._ocr_lang}, CPU 模式)...")
            start = time.time()

            self._ocr_engine = PaddleOCR(
                use_angle_cls=True,       # 启用文字方向分类（旋转文字识别）
                lang=self._ocr_lang,       # 中文 + 英文
                use_gpu=False,             # CPU 模式
                show_log=False,            # 静默模式
                use_space_char=True,       # 识别空格
                drop_score=0.3,            # 丢弃低置信度结果
            )

            elapsed = time.time() - start
            logger.info(f"PaddleOCR 引擎初始化完成，耗时 {elapsed:.1f} 秒")
            return self._ocr_engine

        except ImportError:
            raise ImportError(
                "PaddleOCR 未安装，请执行:\n"
                "  pip install paddlepaddle paddleocr\n"
                "详见: https://github.com/PaddlePaddle/PaddleOCR"
            )

    def _prepare_ocr_image(self, screenshot, region: tuple = None) -> np.ndarray:
        """准备用于 OCR 的图像（裁剪区域 + 转 RGB）

        Args:
            screenshot: 截图数据（bytes、numpy array 或文件路径）
            region: 识别区域 (x1, y1, x2, y2)，注意这里是绝对坐标，None 表示全图

        Returns:
            RGB 格式的 numpy array
        """
        img = self._load_image(screenshot)  # BGR

        if region is not None:
            x1, y1, x2, y2 = region
            img = img[y1:y2, x1:x2]

        # PaddleOCR 需要 RGB 格式
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return img_rgb

    @staticmethod
    def _parse_paddle_results(paddle_result, offset_x: int = 0, offset_y: int = 0) -> List[OCRResult]:
        """解析 PaddleOCR 原始结果为 OCRResult 列表

        Args:
            paddle_result: PaddleOCR.ocr() 返回的原始结果
            offset_x: X 方向偏移（区域裁剪时加回绝对坐标）
            offset_y: Y 方向偏移

        Returns:
            OCRResult 列表
        """
        results = []

        if not paddle_result or not paddle_result[0]:
            return results

        for line in paddle_result[0]:
            box = line[0]          # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            text = line[1][0]      # 识别文字
            confidence = line[1][1] # 置信度

            # 计算边界框 (x, y, w, h) 和中心点
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            x_min = int(min(xs)) + offset_x
            y_min = int(min(ys)) + offset_y
            x_max = int(max(xs)) + offset_x
            y_max = int(max(ys)) + offset_y
            w = x_max - x_min
            h = y_max - y_min
            cx = x_min + w // 2
            cy = y_min + h // 2

            results.append(OCRResult(
                text=text,
                confidence=confidence,
                box=(x_min, y_min, w, h),
                center=(cx, cy),
            ))

        return results

    def recognize_all(self, screenshot, region: tuple = None) -> List[OCRResult]:
        """识别截图中所有文字，返回详细结果（含位置、置信度）

        Args:
            screenshot: 截图数据（bytes、numpy array 或文件路径）
            region: 识别区域 (x1, y1, x2, y2)，None 表示全图

        Returns:
            OCRResult 列表，每个元素包含 text/confidence/box/center
        """
        try:
            ocr = self._get_ocr_engine()

            offset_x, offset_y = 0, 0
            if region is not None:
                offset_x, offset_y = region[0], region[1]

            img_rgb = self._prepare_ocr_image(screenshot, region)

            start = time.time()
            result = ocr.ocr(img_rgb, cls=True)
            elapsed = time.time() - start

            ocr_results = self._parse_paddle_results(result, offset_x, offset_y)
            logger.debug(
                f"OCR 识别完成: 发现 {len(ocr_results)} 处文字, "
                f"耗时 {elapsed * 1000:.0f}ms"
            )
            return ocr_results

        except ImportError:
            raise
        except Exception as e:
            logger.error(f"OCR 识别异常: {e}", exc_info=True)
            return []

    def recognize_text(self, screenshot, region: tuple = None) -> str:
        """识别截图中的文字

        Args:
            screenshot: 截图数据（bytes、numpy array 或文件路径）
            region: 识别区域 (x1, y1, x2, y2)，None 表示全图

        Returns:
            识别出的文字内容（多行用换行符连接），未识别到返回空字符串
        """
        results = self.recognize_all(screenshot, region)
        if not results:
            return ""
        # 按 Y 坐标排序（从上到下），同行按 X 排序（从左到右）
        sorted_results = sorted(results, key=lambda r: (r.box[1], r.box[0]))
        return "\n".join(r.text for r in sorted_results)

    def find_text(
        self,
        screenshot,
        target_text: str,
        region: tuple = None,
        partial: bool = False,
        min_confidence: float = 0.5,
    ) -> Optional[OCRResult]:
        """在截图中查找指定文字，返回其位置信息

        Args:
            screenshot: 截图数据
            target_text: 要查找的文字
            region: 识别区域 (x1, y1, x2, y2)，None 表示全图
            partial: True=包含匹配（"攻击"匹配"自动攻击"），False=精确匹配
            min_confidence: 最低置信度阈值

        Returns:
            匹配到的 OCRResult（含 center 可用于点击），未找到返回 None

        用法示例:
            # 精确查找"开始战斗"按钮
            result = recognizer.find_text(screenshot, "开始战斗")
            if result:
                device.tap(result.center[0], result.center[1])

            # 模糊查找包含"金币"的文字
            result = recognizer.find_text(screenshot, "金币", partial=True)
        """
        results = self.recognize_all(screenshot, region)

        for r in results:
            if r.confidence < min_confidence:
                continue
            if partial and target_text in r.text:
                return r
            elif not partial and r.text.strip() == target_text.strip():
                return r

        logger.debug(f"OCR 未找到文字: '{target_text}' (partial={partial})")
        return None

    def find_all_text(
        self,
        screenshot,
        target_text: str,
        region: tuple = None,
        partial: bool = False,
        min_confidence: float = 0.5,
    ) -> List[OCRResult]:
        """在截图中查找所有匹配的文字

        Args:
            screenshot: 截图数据
            target_text: 要查找的文字
            region: 识别区域 (x1, y1, x2, y2)，None 表示全图
            partial: True=包含匹配，False=精确匹配
            min_confidence: 最低置信度阈值

        Returns:
            所有匹配到的 OCRResult 列表
        """
        results = self.recognize_all(screenshot, region)
        matched = []

        for r in results:
            if r.confidence < min_confidence:
                continue
            if partial and target_text in r.text:
                matched.append(r)
            elif not partial and r.text.strip() == target_text.strip():
                matched.append(r)

        return matched

    def text_exists(
        self,
        screenshot,
        target_text: str,
        region: tuple = None,
        partial: bool = False,
        min_confidence: float = 0.5,
    ) -> bool:
        """判断截图中是否存在指定文字

        Args:
            screenshot: 截图数据
            target_text: 要查找的文字
            region: 识别区域 (x1, y1, x2, y2)，None 表示全图
            partial: True=包含匹配，False=精确匹配
            min_confidence: 最低置信度阈值

        Returns:
            是否存在

        用法示例:
            # 检查是否弹出"确认退出"对话框
            if recognizer.text_exists(screenshot, "确认退出"):
                device.tap(300, 500)  # 点击确认
        """
        result = self.find_text(screenshot, target_text, region, partial, min_confidence)
        return result is not None

    def read_number(
        self,
        screenshot,
        region: tuple,
        pattern: str = r'\d+',
    ) -> Optional[int]:
        """从截图指定区域读取数字

        Args:
            screenshot: 截图数据
            region: 识别区域 (x1, y1, x2, y2)，必填（限定区域提升速度和准确性）
            pattern: 正则表达式，默认匹配第一个整数

        Returns:
            识别到的整数，未找到返回 None

        用法示例:
            # 读取金币数量（金币图标右侧区域）
            gold = recognizer.read_number(screenshot, region=(200, 50, 400, 80))

            # 读取关卡编号（如 "1-5" 中的数字）
            level = recognizer.read_number(screenshot, region=(300, 100, 450, 130), pattern=r'(\d+)')
        """
        text = self.recognize_text(screenshot, region)
        if not text:
            return None

        # 清理常见 OCR 噪音字符
        cleaned = text.replace(' ', '').replace('O', '0').replace('o', '0')
        cleaned = cleaned.replace('l', '1').replace('I', '1')

        match = re.search(pattern, cleaned)
        if match:
            try:
                return int(match.group())
            except ValueError:
                logger.debug(f"数字解析失败: '{match.group()}' (原文: '{text}')")
                return None

        logger.debug(f"区域 {region} 中未找到数字: '{text}'")
        return None

    def detect_color(self, screenshot, x: int, y: int) -> tuple:
        """检测指定坐标的像素颜色

        Args:
            screenshot: 截图数据
            x: X 坐标
            y: Y 坐标

        Returns:
            RGB 颜色值 (r, g, b)
        """
        try:
            img = self._load_image(screenshot)
            # OpenCV 使用 BGR 格式
            b, g, r = img[y, x]
            return (int(r), int(g), int(b))
        except Exception as e:
            logger.error(f"颜色检测异常: {e}")
            return (0, 0, 0)
