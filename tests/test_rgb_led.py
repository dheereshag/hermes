"""test_rgb_led.py — Unit Tests for RGB LED Hardware Driver & State Controller."""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, call, patch

from src.core.stability import ScaleStabilityMachine
from src.devices.led.colors import LEDColor
from src.devices.led.controller import RGBLedController
from src.devices.led.driver import LEDHardwareDriver


class TestLEDHardwareDriver(unittest.TestCase):
    def test_driver_initialization_and_color_setting(self):
        driver = LEDHardwareDriver(red_pin=17, green_pin=27, blue_pin=22, active_high=False)
        self.assertTrue(driver.is_mock or len(driver.pins) == 3)
        driver.set_rgb(1, 0, 0)
        self.assertEqual(driver.current_values, (1, 0, 0))
        driver.set_rgb(0, 1, 0)
        self.assertEqual(driver.current_values, (0, 1, 0))
        driver.set_rgb(0, 0, 1)
        self.assertEqual(driver.current_values, (0, 0, 1))
        driver.close()
        self.assertEqual(len(driver.pins), 0)


class TestRGBLedController(unittest.TestCase):
    def setUp(self):
        self.mock_driver = MagicMock(spec=LEDHardwareDriver)
        self.controller = RGBLedController(driver=self.mock_driver)

    def tearDown(self):
        self.controller.cleanup()

    def test_idle_sets_green(self):
        self.controller.set_idle()
        self.assertEqual(self.controller.current_color, LEDColor.GREEN)
        self.mock_driver.set_rgb.assert_called_with(0, 1, 0)

    def test_startup_test_cycles_green_red_blue_then_idle(self):
        self.controller.startup_test(delay=0.01)
        expected_calls = [
            call(0, 1, 0),
            call(1, 0, 0),
            call(0, 0, 1),
            call(0, 1, 0),
        ]
        self.mock_driver.set_rgb.assert_has_calls(expected_calls)
        self.assertEqual(self.controller.current_color, LEDColor.GREEN)

    def test_active_sets_red(self):
        self.controller.set_active()
        self.assertEqual(self.controller.current_color, LEDColor.RED)
        self.mock_driver.set_rgb.assert_called_with(1, 0, 0)

    def test_cloud_success_reverts_to_green_when_idle(self):
        self.controller.set_idle()
        self.controller.trigger_cloud_success(duration=0.05)
        self.assertEqual(self.controller.current_color, LEDColor.BLUE)
        self.mock_driver.set_rgb.assert_called_with(0, 0, 1)

        time.sleep(0.1)
        self.assertEqual(self.controller.current_color, LEDColor.GREEN)
        self.mock_driver.set_rgb.assert_called_with(0, 1, 0)

    def test_cloud_success_reverts_to_red_when_session_still_active(self):
        self.controller.set_active()
        self.controller.trigger_cloud_success(duration=0.05)
        self.assertEqual(self.controller.current_color, LEDColor.BLUE)

        time.sleep(0.1)
        self.assertEqual(self.controller.current_color, LEDColor.RED)
        self.mock_driver.set_rgb.assert_called_with(1, 0, 0)

    def test_new_weight_cancels_blue_timer_immediately(self):
        self.controller.trigger_cloud_success(duration=1.0)
        self.assertEqual(self.controller.current_color, LEDColor.BLUE)

        self.controller.set_active()
        self.assertEqual(self.controller.current_color, LEDColor.RED)
        self.assertIsNone(self.controller._timer)

    def test_scale_zero_during_blue_preserves_blue_until_timeout(self):
        self.controller.set_active()
        self.controller.trigger_cloud_success(duration=0.08)
        self.assertEqual(self.controller.current_color, LEDColor.BLUE)

        # Vehicle leaves scale while Blue is still active
        self.controller.set_idle()
        # Should remain blue until timer expires
        self.assertEqual(self.controller.current_color, LEDColor.BLUE)

        time.sleep(0.12)
        # Should now resolve to Green
        self.assertEqual(self.controller.current_color, LEDColor.GREEN)


class TestStabilityLedIntegration(unittest.TestCase):
    def setUp(self):
        self.machine = ScaleStabilityMachine()

    @patch("src.devices.led_controller.set_active")
    @patch("src.devices.led_controller.set_idle")
    def test_stability_triggers_active_and_idle_led(self, mock_idle, mock_active):
        # Truck arrives: weight exceeds threshold
        self.machine.process_new_weight(500.0)
        mock_active.assert_called()

        # Weight remains on scale
        mock_idle.assert_not_called()

        # Truck leaves: weight returns to 0.0
        self.machine.process_new_weight(0.0)
        mock_idle.assert_called()


if __name__ == "__main__":
    unittest.main()
