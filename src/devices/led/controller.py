"""controller.py — RGB LED State Machine Controller."""

from __future__ import annotations

import logging
import threading

from src.devices.led.colors import LEDColor
from src.devices.led.driver import LEDHardwareDriver

logger = logging.getLogger(__name__)


class RGBLedController:
    """Orchestrates LED states: Green (Idle), Red (Active), Blue (Success)."""

    def __init__(self, driver: LEDHardwareDriver | None = None) -> None:
        self.driver = driver or LEDHardwareDriver()
        self._current_color = LEDColor.OFF
        self._is_active_session = False
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    @property
    def current_color(self) -> LEDColor:
        return self._current_color

    def _apply_color(self, color: LEDColor) -> None:
        self._current_color = color
        self.driver.set_rgb(*color.value)
        logger.info(f"[LED] State changed to {color.name}")

    def set_idle(self) -> None:
        """Sets LED to Green when scale returns to zero."""
        with self._lock:
            self._is_active_session = False
            if self._timer is None:
                self._apply_color(LEDColor.GREEN)

    def set_active(self) -> None:
        """Sets LED to Red when weight first encountered on scale."""
        with self._lock:
            self._is_active_session = True
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._apply_color(LEDColor.RED)

    def trigger_cloud_success(self, duration: float = 10.0) -> None:
        """Turns LED Blue for duration (seconds) after cloud upload success."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._apply_color(LEDColor.BLUE)
            self._timer = threading.Timer(duration, self._on_success_timeout)
            self._timer.daemon = True
            self._timer.start()

    def _on_success_timeout(self) -> None:
        with self._lock:
            self._timer = None
            self._apply_color(LEDColor.RED if self._is_active_session else LEDColor.GREEN)

    def cleanup(self) -> None:
        """Cancels timers and turns off LED."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._apply_color(LEDColor.OFF)
        self.driver.close()
