"""System-tray icon (pystray). Runs on its own thread; communicates with the
Tk main thread exclusively through a queue."""

from __future__ import annotations

import queue
from typing import Callable, Optional

import pystray
from PIL import Image, ImageDraw


def _make_icon_image(size: int = 64) -> Image.Image:
    """Generate a simple mouse-shaped icon (no asset files needed)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = size // 16
    d.rounded_rectangle([m, m, size - m, size - m], radius=size // 3,
                        fill=(35, 96, 180, 255))
    # mouse body
    cx, top, w, h = size // 2, size // 5, size // 4, size // 2
    d.rounded_rectangle([cx - w // 2, top, cx + w // 2, top + h],
                        radius=w // 2, fill=(240, 240, 240, 255))
    # button separator + scroll wheel
    d.line([cx - w // 2, top + h // 3, cx + w // 2, top + h // 3],
           fill=(35, 96, 180, 255), width=max(2, size // 32))
    d.line([cx, top, cx, top + h // 3],
           fill=(35, 96, 180, 255), width=max(2, size // 32))
    d.rounded_rectangle([cx - size // 32, top + h // 8,
                         cx + size // 32, top + h // 4],
                        radius=size // 64, fill=(220, 60, 60, 255))
    return img


class TrayApp:
    def __init__(self, inbox: "queue.Queue[str]",
                 is_enabled: Callable[[], bool],
                 on_toggle: Optional[Callable[[bool], None]] = None) -> None:
        self.inbox = inbox
        self._is_enabled = is_enabled
        self._on_toggle = on_toggle or (lambda _: None)

        menu = pystray.Menu(
            pystray.MenuItem("Settings", self._show_settings, default=True),
            pystray.MenuItem("Debouncing enabled", self._toggle,
                             checked=lambda item: self._is_enabled()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._exit),
        )
        self.icon = pystray.Icon("mouse-mod", _make_icon_image(),
                                 "mouse-mod — Mouse Debouncer", menu)

    # pystray menu callbacks run on pystray's thread --------------------
    def _show_settings(self, icon=None, item=None) -> None:
        self.inbox.put("show")

    def _toggle(self, icon=None, item=None) -> None:
        self._on_toggle(not self._is_enabled())
        self.icon.update_menu()

    def _exit(self, icon=None, item=None) -> None:
        self.inbox.put("quit")
        self.icon.stop()

    # ------------------------------------------------------------------
    def run(self) -> None:
        self.icon.run()  # call from a background thread
