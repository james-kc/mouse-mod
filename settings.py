"""Application settings: JSON persistence for debounce + app options."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict

APP_NAME = "mouse-mod"


def config_path() -> str:
    """config.json next to the exe (frozen) or next to main.py (dev)."""
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
        else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "config.json")


DEFAULTS: Dict[str, Any] = {
    "autostart": False,
    # debouncer config keys are merged in at load time
}


class Settings:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or config_path()
        self.data: Dict[str, Any] = dict(DEFAULTS)

    def load(self) -> "Settings":
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                self.data = {**DEFAULTS, **loaded}
        except (OSError, json.JSONDecodeError):
            pass  # first run or corrupt file -> defaults
        return self

    def save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2, sort_keys=True)
        except OSError:
            pass  # read-only location: run without persistence

    @property
    def autostart(self) -> bool:
        return bool(self.data.get("autostart", False))

    @autostart.setter
    def autostart(self, value: bool) -> None:
        self.data["autostart"] = bool(value)

    @property
    def debounce(self) -> dict:
        return self.data.get("debounce", {})

    @debounce.setter
    def debounce(self, value: dict) -> None:
        self.data["debounce"] = value
