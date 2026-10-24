"""Pure mouse-click debounce logic.

This module has no Win32 dependencies so it is fully unit-testable. Time is
injected via a ``clock`` callable (monotonic seconds), letting tests simulate
bouncing switch event streams deterministically.

State machine per button:

* On button **down**: if the previous accepted down happened less than
  ``threshold`` seconds ago, the event is a bounce -> swallow it and remember
  that the press was swallowed, so the matching **up** is swallowed too.
* On button **up**: swallow only if the matching down was swallowed.

The OS button state therefore always stays consistent: every accepted down is
followed by its accepted up, and vice versa.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Tuple

# Canonical button identifiers used throughout the app.
LEFT = "left"
RIGHT = "right"
MIDDLE = "middle"
X1 = "x1"
X2 = "x2"

BUTTONS = (LEFT, RIGHT, MIDDLE, X1, X2)

#: Default debounce threshold in milliseconds (typical bounce is < 20 ms,
#: real intentional double-clicks start well above 50 ms).
DEFAULT_THRESHOLD_MS = 50.0


@dataclass
class ButtonConfig:
    enabled: bool = True
    threshold_ms: float = DEFAULT_THRESHOLD_MS


@dataclass
class _ButtonState:
    last_down: float = float("-inf")  # time of last *accepted* down
    press_swallowed: bool = False     # whether current press' down was dropped


@dataclass
class _ClickStats:
    received: int = 0
    suppressed: int = 0


class Debouncer:
    """Decides, per mouse-button event, whether it should pass or be eaten.

    Thread-safe: the hook thread and GUI thread share one instance.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self.master_enabled = True
        self.config: Dict[str, ButtonConfig] = {b: ButtonConfig() for b in BUTTONS}
        self._state: Dict[str, _ButtonState] = {b: _ButtonState() for b in BUTTONS}
        self._stats: Dict[str, _ClickStats] = {b: _ClickStats() for b in BUTTONS}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def handle_event(self, button: str, is_down: bool) -> bool:
        """Process a click event. Returns True if the event should be
        *suppressed* (not delivered to the rest of the system)."""
        with self._lock:
            stats = self._stats[button]
            stats.received += 1

            if not (self.master_enabled and self.config[button].enabled):
                if is_down:
                    self._state[button].press_swallowed = False
                return False

            suppress = self._decide(button, is_down)
            if suppress:
                stats.suppressed += 1
            return suppress

    def set_button(self, button: str, enabled: bool, threshold_ms: float) -> None:
        if button not in BUTTONS:
            raise ValueError(f"unknown button: {button!r}")
        if threshold_ms < 0:
            raise ValueError("threshold must be >= 0")
        with self._lock:
            cfg = self.config[button]
            cfg.enabled = enabled
            cfg.threshold_ms = threshold_ms
            self._state[button] = _ButtonState()  # reset, avoid stale clocks

    def set_master(self, enabled: bool) -> None:
        with self._lock:
            self.master_enabled = enabled

    def get_stats(self) -> Dict[str, Tuple[int, int]]:
        """Return ``{button: (received, suppressed)}`` snapshot."""
        with self._lock:
            return {b: (s.received, s.suppressed) for b, s in self._stats.items()}

    def reset_stats(self) -> None:
        with self._lock:
            self._stats = {b: _ClickStats() for b in BUTTONS}

    def load_config(self, data: dict) -> None:
        """Apply a settings dict (see settings.py) safely."""
        with self._lock:
            self.master_enabled = bool(data.get("master_enabled", True))
            for button in BUTTONS:
                entry = data.get("buttons", {}).get(button, {})
                cfg = self.config[button]
                try:
                    cfg.enabled = bool(entry.get("enabled", cfg.enabled))
                    cfg.threshold_ms = max(0.0, float(entry.get(
                        "threshold_ms", cfg.threshold_ms)))
                except (TypeError, ValueError):
                    pass  # keep defaults on malformed config
                self._state[button] = _ButtonState()

    def dump_config(self) -> dict:
        with self._lock:
            return {
                "master_enabled": self.master_enabled,
                "buttons": {
                    b: {"enabled": c.enabled, "threshold_ms": c.threshold_ms}
                    for b, c in self.config.items()
                },
            }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _decide(self, button: str, is_down: bool) -> bool:
        state = self._state[button]
        if is_down:
            now = self._clock()
            threshold_s = self.config[button].threshold_ms / 1000.0
            if now - state.last_down < threshold_s:
                # Bounce: swallow this down (and remember to swallow its up).
                state.press_swallowed = True
                return True
            state.last_down = now
            state.press_swallowed = False
            return False
        else:
            if state.press_swallowed:
                state.press_swallowed = False
                return True
            return False
