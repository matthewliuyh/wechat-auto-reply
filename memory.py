"""
回复记忆模块
记录用户选择的回复，用于学习用户风格
"""
import json
import os
from datetime import datetime


MEMORY_FILE = os.path.join(os.path.dirname(__file__), "reply_memory.json")


def load_memory():
    """加载历史回复记忆"""
    if not os.path.exists(MEMORY_FILE):
        return []
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_memory(memories):
    """保存记忆"""
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)


def add_reply_record(context_msg, chosen_reply, source="candidate"):
    """
    记录一次回复
    context_msg: 对方消息
    chosen_reply: 用户选择的回复
    source: "candidate"（选中候选）| "manual"（手动输入）
    """
    memories = load_memory()
    record = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "received": context_msg,
        "replied": chosen_reply,
        "source": source,
    }
    memories.append(record)
    # 最多保留500条
    if len(memories) > 500:
        memories = memories[-500:]
    save_memory(memories)


def get_recent_replies(n=10):
    """获取最近N条回复文本，用于风格参考"""
    memories = load_memory()
    recent = memories[-n:]
    return [m["replied"] for m in recent if m.get("replied")]


def get_stats():
    """获取记忆统计"""
    memories = load_memory()
    return {
        "total": len(memories),
        "candidate": sum(1 for m in memories if m.get("source") == "candidate"),
        "manual": sum(1 for m in memories if m.get("source") == "manual"),
        "auto": sum(1 for m in memories if m.get("source") == "auto"),
    }


if __name__ == "__main__":
    add_reply_record("你好", "嗨，你好呀~", "candidate")
    add_reply_record("吃饭了吗", "吃了，你呢？", "manual")
    print(f"统计: {get_stats()}")
    print(f"最近回复: {get_recent_replies()}")
