"""
微信窗口截图模块
通过Win32 API定位微信PC端窗口并截图聊天区域
支持多显示器、区域配置保存、可视化区域设置
"""
import win32gui
import win32con
import ctypes
import ctypes.wintypes
from PIL import Image, ImageGrab
import time
import numpy as np
import json
import os


# ---- 关键：设置DPI感知，必须在任何窗口操作之前调用 ----
def enable_dpi_awareness():
    """使当前进程成为DPI感知，获取真实物理像素坐标而非虚拟化坐标"""
    try:
        # Windows 8.1+：Per-Monitor DPI Aware V2
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return True
    except Exception:
        pass
    try:
        # Windows 10 1703+：DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(0x80000003))
        return True
    except Exception:
        pass
    try:
        # Windows Vista+：System DPI Aware
        ctypes.windll.user32.SetProcessDPIAware()
        return True
    except Exception:
        pass
    return False


# 模块加载时立即设置DPI感知
_DPI_AWARE = enable_dpi_awareness()

# 配置文件路径
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "region_config.json")


# ---- Win32 结构体定义 ----
class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]

class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", ctypes.c_ulong),
        ("szDevice", ctypes.c_wchar * 32),
    ]


def get_monitors():
    """获取所有显示器信息"""
    monitors = []
    
    def callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(info))
        rect = info.rcMonitor
        monitors.append({
            "left": rect.left,
            "top": rect.top,
            "right": rect.right,
            "bottom": rect.bottom,
            "width": rect.right - rect.left,
            "height": rect.bottom - rect.top,
            "is_primary": info.dwFlags & 1 == 1,
        })
        return True
    
    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(RECT),
        ctypes.c_long,
    )
    
    ctypes.windll.user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(callback), 0)
    return monitors


def find_wechat_window():
    """查找微信主窗口，支持多种窗口类名"""
    # 微信PC端可能的窗口类名
    WECHAT_CLASSES = {
        'WeChatMainWndForPC',       # 经典版
        'Qt51514QWindowIcon',       # Qt5新版（类名含Qt版本号）
    }
    result = []
    qt_matches = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            if not title:
                return
            # 严格匹配已知微信类名
            if cls in WECHAT_CLASSES or cls.startswith('Qt5') and 'QWindowIcon' in cls:
                if '微信' in title or 'WeChat' in title:
                    result.append((hwnd, title, cls))
                    return
            # Qt类名匹配（微信新版用Qt5框架，版本号可能变化）
            if cls.startswith('Qt5') and 'QWindowIcon' in cls:
                if '微信' in title or 'WeChat' in title:
                    qt_matches.append((hwnd, title, cls))

    win32gui.EnumWindows(callback, None)
    if result:
        return result[0][0], result[0][1]
    if qt_matches:
        return qt_matches[0][0], qt_matches[0][1]
    return None, None


def load_region_config():
    """加载区域配置"""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # 默认配置：用比例表示，适应不同分辨率
    # 微信PC端典型布局：左侧导航(2%)+会话列表(25%)=27%，标题栏2%，输入框从70%开始
    return {
        "left_ratio": 0.27,     # 聊天区域左边界占窗口宽度比例
        "top_ratio": 0.02,      # 聊天区域上边界占窗口高度比例
        "right_ratio": 1.0,     # 聊天区域右边界占窗口宽度比例
        "bottom_ratio": 0.70,   # 聊天区域下边界占窗口高度比例（到输入框为止）
    }


def save_region_config(cfg):
    """保存区域配置"""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def capture_full_window(hwnd=None):
    """
    截取微信完整窗口（不裁剪）
    返回 (PIL.Image, hwnd, window_rect, client_offset)
    """
    if not hwnd:
        hwnd, _ = find_wechat_window()
    if not hwnd:
        return None, None, None, None

    # 恢复并前置窗口
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.2)
    
    try:
        ctypes.windll.user32.keybd_event(0, 0, 0, 0)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        try:
            win32gui.BringWindowToTop(hwnd)
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        except Exception:
            pass
    time.sleep(0.3)

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top

    # 客户区偏移
    client_abs_left, client_abs_top = win32gui.ClientToScreen(hwnd, (0, 0))
    border_left = client_abs_left - left
    border_top = client_abs_top - top

    # 截图
    img = ImageGrab.grab(bbox=(left, top, right, bottom))
    
    return img, hwnd, (left, top, right, bottom), (border_left, border_top)


def capture_wechat_chat_area(monitor_index=0):
    """
    截取微信聊天区域（根据区域配置裁剪）
    返回 (PIL.Image, hwnd) 或 (None, None)
    """
    img, hwnd, win_rect, (border_left, border_top) = capture_full_window()
    if img is None:
        return None, None

    width, height = img.size
    
    # 读取区域配置
    region_cfg = load_region_config()
    
    chat_left = int(width * region_cfg.get("left_ratio", 0.32))
    chat_top = int(height * region_cfg.get("top_ratio", 0.06))
    chat_right = int(width * region_cfg.get("right_ratio", 1.0))
    chat_bottom = int(height * region_cfg.get("bottom_ratio", 0.92))
    
    # 安全边界
    chat_left = max(0, min(chat_left, width - 100))
    chat_top = max(0, min(chat_top, height - 100))
    chat_right = max(chat_left + 100, min(chat_right, width))
    chat_bottom = max(chat_top + 100, min(chat_bottom, height))
    
    chat_img = img.crop((chat_left, chat_top, chat_right, chat_bottom))
    return chat_img, hwnd


def get_wechat_status(monitor_index=0):
    """获取微信窗口状态"""
    hwnd, title = find_wechat_window()
    if not hwnd:
        return {"found": False, "title": None}
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    
    monitors = get_monitors()
    current_monitor = 0
    win_cx = (left + right) // 2
    win_cy = (top + bottom) // 2
    for i, m in enumerate(monitors):
        if m["left"] <= win_cx <= m["right"] and m["top"] <= win_cy <= m["bottom"]:
            current_monitor = i
            break
    
    return {
        "found": True,
        "title": title,
        "hwnd": hwnd,
        "rect": (left, top, right, bottom),
        "size": (right - left, bottom - top),
        "monitor": current_monitor,
        "monitors": monitors,
    }


def open_region_editor():
    """
    打开区域设置编辑器
    截取微信完整窗口显示预览，手动输入比例值调整边界
    精心设计的界面：卡片式布局、深色预览区、清晰分区
    """
    import tkinter as tk
    from tkinter import ttk, scrolledtext
    import io
    
    # 截取完整窗口
    img, hwnd, win_rect, _ = capture_full_window()
    if img is None:
        import tkinter.messagebox as mb
        mb.showerror("错误", "未找到微信窗口，请先打开微信")
        return
    
    win_width, win_height = img.size
    region_cfg = load_region_config()
    
    # === 创建主窗口 ===
    editor = tk.Toplevel()
    editor.title("识别区域设置")
    editor.configure(bg="#f5f6fa")
    editor.resizable(False, False)
    
    # 计算预览尺寸 - 适配屏幕
    max_preview_w = 760
    max_preview_h = 320
    scale = min(max_preview_w / win_width, max_preview_h / win_height, 1.0)
    preview_w = int(win_width * scale)
    preview_h = int(win_height * scale)
    
    # === 顶部标题栏 ===
    title_bar = tk.Frame(editor, bg="#2c3e50", height=40)
    title_bar.pack(fill=tk.X)
    title_bar.pack_propagate(False)
    tk.Label(title_bar, text="识别区域设置", font=("Microsoft YaHei", 13, "bold"),
             bg="#2c3e50", fg="white").pack(side=tk.LEFT, padx=15, pady=8)
    tk.Label(title_bar, text="调整红色框范围，确定OCR识别的聊天区域", 
             font=("Microsoft YaHei", 9), bg="#2c3e50", fg="#bdc3c7").pack(side=tk.LEFT, padx=5, pady=8)
    
    # === 预览区域 ===
    preview_frame = tk.Frame(editor, bg="#1a1a2e", bd=1, relief=tk.SUNKEN)
    preview_frame.pack(fill=tk.X, padx=15, pady=(10, 5))
    
    canvas = tk.Canvas(preview_frame, width=preview_w, height=preview_h, bg="#1a1a2e",
                       highlightthickness=0)
    canvas.pack(padx=8, pady=8)
    
    # 预览图
    preview_img = img.resize((preview_w, preview_h), Image.LANCZOS)
    buf = io.BytesIO()
    preview_img.save(buf, format="PNG")
    buf.seek(0)
    photo = tk.PhotoImage(data=buf.read())
    canvas.create_image(0, 0, anchor=tk.NW, image=photo)
    canvas.image = photo
    
    # === 参数设置卡片 ===
    card = tk.Frame(editor, bg="white", bd=0, highlightbackground="#dcdde1", highlightthickness=1)
    card.pack(fill=tk.X, padx=15, pady=5)
    
    # 卡片标题
    card_header = tk.Frame(card, bg="white")
    card_header.pack(fill=tk.X, padx=15, pady=(10, 5))
    tk.Label(card_header, text="边界比例", font=("Microsoft YaHei", 11, "bold"),
             bg="white", fg="#2c3e50").pack(side=tk.LEFT)
    tk.Label(card_header, text="(占窗口宽度/高度的比例，0.00 ~ 1.00)", 
             font=("Microsoft YaHei", 8), bg="white", fg="#95a5a6").pack(side=tk.LEFT, padx=8)
    
    # 分隔线
    tk.Frame(card, bg="#ecf0f1", height=1).pack(fill=tk.X, padx=15, pady=2)
    
    # 输入区 - 2x2 网格，每个字段带图标和说明
    input_grid = tk.Frame(card, bg="white")
    input_grid.pack(fill=tk.X, padx=15, pady=10)
    
    # 当前值
    left_var = tk.StringVar(value=f"{region_cfg.get('left_ratio', 0.27):.2f}")
    top_var = tk.StringVar(value=f"{region_cfg.get('top_ratio', 0.02):.2f}")
    right_var = tk.StringVar(value=f"{region_cfg.get('right_ratio', 1.0):.2f}")
    bottom_var = tk.StringVar(value=f"{region_cfg.get('bottom_ratio', 0.70):.2f}")
    
    # 字段定义：图标、标签、变量、描述、颜色
    fields = [
        ("←", "左边界", left_var, "聊天区左侧起点", "#3498db"),
        ("↑", "上边界", top_var, "聊天区顶部起点", "#2ecc71"),
        ("→", "右边界", right_var, "聊天区右侧终点", "#e67e22"),
        ("↓", "下边界", bottom_var, "聊天区底部终点", "#e74c3c"),
    ]
    
    for idx, (icon, label, var, desc, color) in enumerate(fields):
        row_idx = idx // 2
        col_idx = idx % 2
        
        cell = tk.Frame(input_grid, bg="white")
        cell.grid(row=row_idx, column=col_idx, padx=(0, 30) if col_idx == 0 else 0, pady=6, sticky=tk.W)
        
        # 图标圆圈
        icon_label = tk.Label(cell, text=icon, font=("Consolas", 11, "bold"), 
                              bg=color, fg="white", width=2, height=1)
        icon_label.pack(side=tk.LEFT, padx=(0, 6))
        
        # 标签+描述
        text_col = tk.Frame(cell, bg="white")
        text_col.pack(side=tk.LEFT, padx=(0, 4))
        tk.Label(text_col, text=label, font=("Microsoft YaHei", 9, "bold"),
                 bg="white", fg="#2c3e50").pack(anchor=tk.W)
        tk.Label(text_col, text=desc, font=("Microsoft YaHei", 7),
                 bg="white", fg="#95a5a6").pack(anchor=tk.W)
        
        # 输入框
        entry = tk.Entry(cell, textvariable=var, width=6, font=("Consolas", 12, "bold"),
                         bg="#f8f9fa", fg="#2c3e50", relief=tk.FLAT, 
                         highlightbackground="#dcdde1", highlightthickness=1,
                         justify=tk.CENTER)
        entry.pack(side=tk.LEFT, ipady=3)
    
    # === OCR预览区 ===
    ocr_card = tk.Frame(editor, bg="white", bd=0, highlightbackground="#dcdde1", highlightthickness=1)
    ocr_card.pack(fill=tk.X, padx=15, pady=5)
    
    ocr_header = tk.Frame(ocr_card, bg="white")
    ocr_header.pack(fill=tk.X, padx=15, pady=(8, 3))
    tk.Label(ocr_header, text="OCR预览", font=("Microsoft YaHei", 11, "bold"),
             bg="white", fg="#2c3e50").pack(side=tk.LEFT)
    ocr_status_var = tk.StringVar(value="")
    tk.Label(ocr_header, textvariable=ocr_status_var, font=("Microsoft YaHei", 8),
             bg="white", fg="#95a5a6").pack(side=tk.RIGHT)
    
    tk.Frame(ocr_card, bg="#ecf0f1", height=1).pack(fill=tk.X, padx=15, pady=2)
    
    ocr_text = scrolledtext.ScrolledText(ocr_card, height=4, font=("Microsoft YaHei", 10), wrap=tk.WORD,
                                         bg="#f8f9fa", fg="#2c3e50", relief=tk.FLAT,
                                         highlightbackground="#dcdde1", highlightthickness=1,
                                         selectbackground="#3498db")
    ocr_text.pack(fill=tk.X, padx=15, pady=(3, 10))
    
    # 配置消息颜色标签
    ocr_text.tag_configure("other", foreground="#e74c3c", font=("Microsoft YaHei", 10, "bold"))
    ocr_text.tag_configure("me", foreground="#27ae60", font=("Microsoft YaHei", 10, "bold"))
    ocr_text.tag_configure("system", foreground="#95a5a6", font=("Microsoft YaHei", 9))
    ocr_text.tag_configure("error", foreground="#e74c3c")
    
    # === 功能函数（必须在按钮之前定义） ===
    def _get_values():
        """安全读取输入框的值"""
        try:
            l = float(left_var.get())
            t = float(top_var.get())
            r = float(right_var.get())
            b = float(bottom_var.get())
        except ValueError:
            return None
        l = max(0.0, min(l, 0.95))
        t = max(0.0, min(t, 0.95))
        r = max(0.05, min(r, 1.0))
        b = max(0.05, min(b, 1.0))
        if r <= l or b <= t:
            return None
        return l, t, r, b
    
    def update_preview(*args):
        """更新预览框和OCR"""
        vals = _get_values()
        if vals is None:
            ocr_text.config(state=tk.NORMAL)
            ocr_text.delete(1.0, tk.END)
            ocr_text.insert(tk.END, "比例值无效，请检查输入", "error")
            ocr_text.config(state=tk.DISABLED)
            ocr_status_var.set("")
            return
        
        l, t, r, b = vals
        
        # 绘制区域框 + 半透明遮罩效果
        canvas.delete("rect")
        canvas.delete("mask")
        
        pl = int(preview_w * l)
        pt = int(preview_h * t)
        pr = int(preview_w * r)
        pb = int(preview_h * b)
        
        # 半透明遮罩（用stipple模拟）
        canvas.create_rectangle(0, 0, preview_w, pt, fill="#1a1a2e", stipple="gray25", tag="mask")
        canvas.create_rectangle(0, pb, preview_w, preview_h, fill="#1a1a2e", stipple="gray25", tag="mask")
        canvas.create_rectangle(0, pt, pl, pb, fill="#1a1a2e", stipple="gray25", tag="mask")
        canvas.create_rectangle(pr, pt, preview_w, pb, fill="#1a1a2e", stipple="gray25", tag="mask")
        
        # 红色选区框 + 角标
        canvas.create_rectangle(pl, pt, pr, pb, outline="#e74c3c", width=2, tag="rect")
        # 四角标记
        corner_len = 12
        for cx, cy, dx, dy in [(pl, pt, 1, 1), (pr, pt, -1, 1), (pl, pb, 1, -1), (pr, pb, -1, -1)]:
            canvas.create_line(cx, cy, cx + corner_len * dx, cy, fill="#e74c3c", width=3, tag="rect")
            canvas.create_line(cx, cy, cx, cy + corner_len * dy, fill="#e74c3c", width=3, tag="rect")
        
        # 尺寸标注
        region_w = int(win_width * (r - l))
        region_h = int(win_height * (b - t))
        canvas.create_text((pl + pr) // 2, pt - 8, text=f"{region_w} x {region_h}",
                           fill="#e74c3c", font=("Consolas", 9, "bold"), tag="rect")
        
        # OCR预览
        ocr_status_var.set("识别中...")
        editor.update()
        
        cl = int(win_width * l)
        ct = int(win_height * t)
        cr = int(win_width * r)
        cb = int(win_height * b)
        
        crop_img = img.crop((cl, ct, cr, cb))
        try:
            from ocr_engine import ocr_image, filter_noise
            from parser import parse_messages
            items = ocr_image(crop_img)
            items = filter_noise(items)
            msgs = parse_messages(items, cr - cl)
            
            ocr_text.config(state=tk.NORMAL)
            ocr_text.delete(1.0, tk.END)
            
            if not msgs:
                ocr_text.insert(tk.END, "  未识别到消息", "system")
            else:
                other_count = sum(1 for m in msgs if m["sender"] == "other")
                me_count = sum(1 for m in msgs if m["sender"] == "me")
                ocr_status_var.set(f"对方 {other_count} 条 | 我方 {me_count} 条")
                
                for m in msgs:
                    tag = "other" if m["sender"] == "other" else "me"
                    prefix = "对方" if m["sender"] == "other" else "  我"
                    ocr_text.insert(tk.END, f"  [{prefix}] ", tag)
                    ocr_text.insert(tk.END, f"{m['text']}\n")
            
            ocr_text.config(state=tk.DISABLED)
        except Exception as e:
            ocr_text.config(state=tk.NORMAL)
            ocr_text.delete(1.0, tk.END)
            ocr_text.insert(tk.END, f"OCR预览出错: {e}", "error")
            ocr_text.config(state=tk.DISABLED)
            ocr_status_var.set("")
    
    def save_and_close():
        """保存配置并关闭"""
        vals = _get_values()
        if vals is None:
            import tkinter.messagebox as mb
            mb.showwarning("提示", "比例值无效，请检查输入")
            return
        l, t, r, b = vals
        new_cfg = {
            "left_ratio": round(l, 3),
            "top_ratio": round(t, 3),
            "right_ratio": round(r, 3),
            "bottom_ratio": round(b, 3),
        }
        save_region_config(new_cfg)
        editor.destroy()
    
    def reset_default():
        """恢复默认"""
        left_var.set("0.27")
        top_var.set("0.02")
        right_var.set("1.00")
        bottom_var.set("0.70")
        update_preview()
    
    # === 底部按钮栏 ===
    btn_bar = tk.Frame(editor, bg="#f5f6fa")
    btn_bar.pack(fill=tk.X, padx=15, pady=10)
    
    def make_button(parent, text, command, bg_color="#3498db", width=10):
        btn = tk.Button(parent, text=text, command=command, font=("Microsoft YaHei", 10),
                        bg=bg_color, fg="white", activebackground=bg_color, activeforeground="white",
                        relief=tk.FLAT, cursor="hand2", width=width, pady=4)
        return btn
    
    make_button(btn_bar, "预览效果", update_preview, "#3498db").pack(side=tk.LEFT, padx=(0, 8))
    make_button(btn_bar, "保存并关闭", save_and_close, "#27ae60").pack(side=tk.LEFT, padx=(0, 8))
    make_button(btn_bar, "恢复默认", reset_default, "#f39c12", 10).pack(side=tk.LEFT, padx=(0, 8))
    make_button(btn_bar, "取消", editor.destroy, "#95a5a6", 8).pack(side=tk.LEFT)
    
    # 初始绘制
    update_preview()
    
    # 让tk计算所有控件的真实尺寸，再设置窗口大小
    editor.update_idletasks()
    req_w = editor.winfo_reqwidth()
    req_h = editor.winfo_reqheight()
    # 加一点余量防止边缘被截断
    editor.geometry(f"{req_w + 20}x{req_h + 10}")
    
    editor.grab_set()
    editor.wait_window()


if __name__ == "__main__":
    monitors = get_monitors()
    print(f"检测到 {len(monitors)} 个显示器:")
    for i, m in enumerate(monitors):
        print(f"  显示器{i+1}: {m['width']}x{m['height']} at ({m['left']},{m['top']})")
    
    status = get_wechat_status()
    print(f"微信窗口状态: {status}")
    if status["found"]:
        img, hwnd = capture_wechat_chat_area()
        if img:
            img.save("test_capture.png")
            print(f"截图已保存: test_capture.png, 尺寸: {img.size}")
        else:
            print("截图失败")
    else:
        print("未找到微信窗口")
