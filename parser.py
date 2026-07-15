"""
消息解析模块
根据OCR结果的x坐标位置，区分[对方]和[我]的消息
微信PC端布局：对方消息气泡靠左，我的消息气泡靠右
"""
import re


def parse_messages(ocr_items, img_width):
    """
    将OCR识别结果解析为结构化消息列表
    
    参数:
        ocr_items: OCR识别结果（已过滤噪声）
        img_width: 截图宽度（用于判断左右）
    
    返回: list of {"sender": "other"|"me", "text": str, "y": float}
    """
    if not ocr_items or img_width <= 0:
        return []

    # 微信PC端聊天区域布局分析：
    # - 对方头像在x≈30，气泡从x≈60开始，文本中心在左侧~15-40%
    # - 我的头像在x≈width-30，气泡到x≈width-60，文本中心在右侧~60-95%
    # - 群聊中成员名字在对方消息上方，也比较靠左
    # - 中间区域（40%-60%）通常是系统消息、时间戳等
    
    # 自适应分界：根据文本块的水平分布找出左右两个聚类
    x_positions = [item["center_x"] / img_width for item in ocr_items]
    
    # 使用更灵活的分界
    left_threshold = img_width * 0.42
    right_threshold = img_width * 0.58
    
    messages = []
    for item in ocr_items:
        cx = item["center_x"]
        text = item["text"]
        cy = item["center_y"]
        
        if cx < left_threshold:
            sender = "other"
        elif cx > right_threshold:
            sender = "me"
        else:
            # 中间区域，可能是系统消息
            # 短文本且居中 → 跳过（时间戳、系统提示等）
            if len(text) < 15:
                continue
            # 较长的中间文本，按更靠近哪边判断
            sender = "other" if cx < img_width * 0.5 else "me"
        
        # 额外过滤：识别群成员名（格式如"姓名：..."或"姓名 ..."）
        # 群聊中对方名字行通常很短且以冒号结尾或紧跟冒号
        if sender == "other" and len(text) <= 10:
            # 可能是群成员名字，保留但标记
            pass
        
        messages.append({
            "sender": sender,
            "text": text,
            "y": cy,
            "x": cx,
        })
    
    # 合并相邻的同发送者消息（同一气泡内多行文本）
    merged = []
    for msg in messages:
        if merged and merged[-1]["sender"] == msg["sender"]:
            # 如果y距离很近（<25px），认为是同一条消息的续行
            if msg["y"] - merged[-1]["y"] < 25:
                merged[-1]["text"] += msg["text"]
                merged[-1]["y"] = (merged[-1]["y"] + msg["y"]) / 2
                continue
        merged.append(msg)
    
    # 后处理：合并群聊成员名和消息
    # 如果一条"other"消息很短（<=8字）且下一条也是"other"，可能是成员名+消息
    final = []
    for i, msg in enumerate(merged):
        if (msg["sender"] == "other" and len(msg["text"]) <= 8 
            and i + 1 < len(merged) and merged[i+1]["sender"] == "other"
            and merged[i+1]["y"] - msg["y"] < 25):
            # 合并：成员名作为消息前缀
            merged[i+1]["text"] = msg["text"] + ": " + merged[i+1]["text"]
            continue
        final.append(msg)
    
    return final


def get_chat_context(messages, max_messages=20):
    """
    获取最近N条聊天上下文
    返回格式化的上下文字符串
    """
    recent = messages[-max_messages:]
    lines = []
    for msg in recent:
        prefix = "对方" if msg["sender"] == "other" else "我"
        lines.append(f"[{prefix}] {msg['text']}")
    return "\n".join(lines)


def check_need_reply(messages):
    """
    判断是否需要回复
    规则：最新消息是[对方] → 需要回复
          最新消息是[我] → 已回复过，不需要
    """
    if not messages:
        return False, "没有消息"
    
    last = messages[-1]
    if last["sender"] == "other":
        return True, f"对方最新消息: {last['text']}"
    else:
        return False, "最新消息是自己发的，已回复过"


def get_unreplied_message(messages):
    """
    获取未回复的消息内容
    找最后一条[我]之后的所有[对方]消息
    """
    last_me_index = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i]["sender"] == "me":
            last_me_index = i
            break
    
    # 取[我]之后的所有[对方]消息
    unreplied = []
    for i in range(last_me_index + 1, len(messages)):
        if messages[i]["sender"] == "other":
            unreplied.append(messages[i]["text"])
    
    return " ".join(unreplied) if unreplied else None


if __name__ == "__main__":
    # 模拟测试
    test_items = [
        {"text": "你好啊", "center_x": 100, "center_y": 50, "confidence": 0.95},
        {"text": "最近怎么样", "center_x": 100, "center_y": 100, "confidence": 0.93},
        {"text": "挺好的", "center_x": 500, "center_y": 150, "confidence": 0.96},
        {"text": "周末有空吗", "center_x": 100, "center_y": 200, "confidence": 0.91},
    ]
    msgs = parse_messages(test_items, img_width=600)
    for m in msgs:
        print(f"[{m['sender']}] {m['text']}")
    
    need, reason = check_need_reply(msgs)
    print(f"\n需要回复: {need}, 原因: {reason}")
    
    if need:
        unreplied = get_unreplied_message(msgs)
        print(f"未回复消息: {unreplied}")
