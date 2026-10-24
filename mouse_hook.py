"""Low-level mouse hook (WH_MOUSE_LL) via raw ctypes.

A low-level hook must live on a thread that runs a Windows message pump, so
``start()`` spawns a dedicated thread that installs the hook and then sits in
``GetMessage``. The hook callback must stay extremely cheap (a few timestamp
comparisons) or Windows' LowLevelHooksTimeout will silently drop the hook.

Returning 1 from the callback swallows the event — that is how bounces are
filtered before any application sees them.
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable, Optional

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_MOUSE_LL = 14
HC_ACTION = 0
WM_QUIT = 0x0012

WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_XBUTTONDOWN, WM_XBUTTONUP = 0x020B, 0x020C
XBUTTON1, XBUTTON2 = 0x0001, 0x0002

from debouncer import LEFT, RIGHT, MIDDLE, X1, X2  # noqa: E402

_BUTTON_EVENTS = {
    WM_LBUTTONDOWN: (LEFT, True),
    WM_LBUTTONUP: (LEFT, False),
    WM_RBUTTONDOWN: (RIGHT, True),
    WM_RBUTTONUP: (RIGHT, False),
    WM_MBUTTONDOWN: (MIDDLE, True),
    WM_MBUTTONUP: (MIDDLE, False),
}


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int,
                              wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC,
                                     wintypes.HINSTANCE, wintypes.DWORD)
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int,
                                  wintypes.WPARAM, wintypes.LPARAM)
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),
                               wintypes.HWND, wintypes.UINT, wintypes.UINT)
user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM)
# Default c_int restype would truncate the 64-bit handle -> WinError 126.
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

#: Handler receives (button, is_down) and returns True to swallow the event.
EventHandler = Callable[[str, bool], bool]


class MouseHook:
    """Installs WH_MOUSE_LL on its own thread and routes click events to a
    handler. ``stop()`` is safe to call from any thread."""

    def __init__(self, handler: EventHandler) -> None:
        self._handler = handler
        self._hook: Optional[wintypes.HHOOK] = None
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._ready = threading.Event()
        self._install_error: Optional[BaseException] = None
        # Keep a strong reference so the callback is never garbage-collected.
        self._proc = HOOKPROC(self._hook_proc)

    # ------------------------------------------------------------------
    # Hook callback — MUST stay allocation-light and tiny.
    # ------------------------------------------------------------------
    def _hook_proc(self, nCode: int, wParam: int, lParam: int) -> int:
        if nCode == HC_ACTION:
            event = _BUTTON_EVENTS.get(wParam)
            if event is not None:
                button, is_down = event
            elif wParam in (WM_XBUTTONDOWN, WM_XBUTTONUP):
                info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                xbtn = info.mouseData >> 16
                button = X1 if xbtn == XBUTTON1 else X2
                is_down = wParam == WM_XBUTTONDOWN
            else:
                return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

            try:
                if self._handler(button, is_down):
                    return 1  # swallow the event
            except Exception:
                pass  # never propagate: the OS would drop our hook
        return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._ready.clear()
        self._install_error = None
        self._thread = threading.Thread(
            target=self._pump, name="mouse-hook", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5.0)
        if self._install_error is not None:
            raise RuntimeError(
                f"failed to install mouse hook: {self._install_error}")

    def stop(self) -> None:
        tid = self._thread_id
        if tid is not None:
            user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        self._thread_id = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    def _pump(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        try:
            hmod = kernel32.GetModuleHandleW(None)
            self._hook = user32.SetWindowsHookExW(
                WH_MOUSE_LL, self._proc, hmod, 0)
            if not self._hook:
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException as exc:  # report to start() instead of dying
            self._install_error = exc
            self._ready.set()
            return

        self._ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                pass  # pump is required; hook procs fire from within GetMessage
        finally:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
