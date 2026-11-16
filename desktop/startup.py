"""Reversible current-user Windows login startup option."""
from pathlib import Path
import subprocess
import sys
import winreg

RUN_KEY=r'Software\Microsoft\Windows\CurrentVersion\Run'
NAME='MacroDeckMedia'

def command():
    pythonw=Path(sys.executable).with_name('pythonw.exe')
    return subprocess.list2cmdline([str(pythonw),str(Path(__file__).with_name('app.py')),'--minimized'])

def enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,RUN_KEY) as key:
            return winreg.QueryValueEx(key,NAME)[0]==command()
    except OSError:return False

def set_enabled(value):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,RUN_KEY) as key:
        if value:winreg.SetValueEx(key,NAME,0,winreg.REG_SZ,command())
        else:
            try:winreg.DeleteValue(key,NAME)
            except FileNotFoundError:pass
