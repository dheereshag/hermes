"""led package — RGB LED Hardware and State Machine."""

from __future__ import annotations

from src.devices.led.colors import LEDColor
from src.devices.led.controller import RGBLedController
from src.devices.led.driver import LEDHardwareDriver

led_controller = RGBLedController()

__all__ = [
    "LEDColor",
    "LEDHardwareDriver",
    "RGBLedController",
    "led_controller",
]
