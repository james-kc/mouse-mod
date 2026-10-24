"""CustomTkinter settings window for mouse-mod.

Owned by the main thread. The window starts hidden (tray app): the tray menu
drops messages into ``inbox`` which this class polls on the Tk loop —Tk must
never be touched from the hook or pystray threads.
"""

from __future__ import annotations

import queue
from typing import Callable, Optional

import customtkinter as ctk

import autostart
from debouncer import BUTTONS, Debouncer
from settings import Settings

BUTTON_LABELS = {
    "left": "Left",
    "right": "Right",
    "middle": "Middle",
    "x1": "Side (X1)",
    "x2": "Side (X2)",
}

MAX_THRESHOLD_MS = 300
POLL_MS = 250


class SettingsWindow:
    def __init__(self, debouncer: Debouncer, settings: Settings,
                 inbox: "queue.Queue[str]",
                 on_change: Optional[Callable[[], None]] = None,
                 on_quit: Optional[Callable[[], None]] = None) -> None:
        self.debouncer = debouncer
        self.settings = settings
        self.inbox = inbox
        self.on_change = on_change or (lambda: None)
        self._on_quit_cb = on_quit or (lambda: None)

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("mouse-mod")
        self.root.geometry("460x560")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._hide)
        self.root.withdraw()

        self._stat_labels = {}
        self._build()
        self._poll()
        self._refresh_stats()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self.master_var = ctk.BooleanVar(value=self.debouncer.master_enabled)
        ctk.CTkSwitch(
            self.root, text="Debouncing enabled", variable=self.master_var,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._apply_master,
        ).pack(anchor="w", padx=16, pady=(14, 10))

        frame = ctk.CTkFrame(self.root)
        frame.pack(fill="x", padx=16, pady=4)
        frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text="Button", font=ctk.CTkFont(weight="bold"),
                     width=90, anchor="w").grid(row=0, column=0, padx=10, pady=(10, 2))
        ctk.CTkLabel(frame, text="Threshold (ms)",
                     font=ctk.CTkFont(weight="bold")).grid(
                         row=0, column=1, columnspan=2, pady=(10, 2))
        ctk.CTkLabel(frame, text="Received / Suppressed",
                     font=ctk.CTkFont(weight="bold")).grid(
                         row=0, column=3, padx=10, pady=(10, 2))

        for i, button in enumerate(BUTTONS, start=1):
            cfg = self.debouncer.config[button]
            var = ctk.BooleanVar(value=cfg.enabled)
            ctk.CTkCheckBox(frame, text=BUTTON_LABELS[button],
                            variable=var, width=90,
                            command=lambda b=button: self._apply_button(b)
                            ).grid(row=i, column=0, sticky="w", padx=10)

            value_lbl = ctk.CTkLabel(frame, text=f"{cfg.threshold_ms:.0f}",
                                     width=34)
            slider = ctk.CTkSlider(
                frame, from_=0, to=MAX_THRESHOLD_MS, width=170,
                command=lambda v, b=button, lbl=value_lbl:
                    self._apply_button(b, lbl, v))
            slider.set(cfg.threshold_ms)
            slider.grid(row=i, column=1, padx=(4, 0), pady=6)
            value_lbl.grid(row=i, column=2, padx=(0, 4))

            stat_lbl = ctk.CTkLabel(frame, text="0 / 0", width=110, anchor="e")
            stat_lbl.grid(row=i, column=3, padx=10)
            self._stat_labels[button] = stat_lbl

            # Keep per-button widgets reachable for later updates.
            var._button = button  # type: ignore[attr-defined]
            setattr(self, f"_enabled_{button}", var)
            slider._button = button  # type: ignore[attr-defined]
            setattr(self, f"_slider_{button}", slider)

        actions = ctk.CTkFrame(self.root, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=(10, 4))
        ctk.CTkButton(actions, text="Reset counters", width=130,
                      command=self._reset_stats).pack(side="left")

        self.autostart_var = ctk.BooleanVar(value=self.settings.autostart)
        ctk.CTkCheckBox(actions, text="Start with Windows",
                        variable=self.autostart_var,
                        command=self._toggle_autostart).pack(side="right")

        self.status_var = ctk.StringVar(
            value="Click any mouse button — stats update live. "
                  "Close this window to return to the tray.")
        ctk.CTkLabel(self.root, textvariable=self.status_var,
                     wraplength=420, justify="left",
                     text_color=("gray30", "gray70")
                     ).pack(anchor="w", padx=16, pady=(8, 10))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _apply_master(self) -> None:
        self.debouncer.set_master(self.master_var.get())
        self.on_change()

    def _apply_button(self, button: str,
                      label: Optional[ctk.CTkLabel] = None,
                      value: Optional[float] = None) -> None:
        var = getattr(self, f"_enabled_{button}")
        slider = getattr(self, f"_slider_{button}")
        threshold = round(slider.get() if value is None else value)
        if label is not None:
            label.configure(text=str(threshold))
        self.debouncer.set_button(button, var.get(), float(threshold))
        self.on_change()

    def _reset_stats(self) -> None:
        self.debouncer.reset_stats()
        self._refresh_stats()

    def _toggle_autostart(self) -> None:
        want = self.autostart_var.get()
        try:
            autostart.set_enabled(want)
        except OSError as exc:
            self.autostart_var.set(False)
            self.status_var.set(f"Could not update autostart: {exc}")
            return
        self.settings.autostart = want
        self.settings.save()

    # ------------------------------------------------------------------
    # Pump + stats
    # ------------------------------------------------------------------
    def _poll(self) -> None:
        try:
            while True:
                msg = self.inbox.get_nowait()
                if msg == "show":
                    self._show()
                elif msg == "quit":
                    self._quit()
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _refresh_stats(self) -> None:
        for button, (received, suppressed) in self.debouncer.get_stats().items():
            self._stat_labels[button].configure(
                text=f"{received} / {suppressed}")
        self.root.after(POLL_MS, self._refresh_stats)

    def _show(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _hide(self) -> None:
        self.root.withdraw()

    def _quit(self) -> None:
        self._on_quit_cb()
        self.root.destroy()

    # ------------------------------------------------------------------
    def run(self) -> None:
        self.root.mainloop()
