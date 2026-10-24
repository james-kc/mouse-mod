# mouse-mod

A lightweight Windows system-tray utility that debounces mouse buttons — it
filters the spurious double-clicks caused by worn-out switches (e.g. a faulty
middle click) before any application sees them.

Uses a low-level mouse hook (`WH_MOUSE_LL`); **no driver required**.

## Features

- Global mouse-click debounce with a master on/off switch
- Per-button configuration (Left / Right / Middle / X1 / X2):
  independent enable + threshold (0–300 ms, default 50 ms)
- Live click statistics: received vs. suppressed per button — doubles as a
  tester to verify a faulty switch in real time
- Optional "Start with Windows" (HKCU Run registry entry)
- System-tray app; settings persist to `config.json`

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\pythonw main.py
```

Look for the mouse icon in the system tray → right-click → **Settings**.

## Test

```powershell
.\.venv\Scripts\python -m pytest tests/
```

## How it works

- `debouncer.py` — pure per-button state machine; swallows a button-down that
  follows the previous accepted down within the threshold, along with its
  matching button-up (the OS button state always stays consistent).
- `mouse_hook.py` — installs `WH_MOUSE_LL` via ctypes on a dedicated thread
  with a Win32 message pump; returning 1 from the callback eats the event.
- `gui.py` / `tray.py` — CustomTkinter settings window + pystray icon; all
  cross-thread traffic goes through locks or a queue (Tk stays on the main
  thread).

## Caveats

- Low-level hooks cannot intercept clicks delivered to **elevated** apps
  (Task Manager, admin games) unless mouse-mod itself runs as administrator.
- Anti-cheat software in some games may ignore or block synthetic input
  filtering; a kernel-driver approach (e.g. Interception) would be the escape
  hatch if that ever matters.
