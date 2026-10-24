"""mouse-mod entry point.

Threads:
  * main  — Tk/CustomTkinter event loop (Tk requires the main thread)
  * mouse-hook — WH_MOUSE_LL message pump (mouse_hook.py)
  * pystray — tray icon loop
All cross-thread traffic goes through plain function calls guarded by locks
(debouncer/settings) or the GUI inbox queue.
"""

from __future__ import annotations

import ctypes
import queue
import sys
import threading

from debouncer import Debouncer
from gui import SettingsWindow
from mouse_hook import MouseHook
from settings import Settings
from tray import TrayApp


_MUTEX_NAME = "Local\\mouse-mod-single-instance"
_ERROR_ALREADY_EXISTS = 183


def _acquire_single_instance() -> bool:
    """Named mutex guard: two instances would install two hooks and split
    the click statistics between them."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        ctypes.windll.user32.MessageBoxW(
            0, "mouse-mod is already running — check the system tray.",
            "mouse-mod", 0x40)
        return False
    return True


def main() -> int:
    if not _acquire_single_instance():
        return 1

    settings = Settings().load()

    debouncer = Debouncer()
    if settings.debounce:
        debouncer.load_config(settings.debounce)

    def persist() -> None:
        settings.debounce = debouncer.dump_config()
        settings.save()

    hook = MouseHook(debouncer.handle_event)
    hook.start()

    inbox: "queue.Queue[str]" = queue.Queue()

    def on_toggle(enabled: bool) -> None:
        debouncer.set_master(enabled)
        persist()

    def on_quit() -> None:
        persist()
        hook.stop()

    tray = TrayApp(inbox, is_enabled=lambda: debouncer.master_enabled,
                   on_toggle=on_toggle)
    tray_thread = threading.Thread(target=tray.run, name="tray", daemon=True)

    window = SettingsWindow(debouncer, settings, inbox,
                            on_change=persist, on_quit=on_quit)

    tray_thread.start()
    window.run()  # blocks; returns after Exit -> window destroyed

    on_quit()  # idempotent: make sure hook is down + settings saved
    return 0


if __name__ == "__main__":
    sys.exit(main())
