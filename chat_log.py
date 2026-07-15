"""
聊天记录模块
保存干净的真实聊天内容和回复内容，用于后续翻阅
只记录确认发送的回复，不记录OCR噪声和识别错误
"""
import json
import os
from datetime import datetime


# 记录目录
LOG_DIR = os.path.join(os.path.dirname(__file__), "chat_logs")


def _ensure_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def _today_file():
    """当天对应的日志文件路径"""
    _ensure_dir()
    date_str = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(LOG_DIR, f"{date_str}.md")


def save_chat_record(received_msg, reply_text, source="manual", chat_context=None):
    """
    保存一条聊天记录
    
    参数:
        received_msg: 对方发来的消息（已确认的真实内容）
        reply_text: 我方发送的回复（已确认发送的内容）
        source: 来源 - "manual"(手动输入) / "candidate"(选了候选) / "auto"(自动发送)
        chat_context: 可选，最近几条聊天上下文
    """
    now = datetime.now()
    time_str = now.strftime("%H:%M:%S")
    
    # 来源标签
    source_label = {"manual": "手动", "candidate": "候选", "auto": "自动"}.get(source, source)
    
    # 构建记录文本
    lines = []
    lines.append(f"### {time_str} [{source_label}]")
    lines.append("")
    lines.append(f"> 对方: {received_msg}")
    lines.append(f">")
    lines.append(f"> 我: {reply_text}")
    
    # 如果有上下文，附上最近几条（不含当前这轮）
    if chat_context and chat_context.strip():
        lines.append("")
        lines.append("<details>")
        lines.append("<summary>聊天上下文</summary>")
        lines.append("")
        lines.append("```")
        lines.append(chat_context.strip())
        lines.append("```")
        lines.append("")
        lines.append("</details>")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # 写入当天文件
    log_file = _today_file()
    
    # 如果文件不存在，写个标题头
    if not os.path.exists(log_file):
        header = f"# 聊天记录 {now.strftime('%Y-%m-%d')}\n\n"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(header)
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def get_log_dates():
    """获取所有有记录的日期列表（降序）"""
    _ensure_dir()
    files = [f for f in os.listdir(LOG_DIR) if f.endswith(".md")]
    dates = [f.replace(".md", "") for f in files]
    dates.sort(reverse=True)
    return dates


def read_log(date_str=None):
    """
    读取某天的聊天记录
    date_str: "YYYY-MM-DD"，默认今天
    返回: 记录文本内容
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    log_file = os.path.join(LOG_DIR, f"{date_str}.md")
    if not os.path.exists(log_file):
        return None
    
    with open(log_file, "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    # 测试
    save_chat_record("周末有空吗？", "有空呀，什么安排？", "candidate")
    save_chat_record("一起去爬山吧", "好主意！几点出发？", "auto", 
                     chat_context="[对方] 周末有空吗？\n[我] 有空呀\n[对方] 一起去爬山吧")
    print("记录已保存")
    
    content = read_log()
    if content:
        print(content)
