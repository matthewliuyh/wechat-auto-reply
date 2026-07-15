"""
微信自动回复 - 全托管自动模式引擎
持续OCR循环 + 消息变化检测 + 自动生成回复 + 自动发送
"""
import threading
import time
import hashlib
from datetime import datetime


class AutoReplyEngine:
    """
    全托管自动回复引擎
    
    工作流程：
    1. 定时截图 + OCR识别聊天内容
    2. 计算消息指纹，与上次对比检测是否有新消息
    3. 新消息到来 → 判断是否需要回复
    4. 需要回复 → 调用LLM生成候选 → 选最优 → 自动发送
    5. 循环往复
    """
    
    def __init__(self):
        self._running = False
        self._paused = False
        self._thread = None
        self._stop_event = threading.Event()
        
        # 参数
        self.poll_interval = 3.0       # 轮询间隔（秒）
        self.auto_send = True          # 是否自动发送
        self.reply_delay = 2.0         # 发送前等待（秒，模拟阅读时间）
        self.monitor_index = 0         # 显示器索引
        self.max_candidates = 3        # 候选回复数
        
        # 状态
        self.last_msg_fingerprint = ""  # 上次消息指纹
        self.last_messages = []         # 上次消息列表
        self.reply_count = 0            # 本轮自动回复次数
        self.start_time = None          # 启动时间
        
        # 回调（由GUI设置）
        self.on_status = None           # 状态更新回调 fn(text)
        self.on_new_message = None      # 新消息回调 fn(messages, context)
        self.on_reply_generated = None  # 回复生成回调 fn(candidates, chosen)
        self.on_reply_sent = None       # 回复发送回调 fn(text, success)
        self.on_log = None              # 日志回调 fn(text, level)
    
    @property
    def is_running(self):
        return self._running
    
    @property
    def is_paused(self):
        return self._paused
    
    def _log(self, text, level="info"):
        """输出日志"""
        ts = datetime.now().strftime("%H:%M:%S")
        msg = f"[{ts}] {text}"
        if self.on_log:
            self.on_log(msg, level)
    
    def _compute_fingerprint(self, messages):
        """
        计算消息列表的指纹
        只取对方消息的文本，避免自己的回复触发重复检测
        """
        other_texts = [m["text"] for m in messages if m["sender"] == "other"]
        content = "|".join(other_texts)
        return hashlib.md5(content.encode("utf-8")).hexdigest()
    
    def start(self):
        """启动自动模式"""
        if self._running:
            return
        
        self._running = True
        self._paused = False
        self._stop_event.clear()
        self.reply_count = 0
        self.start_time = datetime.now()
        self.last_msg_fingerprint = ""
        self.last_messages = []
        
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._log("自动模式已启动", "success")
    
    def stop(self):
        """停止自动模式"""
        if not self._running:
            return
        
        self._running = False
        self._paused = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._log("自动模式已停止", "warning")
    
    def pause(self):
        """暂停（不停止线程，只是跳过处理）"""
        if self._running and not self._paused:
            self._paused = True
            self._log("自动模式已暂停", "warning")
    
    def resume(self):
        """恢复"""
        if self._running and self._paused:
            self._paused = False
            self._log("自动模式已恢复", "success")
    
    def _loop(self):
        """主循环"""
        # 延迟导入，避免循环依赖
        from capture import capture_wechat_chat_area
        from ocr_engine import ocr_image, filter_noise
        from parser import parse_messages, get_chat_context, check_need_reply, get_unreplied_message
        from generator import generate_replies, load_config
        from sender import send_to_wechat
        from memory import add_reply_record, get_recent_replies
        from chat_log import save_chat_record
        
        while not self._stop_event.is_set():
            try:
                if self._paused:
                    self._stop_event.wait(timeout=1.0)
                    continue
                
                # 1. 截图 + OCR
                self._log("截图识别中...")
                img, hwnd = capture_wechat_chat_area(monitor_index=self.monitor_index)
                if img is None:
                    self._log("未找到微信窗口，等待重试...", "warning")
                    if self.on_status:
                        self.on_status("等待微信窗口...")
                    self._stop_event.wait(timeout=self.poll_interval)
                    continue
                
                ocr_items = ocr_image(img)
                ocr_items = filter_noise(ocr_items)
                
                if not ocr_items:
                    self._log("OCR未识别到文字", "warning")
                    self._stop_event.wait(timeout=self.poll_interval)
                    continue
                
                # 2. 解析消息
                img_width = img.size[0]
                messages = parse_messages(ocr_items, img_width)
                
                # 3. 计算指纹，检测变化
                fingerprint = self._compute_fingerprint(messages)
                
                if fingerprint == self.last_msg_fingerprint:
                    # 无新消息
                    if self.on_status:
                        self.on_status(f"监控中... ({len(messages)}条消息)")
                    self._stop_event.wait(timeout=self.poll_interval)
                    continue
                
                # 有变化
                old_fp = self.last_msg_fingerprint
                self.last_msg_fingerprint = fingerprint
                self.last_messages = messages
                
                # 4. 判断是否需要回复
                need_reply, reason = check_need_reply(messages)
                context = get_chat_context(messages)
                
                self._log(f"检测到新消息: {reason}")
                if self.on_new_message:
                    self.on_new_message(messages, context)
                
                if not need_reply:
                    self._log(f"无需回复: {reason}")
                    if self.on_status:
                        self.on_status(f"无需回复 - {reason[:30]}")
                    self._stop_event.wait(timeout=self.poll_interval)
                    continue
                
                # 5. 生成回复
                unreplied = get_unreplied_message(messages)
                if not unreplied:
                    self._log("未提取到未回复消息内容", "warning")
                    self._stop_event.wait(timeout=self.poll_interval)
                    continue
                
                cfg = load_config()
                if not cfg.get("api_key"):
                    self._log("API Key未配置，无法生成回复", "error")
                    if self.on_status:
                        self.on_status("请先配置API Key")
                    self._stop_event.wait(timeout=self.poll_interval * 2)
                    continue
                
                self._log(f"正在生成回复: {unreplied[:50]}...")
                if self.on_status:
                    self.on_status("生成回复中...")
                
                memory = get_recent_replies(5)
                candidates = generate_replies(context, unreplied, memory, cfg)
                
                if not candidates or candidates[0].startswith("["):
                    self._log(f"生成回复失败: {candidates[0] if candidates else '空'}", "error")
                    self._stop_event.wait(timeout=self.poll_interval)
                    continue
                
                # 选择最优回复（取第一条）
                chosen = candidates[0]
                
                self._log(f"候选回复: {' | '.join(candidates[:3])}")
                if self.on_reply_generated:
                    self.on_reply_generated(candidates, chosen)
                
                # 6. 发送前等待（模拟阅读时间）
                if self.reply_delay > 0:
                    self._log(f"等待{self.reply_delay:.1f}秒（模拟阅读）...")
                    if self.on_status:
                        self.on_status(f"将在{self.reply_delay:.1f}秒后发送...")
                    self._stop_event.wait(timeout=self.reply_delay)
                    if self._stop_event.is_set() or self._paused:
                        self._log("发送被中断", "warning")
                        continue
                
                # 7. 自动发送
                if self.auto_send:
                    self._log(f"自动发送: {chosen[:50]}...")
                    if self.on_status:
                        self.on_status("正在发送...")
                    
                    ok, msg = send_to_wechat(chosen, hwnd=hwnd)
                    if ok:
                        self.reply_count += 1
                        self._log(f"发送成功 (第{self.reply_count}次自动回复)", "success")
                        add_reply_record(unreplied, chosen, "auto")
                        save_chat_record(unreplied, chosen, "auto", chat_context=context)
                        if self.on_reply_sent:
                            self.on_reply_sent(chosen, True)
                        if self.on_status:
                            self.on_status(f"已自动回复 (共{self.reply_count}次)")
                        
                        # 发送后重新计算指纹（因为自己发了消息，屏幕会变化）
                        time.sleep(1.5)
                        # 下次循环会重新截图，指纹自然更新
                    else:
                        self._log(f"发送失败: {msg}", "error")
                        if self.on_reply_sent:
                            self.on_reply_sent(chosen, False)
                        if self.on_status:
                            self.on_status(f"发送失败: {msg[:30]}")
                else:
                    self._log(f"自动发送已关闭，候选回复: {chosen[:50]}")
                    if self.on_status:
                        self.on_status(f"候选回复已生成（未自动发送）")
                
                # 8. 等待下一轮
                self._stop_event.wait(timeout=self.poll_interval)
                
            except Exception as e:
                self._log(f"循环异常: {e}", "error")
                if self.on_status:
                    self.on_status(f"异常: {str(e)[:30]}")
                self._stop_event.wait(timeout=self.poll_interval)
    
    def get_stats(self):
        """获取自动模式统计"""
        elapsed = ""
        if self.start_time:
            delta = datetime.now() - self.start_time
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            elapsed = f"{hours}h{minutes:02d}m{seconds:02d}s"
        
        return {
            "running": self._running,
            "paused": self._paused,
            "reply_count": self.reply_count,
            "elapsed": elapsed,
            "poll_interval": self.poll_interval,
            "auto_send": self.auto_send,
        }
