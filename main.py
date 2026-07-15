"""
微信AI自动回复 - 主界面（手动模式 + 全托管自动模式）
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import os
import sys
import ctypes
import ctypes.wintypes

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

from capture import capture_wechat_chat_area, get_wechat_status, get_monitors, open_region_editor
from ocr_engine import ocr_image, filter_noise
from parser import parse_messages, get_chat_context, check_need_reply, get_unreplied_message
from generator import generate_replies, load_config, save_config, test_api_connection
from sender import send_to_wechat, copy_to_clipboard
from memory import add_reply_record, get_recent_replies, get_stats
from auto_engine import AutoReplyEngine
from chat_log import save_chat_record


class WeChatAutoReplyApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("微信AI自动回复")
        self.root.geometry("960x850")
        self.root.resizable(True, True)
        
        # 状态变量
        self.messages = []
        self.chat_img = None
        self.candidates = []
        self.last_unreplied = ""
        self.selected_monitor = 0
        
        # 自动模式引擎
        self.auto_engine = AutoReplyEngine()
        
        self._build_ui()
        self._check_wechat()
    
    def _build_ui(self):
        """构建界面"""
        # ===== 顶部工具栏（一行，均匀分布） =====
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=10, pady=5)
        
        # 模式切换
        self.mode_var = tk.StringVar(value="manual")
        ttk.Radiobutton(toolbar, text="手动模式", variable=self.mode_var, 
                        value="manual", command=self._on_mode_change).pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(toolbar, text="自动模式", variable=self.mode_var,
                        value="auto", command=self._on_mode_change).pack(side=tk.LEFT, padx=4)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        
        # 手动按钮
        self.btn_detect = ttk.Button(toolbar, text="识别聊天", command=self._on_detect)
        self.btn_detect.pack(side=tk.LEFT, padx=4)
        
        self.btn_generate = ttk.Button(toolbar, text="生成回复", command=self._on_generate, state=tk.DISABLED)
        self.btn_generate.pack(side=tk.LEFT, padx=4)
        
        # 自动按钮
        self.btn_auto_start = ttk.Button(toolbar, text="启动自动", command=self._on_auto_start)
        self.btn_auto_pause = ttk.Button(toolbar, text="暂停", command=self._on_auto_pause, state=tk.DISABLED)
        self.btn_auto_stop = ttk.Button(toolbar, text="停止", command=self._on_auto_stop, state=tk.DISABLED)
        self.btn_auto_start.pack(side=tk.LEFT, padx=4)
        self.btn_auto_pause.pack(side=tk.LEFT, padx=4)
        self.btn_auto_stop.pack(side=tk.LEFT, padx=4)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        
        # 屏幕
        ttk.Label(toolbar, text="屏幕:").pack(side=tk.LEFT, padx=(0, 2))
        monitors = get_monitors()
        monitor_names = [f"显示器{i+1}" for i in range(len(monitors))]
        self.monitor_var = tk.StringVar(value=monitor_names[0] if monitor_names else "显示器1")
        self.monitor_combo = ttk.Combobox(toolbar, textvariable=self.monitor_var,
                                           values=monitor_names, state="readonly", width=8)
        self.monitor_combo.pack(side=tk.LEFT, padx=2)
        self.monitor_combo.bind("<<ComboboxSelected>>", self._on_monitor_change)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        
        self.btn_region = ttk.Button(toolbar, text="区域设置", command=self._on_region_settings)
        self.btn_region.pack(side=tk.LEFT, padx=4)
        
        self.btn_clear = ttk.Button(toolbar, text="清屏", command=self._on_clear)
        self.btn_clear.pack(side=tk.LEFT, padx=4)
        
        self.btn_history = ttk.Button(toolbar, text="历史记录", command=self._on_history)
        self.btn_history.pack(side=tk.LEFT, padx=4)
        
        self.btn_settings = ttk.Button(toolbar, text="设置", command=self._on_settings)
        self.btn_settings.pack(side=tk.LEFT, padx=4)
        
        # 右侧状态
        self.auto_stats_var = tk.StringVar(value="")
        ttk.Label(toolbar, textvariable=self.auto_stats_var, foreground="green").pack(side=tk.RIGHT, padx=5)
        
        self.model_var = tk.StringVar(value="")
        ttk.Label(toolbar, textvariable=self.model_var, foreground="#576B95").pack(side=tk.RIGHT, padx=5)
        
        self.status_var = tk.StringVar(value="就绪 - 手动模式")
        ttk.Label(toolbar, textvariable=self.status_var, foreground="blue").pack(side=tk.RIGHT, padx=5)
        
        # 加载模型名显示
        try:
            _cfg = load_config()
            self.model_var.set(f"模型: {_cfg.get('model', '未知')}")
        except Exception:
            self.model_var.set("模型: 未知")
        
        # ===== 自动模式参数栏 =====
        self.auto_params_frame = ttk.LabelFrame(self.root, text="自动模式参数")
        self.auto_params_frame.pack(fill=tk.X, padx=10, pady=2)
        
        params_row = ttk.Frame(self.auto_params_frame)
        params_row.pack(fill=tk.X, padx=5, pady=3)
        
        ttk.Label(params_row, text="轮询间隔:").pack(side=tk.LEFT)
        self.poll_var = tk.StringVar(value="3")
        ttk.Entry(params_row, textvariable=self.poll_var, width=4, font=("Consolas", 10)).pack(side=tk.LEFT, padx=2)
        ttk.Label(params_row, text="秒").pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Label(params_row, text="发送延迟:").pack(side=tk.LEFT)
        self.delay_var = tk.StringVar(value="2")
        ttk.Entry(params_row, textvariable=self.delay_var, width=4, font=("Consolas", 10)).pack(side=tk.LEFT, padx=2)
        ttk.Label(params_row, text="秒").pack(side=tk.LEFT, padx=(0, 10))
        
        self.auto_send_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(params_row, text="自动发送", variable=self.auto_send_var).pack(side=tk.LEFT, padx=10)
        
        # ===== 聊天上下文显示区 =====
        ctx_frame = ttk.LabelFrame(self.root, text="聊天上下文")
        ctx_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.ctx_text = scrolledtext.ScrolledText(ctx_frame, height=10, font=("Microsoft YaHei", 10), wrap=tk.WORD)
        self.ctx_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.ctx_text.config(state=tk.DISABLED)
        
        # 回复状态
        self.reply_status_var = tk.StringVar(value="")
        ttk.Label(ctx_frame, textvariable=self.reply_status_var, foreground="blue").pack(anchor=tk.W, padx=5)
        
        # ===== 候选回复区 =====
        cand_frame = ttk.LabelFrame(self.root, text="候选回复")
        cand_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.candidate_frames = []
        self.candidate_texts = []
        self.candidate_labels = []
        
        for i in range(3):
            row = ttk.Frame(cand_frame)
            row.pack(fill=tk.X, padx=5, pady=3)
            
            label = ttk.Label(row, text=f"回复{i+1}:", width=5)
            label.pack(side=tk.LEFT)
            
            text_var = tk.StringVar(value="")
            text_entry = ttk.Entry(row, textvariable=text_var, font=("Microsoft YaHei", 10))
            text_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            
            btn_edit = ttk.Button(row, text="改", width=3,
                                   command=lambda idx=i: self._on_edit(idx))
            btn_edit.pack(side=tk.LEFT, padx=2)
            
            btn_send = ttk.Button(row, text="发", width=3,
                                   command=lambda idx=i: self._on_send(idx))
            btn_send.pack(side=tk.LEFT, padx=2)
            
            btn_copy = ttk.Button(row, text="复制", width=4,
                                   command=lambda idx=i: self._on_copy(idx))
            btn_copy.pack(side=tk.LEFT, padx=2)
            
            self.candidate_texts.append(text_var)
            self.candidate_labels.append(label)
            self.candidate_frames.append(row)
        
        # ===== 手动输入区 =====
        input_frame = ttk.LabelFrame(self.root, text="手动输入")
        input_frame.pack(fill=tk.X, padx=10, pady=5)
        
        input_row = ttk.Frame(input_frame)
        input_row.pack(fill=tk.X, padx=5, pady=5)
        
        self.manual_entry = ttk.Entry(input_row, font=("Microsoft YaHei", 10))
        self.manual_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.manual_entry.bind('<Return>', lambda e: self._on_manual_send())
        
        btn_manual_send = ttk.Button(input_row, text="发送", command=self._on_manual_send)
        btn_manual_send.pack(side=tk.LEFT, padx=5)
        
        btn_manual_copy = ttk.Button(input_row, text="仅复制", command=self._on_manual_copy)
        btn_manual_copy.pack(side=tk.LEFT, padx=5)
        
        # ===== 自动模式日志区 =====
        self.log_frame = ttk.LabelFrame(self.root, text="自动模式日志")
        self.log_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(self.log_frame, height=6, font=("Consolas", 9), wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 配置日志颜色标签
        self.log_text.tag_configure("success", foreground="green")
        self.log_text.tag_configure("warning", foreground="orange")
        self.log_text.tag_configure("error", foreground="red")
        self.log_text.tag_configure("info", foreground="black")
        
        # 底部状态栏
        bottom = ttk.Frame(self.root)
        bottom.pack(fill=tk.X, padx=10, pady=5)
        
        self.stats_var = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.stats_var).pack(side=tk.LEFT)
        self._update_stats()
        
        # 初始化模式状态
        self._on_mode_change()
        
        # 设置引擎回调
        self._setup_engine_callbacks()
        
        # 定时刷新自动模式统计
        self._auto_stats_tick()
    
    def _setup_engine_callbacks(self):
        """设置自动引擎回调"""
        def on_status(text):
            self.root.after(0, lambda: self.status_var.set(text))
        
        def on_new_message(messages, context):
            def update():
                self.messages = messages
                self.ctx_text.config(state=tk.NORMAL)
                self.ctx_text.delete(1.0, tk.END)
                self.ctx_text.insert(tk.END, context)
                self.ctx_text.config(state=tk.DISABLED)
            self.root.after(0, update)
        
        def on_reply_generated(candidates, chosen):
            def update():
                for i in range(3):
                    if i < len(candidates):
                        self.candidate_texts[i].set(candidates[i])
                    else:
                        self.candidate_texts[i].set("")
                self.reply_status_var.set(f"自动选择回复1: {chosen[:40]}...")
            self.root.after(0, update)
        
        def on_reply_sent(text, success):
            def update():
                if success:
                    self.reply_status_var.set(f"已自动发送: {text[:40]}...")
                    self._update_stats()
                else:
                    self.reply_status_var.set("自动发送失败")
            self.root.after(0, update)
        
        def on_log(text, level="info"):
            def update():
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, text + "\n", level)
                self.log_text.see(tk.END)
                # 限制日志行数
                lines = int(self.log_text.index('end-1c').split('.')[0])
                if lines > 200:
                    self.log_text.delete(1.0, f"{lines - 200}.0")
                self.log_text.config(state=tk.DISABLED)
            self.root.after(0, update)
        
        self.auto_engine.on_status = on_status
        self.auto_engine.on_new_message = on_new_message
        self.auto_engine.on_reply_generated = on_reply_generated
        self.auto_engine.on_reply_sent = on_reply_sent
        self.auto_engine.on_log = on_log
    
    def _auto_stats_tick(self):
        """定时刷新自动模式统计"""
        if self.auto_engine.is_running:
            stats = self.auto_engine.get_stats()
            state = "暂停" if stats["paused"] else "运行"
            self.auto_stats_var.set(
                f"自动模式 {state} | 回复{stats['reply_count']}次 | 耗时{stats['elapsed']}"
            )
        else:
            self.auto_stats_var.set("")
        self.root.after(1000, self._auto_stats_tick)
    
    def _on_mode_change(self):
        """模式切换"""
        is_auto = self.mode_var.get() == "auto"
        
        # 手动按钮
        self.btn_detect.config(state=tk.DISABLED if is_auto else tk.NORMAL)
        self.btn_generate.config(state=tk.DISABLED)
        
        # 自动按钮
        auto_state = tk.NORMAL if is_auto else tk.DISABLED
        self.btn_auto_start.config(state=auto_state)
        # 如果引擎在运行，保持暂停/停止按钮可用
        if is_auto and self.auto_engine.is_running:
            self.btn_auto_pause.config(state=tk.NORMAL)
            self.btn_auto_stop.config(state=tk.NORMAL)
        else:
            self.btn_auto_pause.config(state=tk.DISABLED)
            self.btn_auto_stop.config(state=tk.DISABLED)
        
        # 参数栏
        for child in self.auto_params_frame.winfo_children():
            for widget in child.winfo_children():
                try:
                    widget.config(state=tk.NORMAL if is_auto else tk.DISABLED)
                except tk.TclError:
                    pass
        
        if is_auto:
            self.status_var.set("自动模式 - 点击「启动自动」开始")
        else:
            # 切到手动时，如果自动引擎在运行，先停止
            if self.auto_engine.is_running:
                self._on_auto_stop()
            self.status_var.set("手动模式 - 点击「识别聊天」")
    
    def _on_auto_start(self):
        """启动自动模式"""
        cfg = load_config()
        if not cfg.get("api_key"):
            messagebox.showwarning("提示", "请先在设置中配置API Key")
            self._on_settings()
            return
        
        # 读取参数
        try:
            self.auto_engine.poll_interval = float(self.poll_var.get())
        except ValueError:
            self.auto_engine.poll_interval = 3.0
        try:
            self.auto_engine.reply_delay = float(self.delay_var.get())
        except ValueError:
            self.auto_engine.reply_delay = 2.0
        self.auto_engine.auto_send = self.auto_send_var.get()
        self.auto_engine.monitor_index = self.selected_monitor
        
        # 清空日志
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        self.auto_engine.start()
        
        self.btn_auto_start.config(state=tk.DISABLED)
        self.btn_auto_pause.config(state=tk.NORMAL)
        self.btn_auto_stop.config(state=tk.NORMAL)
        
        # 禁用手动按钮
        self.btn_detect.config(state=tk.DISABLED)
        self.btn_generate.config(state=tk.DISABLED)
    
    def _on_auto_pause(self):
        """暂停/恢复自动模式"""
        if self.auto_engine.is_paused:
            self.auto_engine.resume()
            self.btn_auto_pause.config(text="暂停")
        else:
            self.auto_engine.pause()
            self.btn_auto_pause.config(text="恢复")
    
    def _on_auto_stop(self):
        """停止自动模式"""
        self.auto_engine.stop()
        self.btn_auto_start.config(state=tk.NORMAL)
        self.btn_auto_pause.config(state=tk.DISABLED, text="暂停")
        self.btn_auto_stop.config(state=tk.DISABLED)
        self.btn_detect.config(state=tk.NORMAL)
        self.status_var.set("自动模式已停止")
    
    def _on_monitor_change(self, event=None):
        """切换显示器"""
        idx = self.monitor_combo.current()
        self.selected_monitor = idx
        self.auto_engine.monitor_index = idx
        monitors = get_monitors()
        if idx < len(monitors):
            m = monitors[idx]
            self.status_var.set(f"已切换到显示器{idx+1} ({m['width']}x{m['height']})")
    
    def _on_clear(self):
        """清屏：清空聊天上下文、候选回复、日志"""
        self.messages = []
        self.candidates = []
        self.last_unreplied = ""
        
        # 清空聊天上下文
        self.ctx_text.config(state=tk.NORMAL)
        self.ctx_text.delete(1.0, tk.END)
        self.ctx_text.config(state=tk.DISABLED)
        
        # 清空候选回复
        for i in range(3):
            self.candidate_texts[i].set("")
        
        # 清空回复状态
        self.reply_status_var.set("")
        
        # 清空日志
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        # 重置按钮状态
        self.btn_generate.config(state=tk.DISABLED)
        self.status_var.set("已清屏")
    
    def _on_history(self):
        """打开历史记录查看窗口 - 微信气泡对话风格"""
        from chat_log import get_log_dates, read_log
        from datetime import datetime as dt
        import math

        dates = get_log_dates()
        current_date_idx = [0]  # 用list以便闭包修改

        win = tk.Toplevel(self.root)
        win.title("聊天记录")
        win.configure(bg="#EDEDED")
        win.geometry("520x620")
        win.minsize(380, 400)

        # === 微信配色（严格对标微信PC端） ===
        BG = "#F5F5F5"          # 聊天区背景
        BUBBLE_OTHER = "#FFFFFF" # 对方白气泡
        BUBBLE_ME = "#95EC69"    # 我方绿气泡
        TEXT_COLOR = "#111111"   # 气泡内文字
        TIME_FG = "#999999"     # 时间标签文字
        HEADER_BG = "#F7F7F7"   # 顶部栏背景
        AVATAR_OTHER = "#576B95" # 对方头像实色
        AVATAR_ME = "#07C160"    # 我方头像实色

        # === 顶部导航栏 ===
        nav_bar = tk.Frame(win, bg=HEADER_BG, height=72,
                           highlightbackground="#D5D5D5", highlightthickness=1)
        nav_bar.pack(fill=tk.X)
        nav_bar.pack_propagate(False)

        # 日期切换：左箭头 < 日期 右箭头 >
        btn_prev = tk.Label(nav_bar, text="  ◀  ", font=("Microsoft YaHei", 14),
                            bg=HEADER_BG, fg="#576B95", cursor="hand2")
        btn_prev.pack(side=tk.LEFT, padx=(10, 0), pady=18)

        date_var = tk.StringVar(value="请选择日期")
        date_lbl = tk.Label(nav_bar, textvariable=date_var, font=("Microsoft YaHei", 14, "bold"),
                            bg=HEADER_BG, fg="#1C1C1C", cursor="hand2")
        date_lbl.pack(side=tk.LEFT, padx=10, pady=18)

        btn_next = tk.Label(nav_bar, text="  ▶  ", font=("Microsoft YaHei", 14),
                            bg=HEADER_BG, fg="#576B95", cursor="hand2")
        btn_next.pack(side=tk.LEFT, padx=6, pady=18)

        count_var = tk.StringVar(value="")
        tk.Label(nav_bar, textvariable=count_var, font=("Microsoft YaHei", 9),
                 bg=HEADER_BG, fg="#999999").pack(side=tk.RIGHT, padx=14, pady=18)

        # === 聊天区 Canvas ===
        canvas_frame = tk.Frame(win, bg=BG)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        vscroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        chat_canvas = tk.Canvas(canvas_frame, bg=BG, highlightthickness=0,
                                yscrollcommand=vscroll.set)
        chat_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscroll.config(command=chat_canvas.yview)

        # 鼠标滚轮支持
        def _on_mousewheel(event):
            chat_canvas.yview_scroll(-1 * (event.delta // 120), "units")
        chat_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # 来源标签
        source_names = {"auto": "自动", "manual": "手动", "candidate": "候选"}
        source_colors = {"auto": "#9B59B6", "manual": "#E67E22", "candidate": "#07C160"}

        def _rounded_rect(canvas, x1, y1, x2, y2, r, **kwargs):
            """绘制圆角矩形"""
            points = []
            # 左上圆角
            for i in range(20):
                a = math.pi / 2 + math.pi / 2 * i / 19
                points.append(x1 + r + r * math.cos(a))
                points.append(y1 + r - r * math.sin(a))
            # 上边
            points.extend([x1 + r, y1, x2 - r, y1])
            # 右上圆角
            for i in range(20):
                a = -math.pi / 2 * i / 19
                points.append(x2 - r + r * math.cos(a))
                points.append(y1 + r + r * math.sin(a))
            # 右边
            points.extend([x2, y2 - r])
            # 右下圆角
            for i in range(20):
                a = -math.pi / 2 - math.pi / 2 * i / 19
                points.append(x2 - r + r * math.cos(a))
                points.append(y2 - r + r * math.sin(a))
            # 下边
            points.extend([x2 - r, y2, x1 + r, y2])
            # 左下圆角
            for i in range(20):
                a = -math.pi - math.pi / 2 * i / 19
                points.append(x1 + r + r * math.cos(a))
                points.append(y2 - r + r * math.sin(a))
            # 左边
            points.extend([x1, y2 - r, x1, y1 + r])
            return canvas.create_polygon(points, smooth=False, **kwargs)

        def _draw_avatar(canvas, cx, cy, color, label):
            """绘制圆角方形头像 - 微信风格：实色填充+白色文字"""
            s = 30  # 头像边长
            r = 6   # 圆角半径
            half = s / 2
            x1, y1 = cx - half, cy - half
            x2, y2 = cx + half, cy + half
            # 圆角方形实色填充
            pts = []
            for i in range(20):
                a = math.pi / 2 + math.pi / 2 * i / 19
                pts.append(x1 + r + r * math.cos(a))
                pts.append(y1 + r - r * math.sin(a))
            pts.extend([x1 + r, y1, x2 - r, y1])
            for i in range(20):
                a = -math.pi / 2 * i / 19
                pts.append(x2 - r + r * math.cos(a))
                pts.append(y1 + r + r * math.sin(a))
            pts.extend([x2, y2 - r])
            for i in range(20):
                a = -math.pi / 2 - math.pi / 2 * i / 19
                pts.append(x2 - r + r * math.cos(a))
                pts.append(y2 - r + r * math.sin(a))
            pts.extend([x2 - r, y2, x1 + r, y2])
            for i in range(20):
                a = -math.pi - math.pi / 2 * i / 19
                pts.append(x1 + r + r * math.cos(a))
                pts.append(y2 - r + r * math.sin(a))
            pts.extend([x1, y2 - r, x1, y1 + r])
            canvas.create_polygon(pts, fill=color, outline=color, smooth=False)
            canvas.create_text(cx, cy, text=label, font=("Microsoft YaHei", 10, "bold"), fill="white")

        def _draw_bubble_other(canvas, y, text, canvas_w):
            """对方消息：左头像 + 白气泡 + 左三角（微信风格）"""
            font = ("Microsoft YaHei", 10)
            avatar_size = 30    # 头像边长
            avatar_half = 15
            gap = 6             # 头像与气泡间距(三角尖占6)
            margin = 12         # 左边距
            pad_x, pad_y = 12, 10  # 微信标准内边距
            max_w = canvas_w - margin - avatar_size - gap - pad_x * 2 - margin - 20
            max_w = max(max_w, 120)

            # 测量文字
            tmp = canvas.create_text(0, 0, text=text, font=font, width=max_w, anchor=tk.NW)
            bbox = canvas.bbox(tmp)
            canvas.delete(tmp)
            if not bbox:
                return y
            tw = min(bbox[2] - bbox[0], max_w)
            th = bbox[3] - bbox[1]
            bw, bh = tw + pad_x * 2, th + pad_y * 2

            # 头像中心（垂直居中于气泡）
            av_cx = margin + avatar_half
            av_cy = y + bh / 2

            # 气泡位置
            tri = 6   # 三角突出长度
            tri_h = 4  # 三角半高
            bx = margin + avatar_size + gap  # 气泡左边缘(含三角)
            bx_body = bx + tri  # 气泡体左边缘
            by = y
            cr = 10  # 气泡圆角半径

            # 绘制白气泡：主体+左侧三角
            points = []
            # 左上圆角(从三角下方开始)
            for i in range(20):
                a = math.pi / 2 + math.pi / 2 * i / 19
                points.append(bx_body + cr + cr * math.cos(a))
                points.append(by + cr - cr * math.sin(a))
            points.extend([bx_body + cr, by, bx_body + bw - cr, by])
            # 右上圆角
            for i in range(20):
                a = -math.pi / 2 * i / 19
                points.append(bx_body + bw - cr + cr * math.cos(a))
                points.append(by + cr + cr * math.sin(a))
            points.extend([bx_body + bw, by + bh - cr])
            # 右下圆角
            for i in range(20):
                a = -math.pi / 2 - math.pi / 2 * i / 19
                points.append(bx_body + bw - cr + cr * math.cos(a))
                points.append(by + bh - cr + cr * math.sin(a))
            points.extend([bx_body + bw, by + bh, bx_body + cr, by + bh])
            # 左下圆角
            for i in range(20):
                a = -math.pi - math.pi / 2 * i / 19
                points.append(bx_body + cr + cr * math.cos(a))
                points.append(by + bh - cr + cr * math.sin(a))
            # 左边含三角尖（指向左侧头像）
            tri_cy = by + bh / 2  # 三角垂直居中
            points.extend([bx_body, by + bh - cr, bx_body, tri_cy + tri_h, bx, tri_cy, bx_body, tri_cy - tri_h, bx_body, by + cr])

            canvas.create_polygon(points, fill=BUBBLE_OTHER, outline=BUBBLE_OTHER, smooth=False)
            canvas.create_text(bx_body + pad_x, by + pad_y, text=text, font=font,
                               fill=TEXT_COLOR, width=max_w, anchor=tk.NW)
            _draw_avatar(canvas, av_cx, av_cy, AVATAR_OTHER, "TA")
            return by + bh

        def _draw_bubble_me(canvas, y, text, canvas_w):
            """我方消息：右头像 + 绿气泡 + 右三角（微信风格）"""
            font = ("Microsoft YaHei", 10)
            avatar_size = 30
            avatar_half = 15
            gap = 6
            margin = 12
            pad_x, pad_y = 12, 10
            max_w = canvas_w - margin - avatar_size - gap - pad_x * 2 - margin - 20
            max_w = max(max_w, 120)

            tmp = canvas.create_text(0, 0, text=text, font=font, width=max_w, anchor=tk.NW)
            bbox = canvas.bbox(tmp)
            canvas.delete(tmp)
            if not bbox:
                return y
            tw = min(bbox[2] - bbox[0], max_w)
            th = bbox[3] - bbox[1]
            bw, bh = tw + pad_x * 2, th + pad_y * 2

            # 头像中心
            av_cx = canvas_w - margin - avatar_half
            av_cy = y + bh / 2

            # 气泡位置（右对齐）
            tri = 6
            tri_h = 4
            bx_body_right = av_cx - avatar_half - gap  # 气泡体右边缘
            bx_body = bx_body_right - bw - tri  # 气泡体左边缘
            by = y
            cr = 10

            # 绿气泡：主体+右侧三角
            points = []
            # 左上圆角
            for i in range(20):
                a = math.pi / 2 + math.pi / 2 * i / 19
                points.append(bx_body + cr + cr * math.cos(a))
                points.append(by + cr - cr * math.sin(a))
            points.extend([bx_body + cr, by, bx_body + bw - cr, by])
            # 右上圆角
            for i in range(20):
                a = -math.pi / 2 * i / 19
                points.append(bx_body + bw - cr + cr * math.cos(a))
                points.append(by + cr + cr * math.sin(a))
            # 右边含三角尖
            tri_cy = by + bh / 2
            points.extend([bx_body + bw, by + cr, bx_body + bw, tri_cy - tri_h, bx_body + bw + tri, tri_cy, bx_body + bw, tri_cy + tri_h, bx_body + bw, by + bh - cr])
            # 右下圆角
            for i in range(20):
                a = -math.pi / 2 - math.pi / 2 * i / 19
                points.append(bx_body + bw - cr + cr * math.cos(a))
                points.append(by + bh - cr + cr * math.sin(a))
            points.extend([bx_body + bw, by + bh, bx_body + cr, by + bh])
            # 左下圆角
            for i in range(20):
                a = -math.pi - math.pi / 2 * i / 19
                points.append(bx_body + cr + cr * math.cos(a))
                points.append(by + bh - cr + cr * math.sin(a))
            points.extend([bx_body, by + bh - cr, bx_body, by + cr])

            canvas.create_polygon(points, fill=BUBBLE_ME, outline=BUBBLE_ME, smooth=False)
            canvas.create_text(bx_body + pad_x, by + pad_y, text=text, font=font,
                               fill=TEXT_COLOR, width=max_w, anchor=tk.NW)
            _draw_avatar(canvas, av_cx, av_cy, AVATAR_ME, "我")
            return by + bh

        def _draw_time_tag(canvas, y, time_text, canvas_w):
            """居中时间标签 - 微信风格：纯文字无背景"""
            font = ("Microsoft YaHei", 9)
            tmp = canvas.create_text(0, 0, text=time_text, font=font, anchor=tk.NW)
            bbox = canvas.bbox(tmp)
            canvas.delete(tmp)
            if not bbox:
                return y
            tw = bbox[2] - bbox[0]
            cx = (canvas_w - tw) / 2
            canvas.create_text(cx, y, text=time_text, font=font, fill=TIME_FG, anchor=tk.NW)
            return y + (bbox[3] - bbox[1])

        def _draw_source_tag(canvas, y, src_text, src_color, canvas_w):
            """居中来源小标签"""
            font = ("Microsoft YaHei", 7)
            tmp = canvas.create_text(0, 0, text=src_text, font=font, anchor=tk.NW)
            bbox = canvas.bbox(tmp)
            canvas.delete(tmp)
            if not bbox:
                return y
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            px, py = 4, 1
            bw = tw + px * 2
            cx = (canvas_w - bw) / 2
            canvas.create_rectangle(cx, y, cx + bw, y + th + py * 2, fill=src_color, outline=src_color)
            canvas.create_text(cx + px, y + py, text=src_text, font=font, fill="white", anchor=tk.NW)
            return y + th + py * 2

        def render(idx):
            """渲染第idx个日期的聊天记录"""
            if not dates or idx < 0 or idx >= len(dates):
                return
            current_date_idx[0] = idx
            date_str = dates[idx]

            # 更新顶部日期
            try:
                d_obj = dt.strptime(date_str, "%Y-%m-%d")
                weekdays = ["一", "二", "三", "四", "五", "六", "日"]
                date_var.set(f"{date_str}  周{weekdays[d_obj.weekday()]}")
            except Exception:
                date_var.set(date_str)

            # 箭头状态
            btn_prev.config(fg="#576B95" if idx > 0 else "#D5D5D5")
            btn_next.config(fg="#576B95" if idx < len(dates) - 1 else "#D5D5D5")

            chat_canvas.delete("all")

            content = read_log(date_str)
            if content is None:
                cw = chat_canvas.winfo_width()
                if cw < 100:
                    cw = 480
                chat_canvas.create_text(cw / 2, 200, text="暂无聊天记录",
                                        font=("Microsoft YaHei", 14), fill="#999999")
                count_var.set("")
                return

            canvas_w = chat_canvas.winfo_width()
            if canvas_w < 100:
                canvas_w = 480

            y = 16
            reply_count = 0
            in_context = False

            for line in content.split("\n"):
                if line.startswith("# "):
                    continue
                elif line.startswith("### "):
                    reply_count += 1
                    parts = line[4:].split(" [", 1)
                    time_part = parts[0]
                    source_part = parts[1].rstrip("]") if len(parts) > 1 else ""

                    y = _draw_time_tag(chat_canvas, y, time_part, canvas_w)
                    y += 4

                    src_lower = source_part.lower()
                    if src_lower in source_names:
                        y = _draw_source_tag(chat_canvas, y,
                                             source_names[src_lower],
                                             source_colors.get(src_lower, "#999"),
                                             canvas_w)
                        y += 2
                    y += 16  # 时间与首条消息间距

                elif line.startswith("> 对方:"):
                    text = line[7:]
                    y = _draw_bubble_other(chat_canvas, y, text, canvas_w)
                    y += 16  # 微信：不同发送方间距

                elif line.startswith("> 我:"):
                    text = line[5:]
                    y = _draw_bubble_me(chat_canvas, y, text, canvas_w)
                    y += 16  # 微信：不同发送方间距

                elif line == ">" or line == "```":
                    continue
                elif line == "---":
                    y += 6
                elif line.startswith("<details>"):
                    in_context = True
                elif line.startswith("</details>"):
                    in_context = False
                elif line.startswith("<summary>"):
                    pass
                elif in_context and line.strip():
                    pass
                elif line.strip():
                    pass

            chat_canvas.config(scrollregion=(0, 0, canvas_w, y + 20))
            chat_canvas.yview_moveto(0)  # 滚到顶部
            count_var.set(f"{reply_count} 条" if reply_count else "")

        # 箭头点击
        def on_prev(event):
            if current_date_idx[0] > 0:
                win.update_idletasks()
                render(current_date_idx[0] - 1)

        def on_next(event):
            if current_date_idx[0] < len(dates) - 1:
                win.update_idletasks()
                render(current_date_idx[0] + 1)

        btn_prev.bind("<Button-1>", on_prev)
        btn_next.bind("<Button-1>", on_next)

        # === 点击日期弹出日历控件 ===
        import calendar as cal_mod

        def _show_calendar(event):
            """弹出日历控件，有记录的日期高亮可点击"""
            if not dates:
                return

            dates_set = set(dates)
            # 从当前日期确定初始月份
            cur_date = dates[current_date_idx[0]] if dates else None
            if cur_date:
                try:
                    cd = dt.strptime(cur_date, "%Y-%m-%d")
                    init_year, init_month = cd.year, cd.month
                except Exception:
                    init_year, init_month = dt.now().year, dt.now().month
            else:
                init_year, init_month = dt.now().year, dt.now().month

            popup = tk.Toplevel(win)
            popup.title("选择日期")
            popup.configure(bg="white")
            popup.resizable(False, False)
            popup.transient(win)
            popup.grab_set()

            # 定位在日期标签下方
            lbl_x = date_lbl.winfo_rootx() - win.winfo_rootx()
            popup_x = win.winfo_rootx() + lbl_x - 80
            popup_y = win.winfo_rooty() + nav_bar.winfo_height() + 4
            popup.geometry(f"+{popup_x}+{popup_y}")

            outer = tk.Frame(popup, bg="white", highlightbackground="#D5D5D5",
                             highlightthickness=1, padx=6, pady=6)
            outer.pack()

            # 月份导航
            month_var = tk.StringVar()
            month_nav = tk.Frame(outer, bg="white")
            month_nav.pack(fill=tk.X, pady=(0, 4))

            btn_m_prev = tk.Label(month_nav, text="◀", font=("Microsoft YaHei", 10),
                                  bg="white", fg="#576B95", cursor="hand2")
            btn_m_prev.pack(side=tk.LEFT, padx=4)
            month_lbl = tk.Label(month_nav, textvariable=month_var,
                                 font=("Microsoft YaHei", 11, "bold"),
                                 bg="white", fg="#1C1C1C", width=12)
            month_lbl.pack(side=tk.LEFT, expand=True)
            btn_m_next = tk.Label(month_nav, text="▶", font=("Microsoft YaHei", 10),
                                  bg="white", fg="#576B95", cursor="hand2")
            btn_m_next.pack(side=tk.RIGHT, padx=4)

            # 星期头
            wk_frame = tk.Frame(outer, bg="white")
            wk_frame.pack(fill=tk.X)
            for w in ["一", "二", "三", "四", "五", "六", "日"]:
                tk.Label(wk_frame, text=w, font=("Microsoft YaHei", 9),
                         bg="white", fg="#999999", width=4).pack(side=tk.LEFT)

            # 日期网格
            grid_frame = tk.Frame(outer, bg="white")
            grid_frame.pack(fill=tk.X)

            display_year = [init_year]
            display_month = [init_month]
            day_labels = []  # (label_widget, day_number)

            def refresh_month():
                y, m = display_year[0], display_month[0]
                month_var.set(f"{y}年 {m:02d}月")

                # 清除旧网格
                for w in grid_frame.winfo_children():
                    w.destroy()
                day_labels.clear()

                # 该月第一天星期几（0=周一）
                first_wday = cal_mod.weekday(y, m, 1)  # 0=Mon
                month_days = cal_mod.monthrange(y, m)[1]

                # 前面空位
                for _ in range(first_wday):
                    tk.Label(grid_frame, text="", font=("Microsoft YaHei", 10),
                             bg="white", width=4, height=1).pack(side=tk.LEFT)

                row_frame = tk.Frame(grid_frame, bg="white")
                row_frame.pack(fill=tk.X)
                col = first_wday

                for day in range(1, month_days + 1):
                    date_str = f"{y}-{m:02d}-{day:02d}"
                    has_record = date_str in dates_set
                    is_selected = (cur_date == date_str)

                    if col > 0 and col % 7 == 0:
                        row_frame = tk.Frame(grid_frame, bg="white")
                        row_frame.pack(fill=tk.X)

                    if has_record:
                        bg_c = "#07C160" if is_selected else "white"
                        fg_c = "white" if is_selected else "#1C1C1C"
                        lbl = tk.Label(row_frame, text=str(day),
                                       font=("Microsoft YaHei", 10, "bold"),
                                       bg=bg_c, fg=fg_c, width=4, height=1,
                                       cursor="hand2", relief=tk.FLAT)
                        lbl.bind("<Button-1>", lambda e, ds=date_str: _pick_date(ds))
                        # 悬停效果
                        lbl.bind("<Enter>", lambda e, l=lbl: l.config(bg="#E8F5E9") if not is_selected else None)
                        lbl.bind("<Leave>", lambda e, l=lbl: l.config(bg="white") if not is_selected else None)
                    else:
                        lbl = tk.Label(row_frame, text=str(day),
                                       font=("Microsoft YaHei", 10),
                                       bg="white", fg="#D5D5D5", width=4, height=1)

                    lbl.pack(side=tk.LEFT)
                    day_labels.append((lbl, day))
                    col += 1

            def _pick_date(date_str):
                if date_str in dates:
                    idx = dates.index(date_str)
                    popup.destroy()
                    win.update_idletasks()
                    render(idx)

            def _prev_month(event):
                m = display_month[0] - 1
                y = display_year[0]
                if m < 1:
                    m = 12
                    y -= 1
                display_year[0] = y
                display_month[0] = m
                refresh_month()

            def _next_month(event):
                m = display_month[0] + 1
                y = display_year[0]
                if m > 12:
                    m = 1
                    y += 1
                display_year[0] = y
                display_month[0] = m
                refresh_month()

            btn_m_prev.bind("<Button-1>", _prev_month)
            btn_m_next.bind("<Button-1>", _next_month)

            refresh_month()

            popup.bind("<Escape>", lambda e: popup.destroy())
            popup.focus_set()

        date_lbl.bind("<Button-1>", _show_calendar)

        # 初始渲染
        if dates:
            win.update_idletasks()
            render(0)
        else:
            date_var.set("暂无记录")

        # 窗口resize时重新渲染
        def on_resize(event):
            if dates:
                render(current_date_idx[0])
        chat_canvas.bind("<Configure>", lambda e: on_resize(e))
    
    def _on_region_settings(self):
        """打开区域设置编辑器"""
        open_region_editor()
    
    def _update_stats(self):
        stats = get_stats()
        self.stats_var.set(f"记忆: {stats['total']}条 (选中{stats['candidate']} | 手动{stats['manual']})")
    
    def _check_wechat(self):
        status = get_wechat_status(monitor_index=self.selected_monitor)
        if status["found"]:
            self.status_var.set(f"微信已连接: {status['title']} ({status['size'][0]}x{status['size'][1]})")
        else:
            self.status_var.set("未检测到微信，请先打开微信PC端")
    
    def _set_status(self, text, color="black"):
        self.status_var.set(text)
    
    # ===== 手动模式操作 =====
    
    def _on_detect(self):
        """识别当前聊天"""
        if self.mode_var.get() == "auto":
            return
        
        self.btn_detect.config(state=tk.DISABLED)
        self.status_var.set("正在截图识别...")
        
        def task():
            try:
                img, hwnd = capture_wechat_chat_area(monitor_index=self.selected_monitor)
                if img is None:
                    self.root.after(0, lambda: self._set_status("未找到微信窗口"))
                    self.root.after(0, lambda: self.btn_detect.config(state=tk.NORMAL))
                    return
                
                self.chat_img = img
                img_width = img.size[0]
                
                debug_path = os.path.join(os.path.dirname(__file__), ".temp", "last_capture.png")
                os.makedirs(os.path.dirname(debug_path), exist_ok=True)
                img.save(debug_path)
                
                self.root.after(0, lambda: self.status_var.set("OCR识别中..."))
                ocr_items = ocr_image(img)
                ocr_items = filter_noise(ocr_items)
                
                if not ocr_items:
                    self.root.after(0, lambda: self._set_status("OCR未识别到任何文字"))
                    self.root.after(0, lambda: self.btn_detect.config(state=tk.NORMAL))
                    return
                
                self.messages = parse_messages(ocr_items, img_width)
                context = get_chat_context(self.messages)
                need_reply, reason = check_need_reply(self.messages)
                
                def update_ui():
                    self.ctx_text.config(state=tk.NORMAL)
                    self.ctx_text.delete(1.0, tk.END)
                    self.ctx_text.insert(tk.END, context)
                    self.ctx_text.config(state=tk.DISABLED)
                    
                    if need_reply:
                        self.reply_status_var.set(f"需要回复 - {reason}")
                        self.btn_generate.config(state=tk.NORMAL)
                    else:
                        self.reply_status_var.set(f"无需回复 - {reason}")
                        self.btn_generate.config(state=tk.DISABLED)
                    
                    self.status_var.set(f"识别完成: {len(self.messages)}条消息, OCR {len(ocr_items)}个文本块")
                    self.btn_detect.config(state=tk.NORMAL)
                
                self.root.after(0, update_ui)
                
            except Exception as e:
                self.root.after(0, lambda: self._set_status(f"识别失败: {e}"))
                self.root.after(0, lambda: self.btn_detect.config(state=tk.NORMAL))
        
        threading.Thread(target=task, daemon=True).start()
    
    def _on_generate(self):
        """生成候选回复"""
        if not self.messages:
            messagebox.showwarning("提示", "请先识别聊天内容")
            return
        
        cfg = load_config()
        if not cfg.get("api_key"):
            messagebox.showwarning("提示", "请先在设置中配置API Key")
            self._on_settings()
            return
        
        self.btn_generate.config(state=tk.DISABLED)
        self.status_var.set("正在生成候选回复...")
        
        def task():
            try:
                context = get_chat_context(self.messages)
                unreplied = get_unreplied_message(self.messages)
                self.last_unreplied = unreplied or ""
                
                memory = get_recent_replies(5)
                candidates = generate_replies(context, unreplied, memory, cfg)
                self.candidates = candidates
                
                def update_ui():
                    for i in range(3):
                        if i < len(candidates):
                            self.candidate_texts[i].set(candidates[i])
                        else:
                            self.candidate_texts[i].set("")
                    self.status_var.set(f"已生成 {len(candidates)} 条候选回复")
                    self.btn_generate.config(state=tk.NORMAL)
                
                self.root.after(0, update_ui)
                
            except Exception as e:
                self.root.after(0, lambda: self._set_status(f"生成失败: {e}"))
                self.root.after(0, lambda: self.btn_generate.config(state=tk.NORMAL))
        
        threading.Thread(target=task, daemon=True).start()
    
    def _on_edit(self, idx):
        """编辑候选回复"""
        if idx >= len(self.candidates):
            return
        
        edit_win = tk.Toplevel(self.root)
        edit_win.title(f"编辑回复{idx+1}")
        edit_win.geometry("400x200")
        
        text = tk.Text(edit_win, font=("Microsoft YaHei", 11), wrap=tk.WORD)
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text.insert(tk.END, self.candidate_texts[idx].get())
        
        def save():
            new_text = text.get(1.0, tk.END).strip()
            self.candidate_texts[idx].set(new_text)
            if idx < len(self.candidates):
                self.candidates[idx] = new_text
            edit_win.destroy()
        
        ttk.Button(edit_win, text="保存", command=save).pack(pady=5)
    
    def _on_send(self, idx):
        """发送候选回复到微信"""
        text = self.candidate_texts[idx].get()
        if not text:
            messagebox.showwarning("提示", "回复内容为空")
            return
        
        if not messagebox.askyesno("确认发送", f"将发送以下内容到微信:\n\n{text}\n\n确认?"):
            return
        
        self.status_var.set("正在发送...")
        ok, msg = send_to_wechat(text)
        if ok:
            self.status_var.set(f"已发送回复{idx+1}")
            add_reply_record(self.last_unreplied, text, "candidate")
            save_chat_record(self.last_unreplied, text, "candidate")
            self._update_stats()
        else:
            messagebox.showerror("发送失败", msg)
            self.status_var.set(f"发送失败: {msg}")
    
    def _on_copy(self, idx):
        """复制候选回复到剪贴板"""
        text = self.candidate_texts[idx].get()
        if text:
            copy_to_clipboard(text)
            self.status_var.set(f"已复制回复{idx+1}")
    
    def _on_manual_send(self):
        """手动输入并发送"""
        text = self.manual_entry.get().strip()
        if not text:
            return
        
        if not messagebox.askyesno("确认发送", f"将发送以下内容到微信:\n\n{text}\n\n确认?"):
            return
        
        self.status_var.set("正在发送...")
        ok, msg = send_to_wechat(text)
        if ok:
            self.status_var.set("已发送手动输入")
            add_reply_record(self.last_unreplied, text, "manual")
            save_chat_record(self.last_unreplied, text, "manual")
            self.manual_entry.delete(0, tk.END)
            self._update_stats()
        else:
            messagebox.showerror("发送失败", msg)
            self.status_var.set(f"发送失败: {msg}")
    
    def _on_manual_copy(self):
        """手动输入仅复制"""
        text = self.manual_entry.get().strip()
        if text:
            copy_to_clipboard(text)
            self.status_var.set("已复制手动输入")
    
    def _on_settings(self):
        """设置窗口"""
        cfg = load_config()
        
        win = tk.Toplevel(self.root)
        win.title("设置")
        win.geometry("520x400")
        win.grab_set()
        
        frame = ttk.Frame(win, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        row = 0
        ttk.Label(frame, text="API提供商:").grid(row=row, column=0, sticky=tk.W, pady=5)
        provider_var = tk.StringVar(value="zhipu" if "bigmodel" in cfg.get("api_url", "") else "deepseek" if "deepseek" in cfg.get("api_url", "") else "custom")
        provider_combo = ttk.Combobox(frame, textvariable=provider_var, values=["zhipu", "deepseek", "custom"], state="readonly", width=15)
        provider_combo.grid(row=row, column=1, columnspan=2, sticky=tk.W, pady=5)
        
        row += 1
        ttk.Label(frame, text="API地址:").grid(row=row, column=0, sticky=tk.W, pady=5)
        url_var = tk.StringVar(value=cfg.get("api_url", ""))
        url_entry = ttk.Entry(frame, textvariable=url_var, width=40)
        url_entry.grid(row=row, column=1, columnspan=2, sticky=tk.W, pady=5)
        
        row += 1
        ttk.Label(frame, text="API Key:").grid(row=row, column=0, sticky=tk.W, pady=5)
        key_var = tk.StringVar(value=cfg.get("api_key", ""))
        key_entry = ttk.Entry(frame, textvariable=key_var, width=40, show="*")
        key_entry.grid(row=row, column=1, columnspan=2, sticky=tk.W, pady=5)
        
        row += 1
        ttk.Label(frame, text="模型:").grid(row=row, column=0, sticky=tk.W, pady=5)
        model_var = tk.StringVar(value=cfg.get("model", ""))
        model_entry = ttk.Entry(frame, textvariable=model_var, width=40)
        model_entry.grid(row=row, column=1, columnspan=2, sticky=tk.W, pady=5)
        
        def on_provider_change(*args):
            p = provider_var.get()
            if p == "zhipu":
                url_var.set("https://open.bigmodel.cn/api/paas/v4/chat/completions")
                model_var.set("glm-4-flash")
            elif p == "deepseek":
                url_var.set("https://api.deepseek.com/v1/chat/completions")
                model_var.set("deepseek-chat")
        
        provider_combo.bind("<<ComboboxSelected>>", on_provider_change)
        
        row += 1
        test_result_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=test_result_var, foreground="green").grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=2)
        
        def do_test():
            test_result_var.set("测试中...")
            win.update()
            test_cfg = {
                "api_url": url_var.get(),
                "api_key": key_var.get(),
                "model": model_var.get(),
            }
            ok, msg = test_api_connection(test_cfg)
            if ok:
                test_result_var.set(f"连接成功: {msg}")
            else:
                test_result_var.set(f"连接失败: {msg}")
        
        row += 1
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=row, column=0, columnspan=3, pady=15)
        
        def _save_settings():
            cfg.update({"api_url": url_var.get(), "api_key": key_var.get(), "model": model_var.get()})
            save_config(cfg)
            win.destroy()
            self.status_var.set("设置已保存")
            self.model_var.set(f"模型: {model_var.get()}")

        ttk.Button(btn_frame, text="保存", command=_save_settings).pack(side=tk.LEFT, padx=10)
        
        ttk.Button(btn_frame, text="测试连接", command=do_test).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="取消", command=win.destroy).pack(side=tk.LEFT, padx=10)
    
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = WeChatAutoReplyApp()
    app.run()
