"""测试完整链路：截图 -> OCR -> 解析"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from capture import capture_wechat_chat_area
from ocr_engine import ocr_image, filter_noise
from parser import parse_messages, get_chat_context, check_need_reply

# 1. 截图
img, hwnd = capture_wechat_chat_area()
if img:
    os.makedirs('.temp', exist_ok=True)
    img.save('.temp/test_capture.png')
    print(f'截图尺寸: {img.size}')
    img_width = img.size[0]

    # 2. OCR
    items = ocr_image(img)
    print(f'OCR原始: {len(items)}个文本块')

    # 3. 过滤噪声
    items = filter_noise(items)
    print(f'过滤后: {len(items)}个文本块')

    # 4. 解析
    msgs = parse_messages(items, img_width)
    print(f'解析消息: {len(msgs)}条')
    for m in msgs:
        sender = m["sender"]
        text = m["text"]
        print(f'  [{sender}] {text}')

    # 5. 判断是否需要回复
    need, reason = check_need_reply(msgs)
    print(f'需要回复: {need}, 原因: {reason}')
else:
    print('截图失败')
