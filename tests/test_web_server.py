from __future__ import annotations

import json
import unittest

from src.config import config
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

    def tearDown(self):
        config.load_settings()

    def test_get_index_html(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.content_type)
        html = res.get_data(as_text=True)
        self.assertIn("Gluvok Hermes", html)
        self.assertIn("/static/tailwindcss.js", html)
        self.assertIn("/static/lucide.min.js", html)
        self.assertNotIn("unpkg.com", html)
        self.assertNotIn("cdn.jsdelivr.net", html)
        self.assertIn("NO_PLATE_DETECTED", html)
        self.assertIn("REJECTED_HUMAN_DETECTED", html)

    def test_static_assets_served(self):
        res_tw = self.client.get("/static/tailwindcss.js")
        self.assertEqual(res_tw.status_code, 200)
        self.assertIn("javascript", res_tw.content_type)
        self.assertGreater(len(res_tw.get_data()), 1000)

        res_lucide = self.client.get("/static/lucide.min.js")
        self.assertEqual(res_lucide.status_code, 200)
        self.assertIn("javascript", res_lucide.content_type)
        self.assertGreater(len(res_lucide.get_data()), 1000)

    def test_subsystem_page_routes(self):
        for route in ("/scale", "/anpr", "/cloud", "/wifi", "/telemetry", "/errors", "/config", "/admin"):
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
        self.assertIn("configured", data["cloud"])
        self.assertNotIn("device_id", data["cloud"])
        self.assertNotIn("device_key", data["cloud"])
        self.assertNotIn("cameras", data)
        self.assertNotIn("anpr_camera_urls", data.get("config", {}))
        self.assertNotIn("serial_port", data.get("scale", {}))
        self.assertIn("spool", data)
        self.assertIn("events", data)

    def test_get_api_config_unauthorized(self):
        res = self.client.get("/api/config")
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertFalse(data.get("success", True))

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

    def test_get_api_config_excludes_credentials(self):
        res = self.client.get(
            "/api/config",
            headers={"Authorization": f"Bearer {self.auth_token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertNotIn("device_id", data)
        self.assertNotIn("device_key", data)
        self.assertIn("center_id", data)
        self.assertIn("anpr_camera_urls", data)

    def test_post_api_config_success(self):
        payload = {
            "serial_port": "/dev/ttyUSB0",
            "serial_baudrate": 9600,
            "anpr_camera_url": "http://192.168.1.150/snapshot",
            "auxiliary_camera_urls": ["http://192.168.1.151/snapshot"],
        }
        res = self.client.post(
            "/api/config",
            data=json.dumps(payload),
            headers={"Authorization": f"Bearer {self.auth_token}"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(config.weight_threshold, 70.0)
        self.assertEqual(config.serial_port, "/dev/ttyUSB0")
        self.assertEqual(config.serial_baudrate, 9600)
        self.assertEqual(config.device_id, "pi1")
        self.assertEqual(config.device_key, "hardware123")
        self.assertIn(config.center_id, (1, 5))
        self.assertEqual(config.anpr_camera_url, "http://192.168.1.150/snapshot")

    def test_post_api_config_with_multiple_anpr_cameras(self):
        payload = {
            "anpr_camera_urls": [
                "http://127.0.0.1:8999/front",
                "http://127.0.0.1:8999/rear",
            ],
            "auxiliary_camera_urls": ["http://127.0.0.1:8999/overview"],
        }
        res = self.client.post(
            "/api/config",
            data=json.dumps(payload),
            headers={"Authorization": f"Bearer {self.auth_token}"},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(config.anpr_camera_urls), 2)
        self.assertEqual(config.anpr_camera_urls[0], "http://127.0.0.1:8999/front")
        self.assertEqual(config.anpr_camera_urls[1], "http://127.0.0.1:8999/rear")
        self.assertEqual(config.anpr_camera_url, "http://127.0.0.1:8999/front")



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
