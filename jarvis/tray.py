"""Windows notification icon using only the built-in Win32 APIs."""
import os
import threading


class TrayIcon:
    def __init__(self, commands):
        self.commands = commands
        self.ready = threading.Event()
        self.hwnd = None
        self.error = None
        self.thread = None

    def start(self):
        if os.name != 'nt':
            return False
        self.thread = threading.Thread(target=self._run, daemon=True, name='jarvis-tray')
        self.thread.start()
        self.ready.wait(2)
        return self.hwnd is not None and self.error is None

    def _run(self):
        import ctypes as c
        from ctypes import wintypes as w
        user = c.WinDLL('user32', use_last_error=True)
        shell = c.WinDLL('shell32', use_last_error=True)
        kernel = c.WinDLL('kernel32', use_last_error=True)
        callback = c.WINFUNCTYPE(c.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
        class WindowClass(c.Structure):
            _fields_ = [('style', w.UINT), ('proc', callback), ('clsExtra', c.c_int), ('wndExtra', c.c_int),
                        ('instance', w.HINSTANCE), ('icon', w.HICON), ('cursor', w.HANDLE),
                        ('brush', w.HANDLE), ('menu', w.LPCWSTR), ('name', w.LPCWSTR)]
        class IconData(c.Structure):
            _fields_ = [('size', w.DWORD), ('hwnd', w.HWND), ('id', w.UINT), ('flags', w.UINT),
                        ('callback', w.UINT), ('icon', w.HICON), ('tip', w.WCHAR*128),
                        ('state', w.DWORD), ('mask', w.DWORD), ('info', w.WCHAR*256),
                        ('version', w.UINT), ('title', w.WCHAR*64), ('infoFlags', w.DWORD),
                        ('guid', c.c_byte*16), ('balloon', w.HICON)]
        user.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        user.DefWindowProcW.restype = c.c_ssize_t
        user.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, c.c_int, c.c_int, c.c_int, c.c_int, w.HWND, w.HMENU, w.HINSTANCE, c.c_void_p]
        user.CreateWindowExW.restype = w.HWND
        user.RegisterClassW.argtypes = [c.POINTER(WindowClass)]
        user.LoadIconW.argtypes = [w.HINSTANCE, c.c_void_p]
        user.LoadIconW.restype = w.HICON
        user.CreatePopupMenu.restype = w.HMENU
        user.AppendMenuW.argtypes = [w.HMENU, w.UINT, c.c_size_t, w.LPCWSTR]
        user.TrackPopupMenu.argtypes = [w.HMENU, w.UINT, c.c_int, c.c_int, c.c_int, w.HWND, c.c_void_p]
        user.TrackPopupMenu.restype = w.UINT
        user.DestroyMenu.argtypes = [w.HMENU]
        user.SetForegroundWindow.argtypes = [w.HWND]
        user.DestroyWindow.argtypes = [w.HWND]
        shell.Shell_NotifyIconW.argtypes = [w.DWORD, c.POINTER(IconData)]
        kernel.GetModuleHandleW.argtypes = [w.LPCWSTR]
        kernel.GetModuleHandleW.restype = w.HMODULE
        data = None
        instance = kernel.GetModuleHandleW(None)
        name = 'JarvisTray' + str(os.getpid()) + str(id(self))
        @callback
        def proc(hwnd, message, wp, lp):
            if message == 0x8001:
                if lp == 0x202:
                    self.commands.put('show')
                elif lp == 0x205:
                    menu = user.CreatePopupMenu()
                    try:
                        actions = [('Show orb', 'show'), ('Conversation / projects', 'panel'), ('Mute / unmute microphone', 'mute'), ('Quit Jarvis', 'quit')]
                        for i, (label, _) in enumerate(actions, 1):
                            user.AppendMenuW(menu, 0, i, label)
                        point = w.POINT()
                        user.GetCursorPos(c.byref(point))
                        user.SetForegroundWindow(hwnd)
                        selected = user.TrackPopupMenu(menu, 0x102, point.x, point.y, 0, hwnd, None)
                        if 1 <= selected <= len(actions):
                            self.commands.put(actions[selected-1][1])
                    finally:
                        user.DestroyMenu(menu)
                return 0
            if message == 0x10:
                user.DestroyWindow(hwnd)
                return 0
            if message == 2:
                user.PostQuitMessage(0)
                return 0
            return user.DefWindowProcW(hwnd, message, wp, lp)
        try:
            cls = WindowClass(0, proc, 0, 0, instance, None, None, None, None, name)
            if not user.RegisterClassW(c.byref(cls)):
                raise c.WinError(c.get_last_error())
            hwnd = user.CreateWindowExW(0, name, 'Jarvis', 0, 0, 0, 0, 0, None, None, instance, None)
            if not hwnd:
                raise c.WinError(c.get_last_error())
            data = IconData()
            data.size, data.hwnd, data.id = c.sizeof(data), hwnd, 1
            data.flags, data.callback, data.icon, data.tip = 7, 0x8001, user.LoadIconW(None, c.c_void_p(32512)), 'Jarvis — show, mute, conversation, quit'
            if not shell.Shell_NotifyIconW(0, c.byref(data)):
                raise RuntimeError('Windows could not create the tray icon')
            self.hwnd = hwnd
            self.ready.set()
            msg = w.MSG()
            while user.GetMessageW(c.byref(msg), None, 0, 0) > 0:
                user.TranslateMessage(c.byref(msg))
                user.DispatchMessageW(c.byref(msg))
        except Exception as error:
            self.error = type(error).__name__
            self.ready.set()
        finally:
            if data is not None:
                shell.Shell_NotifyIconW(2, c.byref(data))
            self.hwnd = None

    def close(self):
        if self.hwnd is not None:
            import ctypes
            from ctypes import wintypes
            user = ctypes.WinDLL('user32')
            user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user.PostMessageW(self.hwnd, 0x10, 0, 0)
        if self.thread:
            self.thread.join(timeout=2)
