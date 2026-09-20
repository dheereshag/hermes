from __future__ import annotations

import json
import unittest

from src.config.config_manager import config
from src.core.telemetry import reset_state
from src.web.app import create_app
from src.web.auth import reset_auth_state
from src.web.server import FallbackWebServer


class TestFlaskDiagnosticsApp(unittest.TestCase):
    def setUp(self):
        reset_state()
        reset_auth_state()
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()

        # Obtain valid superadmin token for protected tests
        res = self.client.post(
            "/api/login",
            data=json.dumps({"userid": "superadmin", "password": "Gluvok@241821"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.auth_token = res.get_json()["token"]

    def test_get_index_html(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.content_type)
        html = res.get_data(as_text=True)
        self.assertIn("Gluvok Hermes", html)
        self.assertIn("tailwindcss", html)
        self.assertIn("NO_PLATE_DETECTED", html)
        self.assertIn("REJECTED_HUMAN_DETECTED", html)

    def test_subsystem_page_routes(self):
        for route in ("/scale", "/anpr", "/cloud", "/wifi", "/telemetry", "/errors", "/config"):
            res = self.client.get(route)
            self.assertEqual(res.status_code, 200)
            self.assertIn("text/html", res.content_type)

    def test_get_api_status(self):
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("scale", data)
        self.assertIn("argus", data)
        self.assertIn("cloud", data)
        self.assertIn("device_id", data["cloud"])
        self.assertIn("configured", data["cloud"])
        self.assertIn("spool", data)
        self.assertIn("events", data)


    def test_post_api_wifi_success(self):
        payload = {"ssid": "TestRouter_5G", "password": "SecretPassword123"}
        res = self.client.post(
            "/api/wifi",
            data=json.dumps(payload),
            headers={"X-Auth-Token": self.auth_token},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(config.wifi_ssid, "TestRouter_5G")
        self.assertEqual(config.wifi_password, "SecretPassword123")

    def test_post_api_wifi_empty_ssid_error(self):
        payload = {"ssid": "", "password": "password"}
        res = self.client.post(
            "/api/wifi",
            data=json.dumps(payload),
            headers={"X-Auth-Token": self.auth_token},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)

    def test_post_api_wifi_clear(self):
        res = self.client.post(
            "/api/wifi/clear",
            headers={"Authorization": f"Bearer {self.auth_token}"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(config.wifi_ssid, "")
        self.assertEqual(config.wifi_password, "")

    def test_post_api_config_success(self):
        payload = {
            "min_weight": 65.0,
            "serial_port": "/dev/ttyUSB0",
            "serial_baudrate": 9600,
            "anpr_camera_url": "http://192.168.1.150/snapshot",
            "auxiliary_camera_urls": ["http://192.168.1.151/snapshot"],
            "anpr_server_url": "http://127.0.0.1:8000/recognize",
            "device_id": "pi1",
            "device_key": "hardware123",
            "center_id": 5,
        }
        res = self.client.post(
            "/api/config",
            data=json.dumps(payload),
            headers={"Authorization": f"Bearer {self.auth_token}"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(config.weight_threshold, 65.0)
        self.assertEqual(config.serial_port, "/dev/ttyUSB0")
        self.assertEqual(config.serial_baudrate, 9600)
        self.assertEqual(config.device_id, "pi1")
        self.assertEqual(config.device_key, "hardware123")
        self.assertEqual(config.center_id, 5)


    def test_post_api_config_unauthorized(self):
        res = self.client.post(
            "/api/config",
            data=json.dumps({"min_weight": 100.0}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 401)

    def test_post_api_config_invalid_payload(self):
        res = self.client.post(
            "/api/config",
            data=json.dumps({"min_weight": -50.0}),
            headers={"X-Auth-Token": self.auth_token},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)

    def test_404_not_found(self):
        res = self.client.get("/api/unknown_endpoint")
        self.assertEqual(res.status_code, 404)
        data = res.get_json()
        self.assertIn("error", data)

    def test_server_lifecycle(self):
        server = FallbackWebServer(host="127.0.0.1", port=8991)
        server.start()
        self.assertTrue(server._is_running)
        server.stop()
        self.assertFalse(server._is_running)


if __name__ == "__main__":
    unittest.main()
