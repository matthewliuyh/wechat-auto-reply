"""
OCR识别模块
使用RapidOCR（PaddleOCR的ONNX轻量版）识别聊天截图中的文字
优化：分区域识别 + 提高识别率
"""
from rapidocr_onnxruntime import RapidOCR
from PIL import Image, ImageFilter
import numpy as np


# 全局OCR引擎实例（懒加载）
_ocr_engine = None


def get_ocr_engine():
    """获取OCR引擎单例"""
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = RapidOCR()
    return _ocr_engine


def ocr_image(img):
    """
    对PIL.Image执行OCR识别
    分段识别以提高完整度：整图识别 + 分段补充
    返回: list of {"text": str, "bbox": [x1,y1,x2,y2], "confidence": float}
    按从上到下排序
    """
    if isinstance(img, Image.Image):
        img_array = np.array(img)
    else:
        img_array = img
        img = Image.fromarray(img_array)

    h, w = img_array.shape[:2]
    engine = get_ocr_engine()

    # 第一步：整图识别
    result1, _ = engine(img_array)
    
    # 第二步：将图片分上下两段再识别（补充被漏掉的文本）
    mid = h // 2
    overlap = 50  # 重叠区域
    
    top_region = img_array[:mid + overlap, :, :]
    bottom_region = img_array[mid - overlap:, :, :]
    
    result_top, _ = engine(top_region)
    result_bottom, _ = engine(bottom_region)
    
    # 合并结果：整图为主，分段补充
    all_items = []
    
    # 整图结果
    for bbox, text, confidence in (result1 or []):
        all_items.append(_parse_item(bbox, text, confidence))
    
    # 上半段补充（坐标不变）
    for bbox, text, confidence in (result_top or []):
        item = _parse_item(bbox, text, confidence)
        if not _is_duplicate(item, all_items):
            all_items.append(item)
    
    # 下半段补充（需要偏移y坐标）
    y_offset = mid - overlap
    for bbox, text, confidence in (result_bottom or []):
        item = _parse_item(bbox, text, confidence, y_offset=y_offset)
        if not _is_duplicate(item, all_items):
            all_items.append(item)
    
    # 按y坐标从上到下排序
    all_items.sort(key=lambda x: x["center_y"])
    return all_items


def _parse_item(bbox, text, confidence, y_offset=0):
    """解析单个OCR结果项"""
    x1 = min(p[0] for p in bbox)
    y1 = min(p[1] for p in bbox) + y_offset
    x2 = max(p[0] for p in bbox)
    y2 = max(p[1] for p in bbox) + y_offset
    return {
        "text": text.strip(),
        "bbox": [int(x1), int(y1), int(x2), int(y2)],
        "confidence": confidence,
        "center_x": (x1 + x2) / 2,
        "center_y": (y1 + y2) / 2,
    }


def _is_duplicate(new_item, existing_items, threshold=0.6):
    """
    检查新项是否与已有项重复
    基于文本内容和位置的重叠度判断
    """
    new_text = new_item["text"]
    new_y = new_item["center_y"]
    new_x = new_item["center_x"]
    new_h = new_item["bbox"][3] - new_item["bbox"][1]
    new_w = new_item["bbox"][2] - new_item["bbox"][0]
    
    for ex in existing_items:
        # 文本相似
        if ex["text"] == new_text:
            # 位置接近
            y_diff = abs(ex["center_y"] - new_y)
            x_diff = abs(ex["center_x"] - new_x)
            if y_diff < new_h * 0.5 and x_diff < new_w * 0.5:
                return True
        # 文本包含关系
        if new_text in ex["text"] or ex["text"] in new_text:
            y_diff = abs(ex["center_y"] - new_y)
            if y_diff < 30:
                return True
    
    return False


def filter_noise(items):
    """
    过滤噪声内容：时间戳、语音秒数、系统提示等
    同时过滤底部输入框区域的内容
    """
    import re
    noise_patterns = [
        r'^\d{1,2}:\d{2}$',           # 时间 "10:30"
        r'^\d{1,2}:\d{2}:\d{2}$',     # 时间 "10:30:00"
        r'^\d{1,2}"$',                 # 语音秒数 '3"'
        r'^\[\d+\]$',                  # [1] 序号
        r'^昨天$', r'^今天$', r'^星期',  # 日期标签
        r'^\d+条新消息$',               # 新消息提示
        r'^以下是新消息$',              # 系统提示
        r'^消息已发出，但被对方拒收',     # 系统提示
        r'^对方正在输入',               # 输入提示
        r'^以下是.*消息$',              # 消息分隔
        r'^按Enter发送，',             # 输入框提示
        r'^Ctrl\+Enter',              # 输入框提示
        r'^表情$',                     # 表情按钮
        r'^文件$',                     # 文件按钮
        r'^截图$',                     # 截图按钮
    ]

    filtered = []
    for item in items:
        text = item["text"]
        if not text or len(text) <= 1:
            continue
        is_noise = False
        for pat in noise_patterns:
            if re.match(pat, text):
                is_noise = True
                break
        if not is_noise:
            filtered.append(item)
    return filtered


if __name__ == "__main__":
    test_img = Image.open("test_capture.png")
    items = ocr_image(test_img)
    items = filter_noise(items)
    for item in items:
        print(f"[{item['center_x']:.0f},{item['center_y']:.0f}] ({item['confidence']:.2f}) {item['text']}")
