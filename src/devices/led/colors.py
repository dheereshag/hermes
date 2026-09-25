"""colors.py — RGB LED Color Definitions."""

from __future__ import annotations

from enum import Enum


class LEDColor(Enum):
    OFF = (0, 0, 0)
    GREEN = (0, 1, 0)
    RED = (1, 0, 0)
    BLUE = (0, 0, 1)


__all__ = ["LEDColor"]
