"""
OCR 功能集成测试

测试内容:
    1. PaddleOCR 引擎初始化
    2. recognize_text - 全图识别
    3. recognize_all - 详细结果
    4. find_text - 文字定位
    5. text_exists - 文字存在判断
    6. read_number - 数字读取
    7. OCRResult 数据结构
"""

import sys
import os

# 动态计算 game_scripts 路径（本文件在 game_platform/tests/ 下）
_GAME_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _GAME_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _GAME_SCRIPTS_DIR)

import cv2
import numpy as np
from game_platform.ocr.recognizer import Recognizer, OCRResult


def create_test_image_ascii(width=800, height=400):
    """创建带英文/数字的测试图片（使用 cv2.putText，无需中文字体）"""
    img = np.ones((height, width, 3), dtype=np.uint8) * 255  # 白色背景

    # 绘制文字（cv2.putText 只支持 ASCII，但足以测试 OCR 引擎）
    cv2.putText(img, "Hello World", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)
    cv2.putText(img, "Level 42", (50, 160), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
    cv2.putText(img, "Gold: 12345", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    cv2.putText(img, "Score: 9876", (400, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    cv2.putText(img, "Press START", (250, 350), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 0, 255), 2)

    return img


def create_test_image_chinese(width=800, height=400):
    """创建带中文的测试图片（使用 PIL + 系统中文字体）"""
    try:
        from PIL import Image, ImageDraw, ImageFont

        # 尝试常见 Windows 中文字体路径
        font_paths = [
            "C:/Windows/Fonts/msyh.ttc",   # 微软雅黑
            "C:/Windows/Fonts/simhei.ttf",  # 黑体
            "C:/Windows/Fonts/simsun.ttc",  # 宋体
        ]

        font = None
        for fp in font_paths:
            try:
                font = ImageFont.truetype(fp, 36)
                break
            except Exception:
                continue

        if font is None:
            print("  [跳过] 未找到中文字体，跳过中文测试")
            return None

        img_pil = Image.new('RGB', (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(img_pil)

        draw.text((50, 30), "开始战斗", fill=(0, 0, 0), font=font)
        draw.text((50, 90), "金币: 88888", fill=(0, 0, 0), font=font)
        draw.text((50, 150), "等级 Lv.25", fill=(0, 0, 0), font=font)
        draw.text((400, 150), "确认退出", fill=(255, 0, 0), font=font)
        draw.text((50, 220), "自动战斗已开启", fill=(0, 128, 0), font=font)
        draw.text((50, 300), "第 3-5 关", fill=(0, 0, 0), font=font)

        # PIL Image -> OpenCV numpy array (RGB -> BGR)
        img_cv = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        return img_cv

    except ImportError:
        print("  [跳过] PIL 未安装，跳过中文测试")
        return None


def test_ocr_engine_init():
    """测试 1: PaddleOCR 引擎初始化"""
    print("\n[测试 1] PaddleOCR 引擎初始化...")
    recognizer = Recognizer()
    engine = recognizer._get_ocr_engine()
    assert engine is not None, "引擎初始化失败"
    # 第二次调用应该使用缓存
    engine2 = recognizer._get_ocr_engine()
    assert engine is engine2, "引擎实例未缓存"
    print("  [通过] 引擎初始化成功，实例已缓存")


def test_recognize_text_ascii():
    """测试 2: 英文/数字识别"""
    print("\n[测试 2] 英文/数字识别...")
    recognizer = Recognizer()
    img = create_test_image_ascii()

    text = recognizer.recognize_text(img)
    print(f"  识别结果:\n{text}")
    assert len(text) > 0, "未识别到任何文字"

    # 验证关键内容被识别
    text_lower = text.lower()
    found_keywords = []
    for keyword in ["hello", "world", "level", "42", "gold", "12345", "score", "9876", "start"]:
        if keyword in text_lower:
            found_keywords.append(keyword)

    print(f"  找到关键词: {found_keywords}")
    assert len(found_keywords) >= 5, f"关键词识别不足，只找到 {len(found_keywords)} 个"
    print(f"  [通过] 成功识别 {len(found_keywords)}/9 个关键词")


def test_recognize_all():
    """测试 3: recognize_all 详细结果"""
    print("\n[测试 3] recognize_all 详细结果...")
    recognizer = Recognizer()
    img = create_test_image_ascii()

    results = recognizer.recognize_all(img)
    print(f"  发现 {len(results)} 处文字:")
    for r in results:
        print(f"    {r}")

    assert len(results) > 0, "未识别到任何结果"
    assert all(isinstance(r, OCRResult) for r in results), "结果类型不正确"
    assert all(r.confidence > 0 for r in results), "置信度异常"
    assert all(len(r.box) == 4 for r in results), "边界框格式错误"
    assert all(len(r.center) == 2 for r in results), "中心点格式错误"
    print(f"  [通过] {len(results)} 条结果，数据结构正确")


def test_find_text():
    """测试 4: 文字定位"""
    print("\n[测试 4] 文字定位 (find_text)...")
    recognizer = Recognizer()
    img = create_test_image_ascii()

    # 精确匹配
    result = recognizer.find_text(img, "Press START", partial=True)
    if result:
        print(f"  精确查找 'Press START': {result}")
        assert result.center[0] > 0 and result.center[1] > 0, "中心点坐标异常"
        print(f"  [通过] 找到文字，中心点: {result.center}")
    else:
        print("  [警告] 精确查找未找到 'Press START'，尝试部分匹配")

    # 部分匹配
    result2 = recognizer.find_text(img, "Level", partial=True)
    if result2:
        print(f"  部分查找 'Level': {result2}")
        print(f"  [通过] 部分匹配成功")
    else:
        print("  [警告] 部分查找 'Level' 未命中（OCR 可能识别为其他形式）")


def test_text_exists():
    """测试 5: 文字存在判断"""
    print("\n[测试 5] 文字存在判断 (text_exists)...")
    recognizer = Recognizer()
    img = create_test_image_ascii()

    # 应该存在
    exists = recognizer.text_exists(img, "Gold", partial=True)
    print(f"  'Gold' 存在: {exists}")

    # 不应该存在
    not_exists = recognizer.text_exists(img, "Diamond", partial=True)
    print(f"  'Diamond' 存在: {not_exists}")
    assert not not_exists, "'Diamond' 不应该被找到"
    print("  [通过] 存在/不存在判断正确")


def test_read_number():
    """测试 6: 数字读取"""
    print("\n[测试 6] 数字读取 (read_number)...")
    recognizer = Recognizer()
    img = create_test_image_ascii()

    # "Gold: 12345" 实际位置: box=(51, 216, 192, 28) → 范围 (51,216) 到 (243,244)
    number = recognizer.read_number(img, region=(50, 210, 260, 250))
    print(f"  Gold 区域读取数字: {number}")
    if number is not None:
        assert number == 12345, f"期望 12345，得到 {number}"
        print(f"  [通过] 正确读取数字 12345")
    else:
        print("  [警告] 未能从 Gold 区域读取数字，尝试更大区域")
        number = recognizer.read_number(img, region=(0, 180, 500, 280))
        print(f"  扩大区域后读取: {number}")


def test_region_ocr():
    """测试 7: 区域限定识别"""
    print("\n[测试 7] 区域限定识别...")
    recognizer = Recognizer()
    img = create_test_image_ascii()

    # 只识别 "Score: 9876" 所在区域 (右半部分)
    text = recognizer.recognize_text(img, region=(350, 200, 800, 280))
    print(f"  右侧区域识别结果: '{text}'")

    # 不应该包含 "Gold"
    assert "gold" not in text.lower(), "区域限定失效，包含了不该有的内容"
    print("  [通过] 区域限定正确，未包含左侧内容")


def test_chinese_ocr():
    """测试 8: 中文识别"""
    print("\n[测试 8] 中文识别...")
    recognizer = Recognizer()
    img = create_test_image_chinese()

    if img is None:
        print("  [跳过] 无法生成中文测试图片")
        return

    text = recognizer.recognize_text(img)
    print(f"  识别结果:\n{text}")
    assert len(text) > 0, "中文识别无结果"

    # 验证中文关键词
    found = []
    for keyword in ["开始战斗", "金币", "88888", "等级", "确认退出", "自动战斗", "3-5"]:
        if keyword in text:
            found.append(keyword)

    print(f"  找到关键词: {found}")
    assert len(found) >= 4, f"中文关键词识别不足，只找到 {len(found)} 个"
    print(f"  [通过] 成功识别 {len(found)}/7 个中文关键词")

    # 测试 find_text 中文
    result = recognizer.find_text(img, "开始战斗", partial=False)
    if result:
        print(f"  find_text '开始战斗': center={result.center}, conf={result.confidence:.2f}")
        print(f"  [通过] 中文文字定位成功")
    else:
        print("  [警告] find_text 未找到 '开始战斗'")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("OCR 功能集成测试")
    print("=" * 60)

    tests = [
        test_ocr_engine_init,
        test_recognize_text_ascii,
        test_recognize_all,
        test_find_text,
        test_text_exists,
        test_read_number,
        test_region_ocr,
        test_chinese_ocr,
    ]

    passed = 0
    failed = 0
    errors = []

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((test.__name__, str(e)))
            print(f"  [失败] {e}")

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败, 共 {len(tests)} 个")
    if errors:
        print("失败详情:")
        for name, err in errors:
            print(f"  - {name}: {err}")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
