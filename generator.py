"""
LLM回复生成模块
调用大模型API生成候选回复，支持多种模型
"""
import requests
import json
import time


# 默认配置
DEFAULT_CONFIG = {
    "api_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",  # 智谱API
    "api_key": "",           # 需要用户配置
    "model": "glm-4-flash",  # 智谱免费模型
    "max_tokens": 150,
    "temperature": 0.7,
    "num_candidates": 3,
}


def load_config():
    """加载配置"""
    import os
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        cfg = DEFAULT_CONFIG.copy()
        cfg.update(saved)
        return cfg
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    """保存配置"""
    import os
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


SYSTEM_PROMPT = """你是一个微信聊天助手，帮助用户回复微信消息。
要求：
1. 回复要自然、口语化，像真人聊天一样
2. 不要太长，一般1-3句话
3. 不要用太书面或太正式的语气
4. 适当使用口语词如"嗯"、"哈"、"哦"等
5. 不要出现AI、人工智能、模型等字眼
6. 回复要针对对方最新消息，结合聊天上下文"""


def generate_replies(chat_context, unreplied_msg, memory_texts=None, cfg=None):
    """
    生成3条候选回复
    
    参数:
        chat_context: 格式化的聊天上下文
        unreplied_msg: 未回复的消息
        memory_texts: 历史回复记忆列表
        cfg: 配置字典
    
    返回: list of str (3条候选回复)
    """
    if cfg is None:
        cfg = load_config()
    
    if not cfg.get("api_key"):
        return ["[未配置API Key，请在设置中填写]"] * 3
    
    # 构建用户消息
    user_content = f"聊天上下文:\n{chat_context}\n\n对方最新消息: {unreplied_msg}\n\n"
    
    if memory_texts:
        user_content += f"我的历史回复风格参考:\n" + "\n".join(memory_texts[-5:]) + "\n\n"
    
    user_content += "请生成3条不同的候选回复，用|||分隔，只输出回复内容本身，不要序号和解释。"
    
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": cfg["max_tokens"],
        "temperature": cfg["temperature"],
    }
    
    try:
        resp = requests.post(cfg["api_url"], headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        
        # 解析3条候选回复
        if "|||" in content:
            candidates = [c.strip() for c in content.split("|||") if c.strip()]
        else:
            # 模型没按格式输出，尝试按换行分割
            candidates = [c.strip().lstrip("123.、") for c in content.split("\n") if c.strip()]
        
        # 确保至少有1条
        candidates = [c for c in candidates if len(c) > 1]
        if not candidates:
            candidates = [content]
        
        # 过滤掉太像AI的回复
        candidates = filter_ai_like(candidates)
        
        # 最多3条
        return candidates[:3]
        
    except requests.exceptions.RequestException as e:
        return [f"[API调用失败: {str(e)}]"]
    except (KeyError, IndexError) as e:
        return [f"[解析回复失败: {str(e)}]"]


def test_api_connection(cfg):
    """
    测试API连接是否正常
    返回 (bool, str)  (是否成功, 消息)
    """
    if not cfg.get("api_key"):
        return False, "API Key为空"
    if not cfg.get("api_url"):
        return False, "API地址为空"
    if not cfg.get("model"):
        return False, "模型名为空"
    
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "user", "content": "你好，请用一句话回复"},
        ],
        "max_tokens": 50,
    }
    
    try:
        resp = requests.post(cfg["api_url"], headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        return True, f"模型 {cfg['model']} 回复: {content[:50]}"
    except requests.exceptions.ConnectionError:
        return False, "连接失败，请检查API地址和网络"
    except requests.exceptions.Timeout:
        return False, "请求超时，请检查网络"
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response else "N/A"
        if code == 401:
            return False, f"认证失败({code})，请检查API Key"
        elif code == 404:
            return False, f"地址不存在({code})，请检查API地址和模型名"
        else:
            return False, f"HTTP错误 {code}: {str(e)[:100]}"
    except (KeyError, IndexError) as e:
        return False, f"解析响应失败: {e}"
    except Exception as e:
        return False, f"未知错误: {str(e)[:100]}"


def filter_ai_like(candidates):
    """过滤掉太像AI的回复"""
    ai_keywords = [
        "作为AI", "我是人工智能", "作为模型", "作为助手",
        "我无法", "我不能", "抱歉我不能", "对不起我不能",
        "总的来说", "综上所述", "首先其次", "一方面另一方面",
    ]
    filtered = []
    for c in candidates:
        is_ai = False
        for kw in ai_keywords:
            if kw in c:
                is_ai = True
                break
        if not is_ai:
            filtered.append(c)
    return filtered if filtered else candidates


if __name__ == "__main__":
    cfg = load_config()
    if cfg["api_key"]:
        context = "[对方] 你好啊\n[我] 嗨\n[对方] 周末有空吗"
        unreplied = "周末有空吗"
        replies = generate_replies(context, unreplied, cfg=cfg)
        for i, r in enumerate(replies, 1):
            print(f"候选{i}: {r}")
    else:
        print("请先在config.json中配置api_key")
