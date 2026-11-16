"""Windows notification icon with its own message loop; no Tk calls off-thread.

Uses the installed shell API, without adding another runtime dependency.
Callbacks are delivered to the Tk thread through a queue supplied by App.
"""
import ctypes as c
from ctypes import wintypes as w
import logging
import os
import threading

TRAY_TITLE='MacroDeck.Tray.N16R8'
RESTORE_MESSAGE=0x8003
CALLBACK_MESSAGE=0x8001
LOG=logging.getLogger('macrodeck')
LRESULT=c.c_ssize_t
WNDPROC=c.WINFUNCTYPE(LRESULT,w.HWND,w.UINT,w.WPARAM,w.LPARAM)

class WNDCLASS(c.Structure):
    _fields_=[('style',w.UINT),('lpfnWndProc',WNDPROC),('cbClsExtra',c.c_int),('cbWndExtra',c.c_int),
              ('hInstance',w.HINSTANCE),('hIcon',w.HICON),('hCursor',w.HANDLE),('hbrBackground',w.HANDLE),
              ('lpszMenuName',w.LPCWSTR),('lpszClassName',w.LPCWSTR)]

class GUID(c.Structure):
    _fields_=[('a',w.DWORD),('b',w.WORD),('d',w.WORD),('tail',c.c_ubyte*8)]

class NOTIFYICONDATA(c.Structure):
    _fields_=[('cbSize',w.DWORD),('hWnd',w.HWND),('uID',w.UINT),('uFlags',w.UINT),
              ('uCallbackMessage',w.UINT),('hIcon',w.HICON),('szTip',w.WCHAR*128),
              ('dwState',w.DWORD),('dwStateMask',w.DWORD),('szInfo',w.WCHAR*256),
              ('uVersion',w.UINT),('szInfoTitle',w.WCHAR*64),('dwInfoFlags',w.DWORD),
              ('guidItem',GUID),('hBalloonIcon',w.HICON)]


class TrayIcon:
    def __init__(self,icon_path,events):
        self.icon_path=str(icon_path);self.events=events
        self.hwnd=None;self.available=False;self.error=None
        self._ready=threading.Event();self._stopping=threading.Event()
        self.thread=threading.Thread(target=self._run,name='MacroDeck tray',daemon=True)

    def start(self):
        self.thread.start()
        if not self._ready.wait(3):
            self._stopping.set();return False
        return self.available

    def stop(self):
        self._stopping.set()
        if self.hwnd:self.user.PostMessageW(self.hwnd,0x10,0,0)
        if self.thread.is_alive():self.thread.join(timeout=1)

    def _api(self):
        self.user=c.WinDLL('user32',use_last_error=True)
        self.shell=c.WinDLL('shell32',use_last_error=True)
        self.kernel=c.WinDLL('kernel32',use_last_error=True)
        specs={
            'RegisterClassW':([c.POINTER(WNDCLASS)],w.WORD),
            'UnregisterClassW':([w.LPCWSTR,w.HINSTANCE],w.BOOL),
            'CreateWindowExW':([w.DWORD,w.LPCWSTR,w.LPCWSTR,w.DWORD,c.c_int,c.c_int,c.c_int,c.c_int,w.HWND,w.HMENU,w.HINSTANCE,c.c_void_p],w.HWND),
            'DefWindowProcW':([w.HWND,w.UINT,w.WPARAM,w.LPARAM],LRESULT),
            'DestroyWindow':([w.HWND],w.BOOL),
            'PostQuitMessage':([c.c_int],None),
            'PostMessageW':([w.HWND,w.UINT,w.WPARAM,w.LPARAM],w.BOOL),
            'GetMessageW':([c.POINTER(w.MSG),w.HWND,w.UINT,w.UINT],c.c_int),
            'TranslateMessage':([c.POINTER(w.MSG)],w.BOOL),
            'DispatchMessageW':([c.POINTER(w.MSG)],LRESULT),
            'RegisterWindowMessageW':([w.LPCWSTR],w.UINT),
            'LoadImageW':([w.HINSTANCE,w.LPCWSTR,w.UINT,c.c_int,c.c_int,w.UINT],w.HANDLE),
            'DestroyIcon':([w.HICON],w.BOOL),
            'CreatePopupMenu':([],w.HMENU),
            'AppendMenuW':([w.HMENU,w.UINT,c.c_size_t,w.LPCWSTR],w.BOOL),
            'SetMenuDefaultItem':([w.HMENU,w.UINT,w.UINT],w.BOOL),
            'GetCursorPos':([c.POINTER(w.POINT)],w.BOOL),
            'SetForegroundWindow':([w.HWND],w.BOOL),
            'TrackPopupMenu':([w.HMENU,w.UINT,c.c_int,c.c_int,c.c_int,w.HWND,c.c_void_p],w.UINT),
            'DestroyMenu':([w.HMENU],w.BOOL),
        }
        for name,(args,result) in specs.items():
            method=getattr(self.user,name);method.argtypes=args;method.restype=result
        self.shell.Shell_NotifyIconW.argtypes=[w.DWORD,c.POINTER(NOTIFYICONDATA)]
        self.shell.Shell_NotifyIconW.restype=w.BOOL
        self.kernel.GetModuleHandleW.argtypes=[w.LPCWSTR];self.kernel.GetModuleHandleW.restype=w.HMODULE

    def _add(self):
        self.available=bool(self.shell.Shell_NotifyIconW(0,c.byref(self.data)))
        return self.available

    def _menu(self):
        menu=self.user.CreatePopupMenu()
        if not menu:return
        try:
            self.user.AppendMenuW(menu,0,1,'MacroDeck’i aç')
            self.user.AppendMenuW(menu,0x800,0,None)
            self.user.AppendMenuW(menu,0,2,'Çıkış')
            self.user.SetMenuDefaultItem(menu,1,False)
            point=w.POINT();self.user.GetCursorPos(c.byref(point))
            self.user.SetForegroundWindow(self.hwnd)
            selected=self.user.TrackPopupMenu(menu,0x100|0x2,point.x,point.y,0,self.hwnd,None)
            self.user.PostMessageW(self.hwnd,0,0,0)
            if selected:self.events.put('show' if selected==1 else 'exit')
        finally:self.user.DestroyMenu(menu)

    def _window_proc(self,hwnd,message,wp,lp):
        try:
            if message==RESTORE_MESSAGE:self.events.put('show');return 0
            if message==self.taskbar_created:
                if not self._stopping.is_set():
                    if not self._add():self.events.put('unavailable')
                return 0
            if message==CALLBACK_MESSAGE:
                if lp==0x203:self.events.put('show') # WM_LBUTTONDBLCLK
                elif lp in (0x205,0x7b):self._menu() # right button / keyboard menu
                return 0
            if message==0x10:self.user.DestroyWindow(hwnd);return 0
            if message==0x2:self.user.PostQuitMessage(0);return 0
        except Exception:LOG.exception('Bildirim alanı işlemi başarısız')
        return self.user.DefWindowProcW(hwnd,message,wp,lp)

    def _run(self):
        icon=None;registered=False
        name=f'MacroDeck.Tray.{os.getpid()}'
        try:
            self._api()
            instance=self.kernel.GetModuleHandleW(None)
            self.taskbar_created=self.user.RegisterWindowMessageW('TaskbarCreated')
            if not self.taskbar_created:raise c.WinError(c.get_last_error())
            self.callback=WNDPROC(self._window_proc)
            wc=WNDCLASS();wc.lpfnWndProc=self.callback;wc.hInstance=instance;wc.lpszClassName=name
            if not self.user.RegisterClassW(c.byref(wc)):raise c.WinError(c.get_last_error())
            registered=True
            self.hwnd=self.user.CreateWindowExW(0,name,TRAY_TITLE,0,0,0,0,0,None,None,instance,None)
            if not self.hwnd:raise c.WinError(c.get_last_error())
            icon=self.user.LoadImageW(None,self.icon_path,1,0,0,0x10|0x40)
            if not icon:raise c.WinError(c.get_last_error())
            self.data=NOTIFYICONDATA();self.data.cbSize=c.sizeof(self.data)
            self.data.hWnd=self.hwnd;self.data.uID=1;self.data.uFlags=1|2|4
            self.data.uCallbackMessage=CALLBACK_MESSAGE;self.data.hIcon=icon
            self.data.szTip='MacroDeck Medya · Açmak için çift tıkla'
            if not self._add():raise RuntimeError('Bildirim alanına simge eklenemedi.')
            self._ready.set()
            if self._stopping.is_set():return
            message=w.MSG()
            while True:
                result=self.user.GetMessageW(c.byref(message),None,0,0)
                if result==0:break
                if result<0:raise c.WinError(c.get_last_error())
                self.user.TranslateMessage(c.byref(message));self.user.DispatchMessageW(c.byref(message))
        except Exception as exc:
            self.error=str(exc);LOG.exception('Bildirim alanı başlatılamadı')
            if self._ready.is_set() and not self._stopping.is_set():self.events.put('unavailable')
        finally:
            self.available=False;self._ready.set()
            if hasattr(self,'data'):self.shell.Shell_NotifyIconW(2,c.byref(self.data))
            if self.hwnd:self.user.DestroyWindow(self.hwnd);self.hwnd=None
            if icon:self.user.DestroyIcon(icon)
            if registered:self.user.UnregisterClassW(name,instance)
