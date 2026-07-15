"""
消息发送模块
通过Win32 API将回复发送到微信：
1. 前置微信窗口
2. 用pyperclip写入剪贴板
3. 模拟Ctrl+V粘贴 + Enter发送
"""
import win32gui
import win32con
import ctypes
import time
import pyperclip


# Win32 常量
VK_CONTROL = 0x11
VK_RETURN = 0x0D
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002


def find_wechat_window():
    """查找微信窗口（支持多种类名）"""
    result = []
    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            if not title:
                return
            if cls == 'WeChatMainWndForPC' or (cls.startswith('Qt5') and 'QWindowIcon' in cls):
                if '微信' in title or 'WeChat' in title:
                    result.append(hwnd)
    win32gui.EnumWindows(callback, None)
    if result:
        return result[0]
    all_wechat = []
    def callback2(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            if title and ('微信' in title or 'WeChat' in title):
                if cls not in ('TkTopLevel', 'Tk', 'Python', 'ConsoleWindowClass'):
                    all_wechat.append(hwnd)
    win32gui.EnumWindows(callback2, None)
    return all_wechat[0] if all_wechat else None


def _bring_to_front(hwnd):
    """将窗口置顶"""
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
    time.sleep(0.5)


def _set_clipboard_text(text):
    """用pyperclip设置剪贴板文本"""
    try:
        pyperclip.copy(text)
        # 验证写入成功
        read_back = pyperclip.paste()
        if read_back == text:
            return True
        # pyperclip有时写入延迟，再试一次
        time.sleep(0.1)
        pyperclip.copy(text)
        return True
    except Exception as e:
        return False


def _key_press(vk_code):
    """模拟按下并释放一个键"""
    ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
    time.sleep(0.05)
    ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)


def _key_combo(vk1, vk2):
    """模拟组合键：按下vk1 → 按下vk2 → 释放vk2 → 释放vk1"""
    ctypes.windll.user32.keybd_event(vk1, 0, 0, 0)
    time.sleep(0.05)
    ctypes.windll.user32.keybd_event(vk2, 0, 0, 0)
    time.sleep(0.05)
    ctypes.windll.user32.keybd_event(vk2, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)
    ctypes.windll.user32.keybd_event(vk1, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.1)


def _click_input_box(hwnd):
    """点击微信输入框"""
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top

    # 输入框位置：聊天区域底部，水平居中于聊天区域
    # 左侧27%是会话列表，聊天区域从27%开始
    chat_start_x = left + int(width * 0.35)
    input_x = (chat_start_x + right) // 2
    # 输入框在窗口高度的70%位置附近
    input_y = top + int(height * 0.75)

    ctypes.windll.user32.SetCursorPos(input_x, input_y)
    time.sleep(0.1)
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.3)


def send_to_wechat(text, hwnd=None):
    """
    将文本发送到微信当前聊天窗口
    完整流程：前置窗口 → 点击输入框 → 剪贴板写入 → Ctrl+V粘贴 → Enter发送
    """
    if not hwnd:
        hwnd = find_wechat_window()
    if not hwnd:
        return False, "未找到微信窗口"

    # 1. 前置微信窗口
    _bring_to_front(hwnd)

    # 2. 点击输入框确保焦点在输入区域
    _click_input_box(hwnd)

    # 3. 将文本写入剪贴板
    ok = _set_clipboard_text(text)
    if not ok:
        return False, "写入剪贴板失败"

    # 4. Ctrl+V 粘贴
    _key_combo(VK_CONTROL, VK_V)
    time.sleep(0.5)

    # 5. Enter 发送
    _key_press(VK_RETURN)
    time.sleep(0.2)

    return True, "发送成功"


def copy_to_clipboard(text):
    """仅复制到剪贴板，不自动发送"""
    return _set_clipboard_text(text)


if __name__ == "__main__":
    print("测试发送模块 - 请确保微信已打开")
    hwnd = find_wechat_window()
    if hwnd:
        print(f"找到微信窗口: {hwnd}")
    else:
        print("未找到微信窗口")
    
    # 测试剪贴板
    ok = copy_to_clipboard("测试复制")
    print(f"复制结果: {ok}, 粘贴板内容: {pyperclip.paste()}")
