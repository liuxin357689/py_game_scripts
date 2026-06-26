"""
OCR 图像识别模块

提供图像处理和文字识别功能：
    - 模板匹配（彩色/灰度）
    - OCR 文字识别（基于 PaddleOCR）
    - 颜色检测
    - 图像预处理
"""

from .recognizer import Recognizer, OCRResult

__all__ = ["Recognizer", "OCRResult"]
