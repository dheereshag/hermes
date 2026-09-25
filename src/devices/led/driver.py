"""driver.py — Low-Level Hardware Interface for RGB LED using python-periphery."""
from __future__ import annotations

import glob
import logging
import os
from typing import Any

from periphery import GPIO, GPIOError

from src.config.constants import (
    DEFAULT_LED_ACTIVE_HIGH,
    DEFAULT_LED_PIN_BLUE,
    DEFAULT_LED_PIN_GREEN,
    DEFAULT_LED_PIN_RED,
)

logger = logging.getLogger(__name__)


def _open_gpio(pin: int) -> Any:
    for chip in ("/dev/gpiochip4", "/dev/gpiochip0") + tuple(sorted(glob.glob("/dev/gpiochip*"), reverse=True)):
        if os.path.exists(chip):
            try:
                return GPIO(chip, pin, "out")
            except (GPIOError, LookupError, OSError):
                logger.debug("Failed opening GPIO %d on chip %s", pin, chip)
    return GPIO(pin, "out")


class LEDHardwareDriver:
    """Controls physical GPIO pins using python-periphery with mock fallback."""

    def __init__(
        self,
        red_pin: int = DEFAULT_LED_PIN_RED,
        green_pin: int = DEFAULT_LED_PIN_GREEN,
        blue_pin: int = DEFAULT_LED_PIN_BLUE,
        active_high: bool = DEFAULT_LED_ACTIVE_HIGH,
    ) -> None:
        self.red_pin, self.green_pin, self.blue_pin = red_pin, green_pin, blue_pin
        self.active_high = active_high
        self.is_mock, self.pins, self.current_values = False, {}, (0, 0, 0)
        self._init_pins()

    def _init_pins(self) -> None:
        try:
            self.pins = {"r": _open_gpio(self.red_pin), "g": _open_gpio(self.green_pin), "b": _open_gpio(self.blue_pin)}
        except (GPIOError, LookupError, OSError) as err:
            self.is_mock = True
            logger.info("[LED Driver] Native GPIO unavailable (%s). Running in mock mode.", err)

    def set_rgb(self, red: int, green: int, blue: int) -> None:
        self.current_values = (red, green, blue)
        if not self.is_mock and self.pins:
            for key, val in (("r", red), ("g", green), ("b", blue)):
                if (pin := self.pins.get(key)) is not None:
                    pin.write(bool(val) if self.active_high else not bool(val))

    def close(self) -> None:
        for pin in self.pins.values():
            try:
                pin.close()
            except (GPIOError, OSError) as err:
                logger.debug("Error closing pin: %s", err)
        self.pins.clear()
