"""Keep shortcut/login launches from competing for the same serial device."""
import atexit
import ctypes
import time

TITLE = "MacroDeck · Medya"
_handle = None


def acquire():
    global _handle
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    ctypes.set_last_error(0)
    handle = kernel.CreateMutexW(None, False, "Local\\MacroDeck.Media.N16R8")
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(handle)
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        user.FindWindowW.restype = ctypes.c_void_p
        user.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        user.PostMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
        user.PostMessageW.restype=ctypes.c_int
        for _ in range(10):
            from tray import TRAY_TITLE,RESTORE_MESSAGE
            tray=user.FindWindowW(None,TRAY_TITLE)
            if tray:
                user.PostMessageW(tray,RESTORE_MESSAGE,0,0)
                break
            window = user.FindWindowW(None, TITLE)
            if window:
                user.ShowWindow(window, 9)
                user.SetForegroundWindow(window)
                break
            time.sleep(0.1)
        return False
    _handle = handle
    atexit.register(kernel.CloseHandle, handle)
    return True
