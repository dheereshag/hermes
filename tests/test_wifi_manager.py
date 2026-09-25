import unittest
from unittest.mock import MagicMock, patch

from src.devices.wifi import (
    connect_to_wifi,
    get_existing_profile,
    get_wifi_interface,
    is_hotspot_active,
    is_wifi_connected,
    start_emergency_hotspot,
    start_wifi_watchdog,
    stop_emergency_hotspot,
    stop_wifi_watchdog,
)


class TestWiFiManager(unittest.TestCase):
    def tearDown(self):
        stop_wifi_watchdog()
        stop_emergency_hotspot()

    @patch("src.devices.wifi.is_nmcli_available", return_value=True)
    @patch("src.devices.wifi.subprocess.run")
    def test_is_wifi_connected_true(self, mock_run, mock_nmcli):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "wifi:connected:Office_5G\nethernet:connected:Wired 1\n"
        mock_run.return_value = mock_res

        self.assertTrue(is_wifi_connected())

    @patch("src.devices.wifi.is_nmcli_available", return_value=True)
    @patch("src.devices.wifi.subprocess.run")
    def test_is_wifi_connected_false_when_disconnected(self, mock_run, mock_nmcli):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "wifi:disconnected:\nethernet:connected:Wired 1\n"
        mock_run.return_value = mock_res

        self.assertFalse(is_wifi_connected())

    @patch("src.devices.wifi.is_nmcli_available", return_value=True)
    @patch("src.devices.wifi.subprocess.run")
    def test_is_wifi_connected_false_when_in_hotspot_mode(self, mock_run, mock_nmcli):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "wifi:connected:hermes-hotspot\n"
        mock_run.return_value = mock_res

        # If connected connection is the hotspot itself, it shouldn't count as normal wifi
        self.assertFalse(is_wifi_connected())

    @patch("src.devices.wifi.is_nmcli_available", return_value=True)
    @patch("src.devices.wifi.subprocess.run")
    def test_start_and_stop_emergency_hotspot(self, mock_run, mock_nmcli):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "wifi:connected:hermes-hotspot\n"
        mock_run.return_value = mock_res

        # Start hotspot
        success = start_emergency_hotspot("hermes", "12345678")
        self.assertTrue(success)
        self.assertTrue(is_hotspot_active())

        # Stop hotspot
        mock_res.stdout = "wifi:disconnected:\n"
        stopped = stop_emergency_hotspot()
        self.assertTrue(stopped)
        self.assertFalse(is_hotspot_active())

    @patch("src.devices.wifi.is_nmcli_available", return_value=True)
    @patch("src.devices.wifi.subprocess.run")
    def test_is_hotspot_active_false_when_profile_deleted(self, mock_run, mock_nmcli):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "wifi:disconnected:\n"
        mock_run.return_value = mock_res

        self.assertFalse(is_hotspot_active())

    @patch("src.devices.wifi.is_nmcli_available", return_value=True)
    @patch("src.devices.wifi._activate_hotspot_connection")
    @patch("src.devices.wifi.is_hotspot_active", return_value=False)
    def test_hotspot_self_healing_recreates_when_deleted(self, mock_active, mock_activate, mock_nmcli):
        success = start_emergency_hotspot("hermes", "12345678")
        self.assertTrue(success)
        mock_activate.assert_called_once_with("hermes", "12345678")

    @patch("src.devices.wifi.is_nmcli_available", return_value=True)
    @patch("src.devices.wifi.subprocess.run")
    def test_connect_to_wifi_success(self, mock_run, mock_nmcli):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Device 'wlan0' successfully activated with 'Office_5G'."
        mock_run.return_value = mock_res

        success, msg = connect_to_wifi("Office_5G", "password123")
        self.assertTrue(success)
        self.assertIn("Successfully connected", msg)

    @patch("src.devices.wifi.is_nmcli_available", return_value=True)
    @patch("src.devices.wifi.subprocess.run")
    def test_connect_to_wifi_failure(self, mock_run, mock_nmcli):
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stderr = "Error: Secrets were required, but not provided."
        mock_run.return_value = mock_res

        success, msg = connect_to_wifi("Office_5G", "wrongpassword")
        self.assertFalse(success)
        self.assertIn("Failed to connect", msg)

    def test_connect_to_wifi_empty_ssid(self):
        success, msg = connect_to_wifi("", "password")
        self.assertFalse(success)
        self.assertIn("cannot be empty", msg)

    def test_watchdog_start_stop(self):
        start_wifi_watchdog(interval=0.5)
        stop_wifi_watchdog()

    @patch("src.devices.wifi.is_nmcli_available", return_value=True)
    @patch("src.devices.wifi.subprocess.run")
    def test_get_wifi_interface_detected(self, mock_run, mock_nmcli):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "eth0:ethernet\nwlan1:wifi\nlo:loopback\n"
        mock_run.return_value = mock_res

        self.assertEqual(get_wifi_interface(), "wlan1")

    @patch("src.devices.wifi.is_nmcli_available", return_value=True)
    @patch("src.devices.wifi.subprocess.run")
    def test_get_wifi_interface_fallback_wlan0(self, mock_run, mock_nmcli):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "eth0:ethernet\nlo:loopback\n"
        mock_run.return_value = mock_res

        self.assertEqual(get_wifi_interface(), "wlan0")

    @patch("src.devices.wifi.is_nmcli_available", return_value=False)
    def test_get_wifi_interface_no_nmcli(self, mock_nmcli):
        self.assertEqual(get_wifi_interface(), "wlan0")

    @patch("src.devices.wifi.is_nmcli_available", return_value=True)
    @patch("src.devices.wifi._activate_hotspot_connection")
    def test_start_emergency_hotspot_failure_logs_detail(self, mock_activate, mock_nmcli):
        import subprocess as sp
        mock_activate.side_effect = sp.CalledProcessError(
            4, ["nmcli", "connection", "add"], stderr="Insufficient privileges"
        )
        with self.assertLogs("src.devices.wifi", level="ERROR") as cm:
            success = start_emergency_hotspot("hermes", "12345678")
            self.assertFalse(success)
            self.assertTrue(any("Insufficient privileges" in msg for msg in cm.output))

    @patch("src.devices.wifi.is_nmcli_available", return_value=True)
    @patch("src.devices.wifi.subprocess.run")
    def test_get_existing_profile_found(self, mock_run, mock_nmcli):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Home_WiFi:802-11-wireless\nWired:ethernet\nOffice_5G:wifi\n"
        mock_run.return_value = mock_res

        self.assertEqual(get_existing_profile("Office_5G"), "Office_5G")

    @patch("src.devices.wifi.is_nmcli_available", return_value=True)
    @patch("src.devices.wifi.subprocess.run")
    def test_get_existing_profile_not_found(self, mock_run, mock_nmcli):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Home_WiFi:802-11-wireless\nWired:ethernet\n"
        mock_run.return_value = mock_res

        self.assertIsNone(get_existing_profile("Unknown_WiFi"))

    @patch("src.devices.wifi.is_nmcli_available", return_value=True)
    @patch("src.devices.wifi.get_existing_profile", return_value="Office_5G")
    @patch("src.devices.wifi._run_nmcli")
    def test_connect_to_wifi_reconnect_existing_profile(self, mock_nmcli, mock_get_profile, mock_avail):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_nmcli.return_value = mock_res

        success, msg = connect_to_wifi("Office_5G", "newpassword")
        self.assertTrue(success)
        self.assertIn("Successfully connected", msg)
        mock_nmcli.assert_any_call(["connection", "up", "id", "Office_5G"], timeout=20, check=False)


if __name__ == "__main__":
    unittest.main()
