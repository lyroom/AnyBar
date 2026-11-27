import ctypes
import subprocess
import sys
from ctypes import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
gdi32.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.GetPixel.restype = wintypes.COLORREF


DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_CAPTION = 0x00C00000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_FRAMECHANGED = 0x0020
SWP_HIDEWINDOW = 0x0080
HWND_TOP = 0
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2

user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = wintypes.HWND
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
user32.SetParent.restype = wintypes.HWND
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
kernel32 = ctypes.windll.kernel32
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
user32.RegisterClassW.argtypes = [ctypes.c_void_p]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                   wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_longlong
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL
user32.RedrawWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.HANDLE, wintypes.UINT]
user32.RedrawWindow.restype = wintypes.BOOL



def enable_dpi_awareness():
    try:
        user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    except OSError:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except OSError:
            user32.SetProcessDPIAware()


def get_system_dpi() -> int:
    try:
        user32.GetDpiForSystem.restype = wintypes.UINT
        return int(user32.GetDpiForSystem())
    except (OSError, AttributeError):
        return 96


def find_taskbar():
    return user32.FindWindowW("Shell_TrayWnd", None)


def find_tray_notify(taskbar_hwnd=None):
    if not taskbar_hwnd:
        taskbar_hwnd = find_taskbar()
    if not taskbar_hwnd:
        return None
    return user32.FindWindowExW(taskbar_hwnd, None, "TrayNotifyWnd", None)


def find_window_by_class(parent_hwnd, class_name):
    if not parent_hwnd:
        return None
    return user32.FindWindowExW(parent_hwnd, None, class_name, None)


def get_rect(hwnd):
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return (rect.left, rect.top, rect.right, rect.bottom)


def embed_in_taskbar(bar_hwnd, taskbar_hwnd):
    style = user32.GetWindowLongW(bar_hwnd, GWL_STYLE)
    style = (style & ~WS_CHILD) | WS_POPUP
    user32.SetWindowLongW(bar_hwnd, GWL_STYLE, style)
    ex = user32.GetWindowLongW(bar_hwnd, GWL_EXSTYLE)
    ex = ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    user32.SetWindowLongW(bar_hwnd, GWL_EXSTYLE, ex)
    user32.SetParent(bar_hwnd, taskbar_hwnd)


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)
_host_class_registered = False
_host_wndproc_ref = None


def _host_wndproc(hwnd, msg, wparam, lparam):
    if msg == 0x0084:
        return -1
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def create_taskbar_host(taskbar_hwnd, x, y, w, h):
    global _host_class_registered, _host_wndproc_ref
    if not _host_class_registered:
        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]
        _host_wndproc_ref = WNDPROC(_host_wndproc)
        wc = WNDCLASSW()
        wc.lpfnWndProc = _host_wndproc_ref
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.lpszClassName = "AnyBarHostWnd"
        if not user32.RegisterClassW(ctypes.byref(wc)):
            return 0
        _host_class_registered = True
    return user32.CreateWindowExW(
        0, "AnyBarHostWnd", "", 0x40000000 | 0x10000000,
        int(x), int(y), int(w), int(h), taskbar_hwnd, 0,
        kernel32.GetModuleHandleW(None), 0)


def move_host_window(hwnd, x, y, w, h):
    user32.SetWindowPos(hwnd, 0, int(x), int(y), int(w), int(h),
                        SWP_NOACTIVATE | 0x0004)


def destroy_host_window(hwnd):
    user32.DestroyWindow(hwnd)


def invalidate_taskbar(taskbar_hwnd=None):
    """通知 Shell_TrayWnd 及其子窗口重绘暴露区域，消除胶囊收缩或移动后的背景残影。"""
    if not taskbar_hwnd:
        taskbar_hwnd = find_taskbar()
    if not taskbar_hwnd:
        return
    try:
        # RDW_INVALIDATE(0x1) | RDW_ERASE(0x4) | RDW_ALLCHILDREN(0x80)
        user32.RedrawWindow(taskbar_hwnd, None, None, 0x0001 | 0x0004 | 0x0080)
    except OSError:
        pass


def detach_from_host(hwnd):
    """把条窗从 Host 中转窗口摘出为独立的隐藏弹出窗口。

    销毁 Host（或进程 teardown）前必须先解除父子关系：父窗口销毁时
    系统会连带销毁全部子窗口，Qt 侧即收到 external WM_DESTROY 报错。
    """
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    user32.SetWindowLongW(hwnd, GWL_STYLE, (style & ~WS_CHILD) | WS_POPUP)
    user32.SetParent(hwnd, None)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
                        | SWP_HIDEWINDOW | SWP_FRAMECHANGED)



def set_topmost_flag_child(hwnd):
    user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)


def set_child_pos(hwnd, x, y):
    SWP_NOZORDER = 0x0004
    user32.SetWindowPos(hwnd, 0, int(x), int(y), 0, 0,
                        SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)



def tray_notify_left_in_taskbar():
    taskbar = find_taskbar()
    if not taskbar:
        return None
    tb_rect = get_rect(taskbar)
    if not tb_rect:
        return None
    tray = find_tray_notify(taskbar)
    if tray:
        tray_rect = get_rect(tray)
        if tray_rect:
            return tray_rect[0] - tb_rect[0], tray_rect[3] - tray_rect[1]
    return None, None


def set_taskbar_child_pos(hwnd, x, y, w, h):
    user32.SetWindowPos(hwnd, HWND_TOP, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)


def set_topmost_flag(hwnd):
    r = get_rect(hwnd)
    if r:
        hit = user32.WindowFromPoint(wintypes.POINT((r[0] + r[2]) // 2, (r[1] + r[3]) // 2))
        if hit and hit != hwnd:
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_NOACTIVATE)


def get_foreground_window():
    return user32.GetForegroundWindow()


def get_foreground_class() -> str:
    fg = get_foreground_window()
    if not fg:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(fg, buf, 256)
    return buf.value


def is_fullscreen_window(hwnd, screen_w, screen_h):
    if not hwnd:
        return False
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    if buf.value in ("Progman", "WorkerW"):
        return False
    try:
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    except OSError:
        ex = 0
    if ex & WS_EX_TOOLWINDOW:
        return False
    r = get_rect(hwnd)
    if not r:
        return False
    return (r[2] - r[0]) >= screen_w and (r[3] - r[1]) >= screen_h



_SHELL_HOST_PROCS = {"shellexperiencehost.exe", "shellhost.exe",
                      "startmenuexperiencehost.exe", "searchhost.exe",
                      "textinputhost.exe"}


def get_window_process_name(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(260)
        size = wintypes.DWORD(260)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value.replace("/", "\\").split("\\")[-1].lower()
        return ""
    finally:
        kernel32.CloseHandle(h)

def is_fullscreen_active(screen_w, screen_h):
    fg = get_foreground_window()
    if not fg:
        return False
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(fg, buf, 256)
    if buf.value in ("Progman", "WorkerW", "Shell_TrayWnd",
                     "Windows.UI.Composition.DesktopWindowContentBridge"):
        return False
    if buf.value == "Windows.UI.Core.CoreWindow":
        if get_window_process_name(fg) in _SHELL_HOST_PROCS:
            return False
    return is_fullscreen_window(fg, screen_w, screen_h)


def taskbar_auto_hidden(tb_rect, screen_w, screen_h):
    left, top, right, bottom = tb_rect
    if top >= screen_h - 2:
        return True
    if bottom <= 2:
        return True
    if left >= screen_w - 2:
        return True
    if right <= 2:
        return True
    return False

_UIA_PS = """
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
$tb=[System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ClassNameProperty,'Shell_TrayWnd'))
if(-not $tb){Write-Output '0 0 0';exit}
$tbr=$tb.Current.BoundingRectangle
$a=$tb.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
$ir=0.0;$tl=0.0;$rr=0.0
foreach($e in $a){$c=$e.Current;$r=$c.BoundingRectangle;if($c.ClassName -eq 'Taskbar.TaskListButtonAutomationPeer' -and -not $r.IsEmpty -and $r.Top -ge $tbr.Top - 2 -and $r.Bottom -le $tbr.Bottom + 2 -and $r.Right -gt $ir){$ir=[double]$r.Right}if($c.ClassName -eq 'TrayNotifyWnd' -and -not $r.IsEmpty){$tl=[double]$r.Left}if($c.ClassName -eq 'ReBarWindow32' -and -not $r.IsEmpty){$rr=[double]$r.Right}}
Write-Output ($ir.ToString()+' '+$tl.ToString()+' '+$rr.ToString())
"""


_SUBPROC_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _load_native_uia():
    """加载微型原生 C++ 动态库（taskbar_native.dll），实现 0 进程毫秒级 UIA 图标右缘直接查找。"""
    try:
        import sys
        from pathlib import Path
        candidate_dirs = [
            Path(__file__).resolve().parent,
            Path(__file__).resolve().parent.parent,
            Path(__file__).resolve().parent.parent.parent,
            Path(sys.executable).parent,
        ]
        if hasattr(sys, "_MEIPASS"):
            candidate_dirs.insert(0, Path(sys._MEIPASS))
            candidate_dirs.insert(1, Path(sys._MEIPASS) / "app" / "platform")
            candidate_dirs.insert(2, Path(sys._MEIPASS) / "app")
        for d in candidate_dirs:
            p = d / "taskbar_native.dll"
            if p.exists():
                dll = ctypes.CDLL(str(p))
                fn = dll.find_icon_right_edge_native
                fn.argtypes = [ctypes.c_int, ctypes.c_int]
                fn.restype = ctypes.c_int
                return fn
    except Exception:
        pass
    return None


_NATIVE_UIA_FUNC = _load_native_uia()


def find_icon_right_edge_uia(tray_left_phys, rebar_right_phys):
    # 1. 优先使用微型原生 C++ 动态库直接查找（毫秒级、0 子进程、0 额外开销）
    if _NATIVE_UIA_FUNC is not None:
        try:
            v = _NATIVE_UIA_FUNC(int(tray_left_phys), int(rebar_right_phys))
            if v and v > 0:
                return v
        except Exception:
            pass

    # 2. 平滑回退机制：若原生 DLL 未命中，执行 PowerShell 进程探测
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _UIA_PS],
            capture_output=True, text=True, timeout=1.5,
            creationflags=_SUBPROC_FLAGS,
        )
        parts = r.stdout.strip().split()
        if len(parts) < 3:
            return None
        ir, tl, rr = float(parts[0]), float(parts[1]), float(parts[2])
        if ir <= 0:
            return None
        if tl > 0 and rr > 0 and tray_left_phys > rebar_right_phys and (tl - rr) > 0:
            scale = (tl - rr) / (tray_left_phys - rebar_right_phys)
            return int(rebar_right_phys + (ir - rr) / scale)
        if tl > 0 and tray_left_phys > 0:
            return int(ir * tray_left_phys / tl)
    except Exception:
        return None
    return None

MONITOR_DEFAULTTONEAREST = 0x00000002


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


def get_monitor_info(hwnd):
    if not hwnd:
        return None
    try:
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HWND
        user32.GetMonitorInfoW.argtypes = [wintypes.HWND, ctypes.POINTER(_MONITORINFO)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(mi)
        if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return None
        return (mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right, mi.rcMonitor.bottom,
                mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom)
    except OSError:
        return None


def get_taskbar_edge(tb_rect, monitor_info):
    if not monitor_info:
        return "bottom"
    ml, mt, mr, mb = monitor_info[0], monitor_info[1], monitor_info[2], monitor_info[3]
    tb_left, tb_top, tb_right, tb_bottom = tb_rect
    if tb_bottom >= mb - 2:
        return "bottom"
    if tb_top <= mt + 2:
        return "top"
    if tb_right >= mr - 2:
        return "right"
    if tb_left <= ml + 2:
        return "left"
    return "bottom"

WINEVENT_OUTOFCONTEXT = 0x0000
EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_OBJECT_SHOW = 0x8002
EVENT_OBJECT_REORDER = 0x8004

WinEventProcType = ctypes.WINFUNCTYPE(
    None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
    wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)

_winevent_hook_handle = None
_winevent_proc_ref = None


def install_winevent_hook(callback):
    global _winevent_hook_handle, _winevent_proc_ref, _winevent_hook_handles
    try:
        user32.SetWinEventHook.restype = wintypes.HANDLE
        user32.SetWinEventHook.argtypes = [
            wintypes.DWORD, wintypes.DWORD, wintypes.HINSTANCE,
            WinEventProcType, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
        proc = WinEventProcType(callback)
        _winevent_proc_ref = proc
        _winevent_hook_handles = []
        for ev in (EVENT_SYSTEM_FOREGROUND, EVENT_OBJECT_SHOW, EVENT_OBJECT_REORDER):
            h = user32.SetWinEventHook(ev, ev, 0, proc, 0, 0, WINEVENT_OUTOFCONTEXT)
            if h:
                _winevent_hook_handles.append(h)
        _winevent_hook_handle = _winevent_hook_handles[0] if _winevent_hook_handles else 0
        return bool(_winevent_hook_handles)
    except OSError:
        return False


def uninstall_winevent_hook():
    global _winevent_hook_handle, _winevent_proc_ref, _winevent_hook_handles
    for h in (getattr(sys.modules[__name__], "_winevent_hook_handles", None) or []):
        try:
            user32.UnhookWinEvent(h)
        except OSError:
            pass
    _winevent_hook_handles = []
    _winevent_hook_handle = None
    _winevent_proc_ref = None

def sample_taskbar_bg_color(bar_rect):
    x0, y0, x1, y1 = bar_rect
    hdc = user32.GetDC(None)
    if not hdc:
        return None
    try:
        w = max(1, x1 - x0)
        cols = (int(x0 + w * 0.25), int(x0 + w * 0.5), int(x0 + w * 0.75))
        rows = {}
        for tag, ys in (("top", y0 - 3), ("bot", y1 + 3)):
            pts = []
            for x in cols:
                c = gdi32.GetPixel(hdc, x, ys)
                if c in (0xFFFFFFFF, 0):
                    continue
                pts.append((c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF))
            if not pts:
                continue
            n = len(pts)
            rows[tag] = (sum(p[0] for p in pts) // n,
                         sum(p[1] for p in pts) // n,
                         sum(p[2] for p in pts) // n)
        if "top" in rows and "bot" in rows:
            t, b = rows["top"], rows["bot"]
            return ((t[0] + b[0]) // 2, (t[1] + b[1]) // 2, (t[2] + b[2]) // 2)
        if rows:
            return next(iter(rows.values()))
        return None
    finally:
        user32.ReleaseDC(None, hdc)


# ---------------------------------------------------------------------------
# Windows DPAPI 数据保护（保护 API Key 等敏感凭据）
# ---------------------------------------------------------------------------
crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


crypt32.CryptProtectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    wintypes.LPCWSTR,
    ctypes.POINTER(DATA_BLOB),
    wintypes.LPVOID,
    wintypes.LPVOID,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
]
crypt32.CryptProtectData.restype = wintypes.BOOL

crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    ctypes.POINTER(wintypes.LPWSTR),
    ctypes.POINTER(DATA_BLOB),
    wintypes.LPVOID,
    wintypes.LPVOID,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
]
crypt32.CryptUnprotectData.restype = wintypes.BOOL

kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
kernel32.LocalFree.restype = wintypes.HLOCAL

CRYPTPROTECT_UI_FORBIDDEN = 0x01


def dpapi_protect(plaintext: bytes) -> bytes:
    """使用 Windows DPAPI 对当前登录用户的二进制数据进行对称加密。"""
    if not plaintext:
        return b""
    buf = ctypes.create_string_buffer(plaintext)
    blob_in = DATA_BLOB(len(plaintext), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    blob_out = DATA_BLOB()
    res = crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        "AnyBarSecret",
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(blob_out),
    )
    if not res:
        err = ctypes.get_last_error()
        raise OSError(f"CryptProtectData 失败 (错误码 {err})")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def dpapi_unprotect(ciphertext: bytes) -> bytes:
    """使用 Windows DPAPI 解密当前用户加密的二进制数据。"""
    if not ciphertext:
        return b""
    buf = ctypes.create_string_buffer(ciphertext)
    blob_in = DATA_BLOB(len(ciphertext), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    blob_out = DATA_BLOB()
    res = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(blob_out),
    )
    if not res:
        err = ctypes.get_last_error()
        raise OSError(f"CryptUnprotectData 失败 (错误码 {err})")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)
