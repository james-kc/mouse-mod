"""Register/unregister the app to launch at Windows login (HKCU Run key)."""

from __future__ import annotations

import os
import sys
import winreg

APP_NAME = "mouse-mod"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launcher_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return f'"{pythonw if os.path.exists(pythonw) else sys.executable}" "{script}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
        return bool(value)
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                        winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ,
                              _launcher_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except OSError:
                pass  # wasn't registered
