"""driver.py — Low-Level Hardware Interface for RGB LED."""

from __future__ import annotations

import logging
from typing import Any

from gpiozero.exc import BadPinFactory, GPIODeviceError

from src.config.constants import (
    DEFAULT_LED_ACTIVE_HIGH,
    DEFAULT_LED_PIN_BLUE,
    DEFAULT_LED_PIN_GREEN,
    DEFAULT_LED_PIN_RED,
)

logger = logging.getLogger(__name__)


class LEDHardwareDriver:
    """Controls physical GPIO pins using gpiozero with mock fallback."""

    def __init__(
        self,
        red_pin: int = DEFAULT_LED_PIN_RED,
        green_pin: int = DEFAULT_LED_PIN_GREEN,
        blue_pin: int = DEFAULT_LED_PIN_BLUE,
        active_high: bool = DEFAULT_LED_ACTIVE_HIGH,
    ) -> None:
        self.red_pin = red_pin
        self.green_pin = green_pin
        self.blue_pin = blue_pin
        self.active_high = active_high
        self.is_mock = False
        self._led: Any = self._init_device()

    def _init_device(self) -> Any:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                from gpiozero import RGBLED
                return RGBLED(self.red_pin, self.green_pin, self.blue_pin, active_high=self.active_high, pwm=False)
            except (BadPinFactory, GPIODeviceError, ImportError, OSError, RuntimeError) as err:
                self.is_mock = True
                logger.warning(
                    "[LED Driver] Native GPIO unavailable (%s). Running in MOCK mode — physical pins will NOT change! "
                    "Install 'rpi-lgpio' on Raspberry Pi.", err
                )
                from gpiozero import RGBLED, Device
                from gpiozero.pins.mock import MockFactory
                Device.pin_factory = MockFactory()
                return RGBLED(self.red_pin, self.green_pin, self.blue_pin, active_high=self.active_high, pwm=False)

    def set_rgb(self, red: int, green: int, blue: int) -> None:
        """Sets the RGB LED color directly (0 or 1 per channel)."""
        if self._led is not None:
            self._led.color = (red, green, blue)

    def close(self) -> None:
        """Releases GPIO pins cleanly."""
        if self._led is not None:
            self._led.close()
            self._led = None
