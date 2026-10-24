# mouse-mod

A lightweight Windows system-tray utility that debounces mouse buttons — filters
spurious double-clicks caused by worn-out switches (e.g. a faulty middle click).

Uses a low-level mouse hook (`WH_MOUSE_LL`); no driver required.

[![Development branch](https://img.shields.io/badge/development-feature%2Fdebounce--app-blue)](../../tree/feature/debounce-app)

## Features

- Per-button debounce thresholds (left, right, middle, X1, X2)
- Click statistics: received vs. suppressed, per button
- Launch with Windows option
- System-tray app with a small settings window

## Status

Early development.
