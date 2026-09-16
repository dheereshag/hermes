from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

from src.config.config_manager import config
from src.core.telemetry import get_error_counts, get_system_events, reset_state
from src.integrations.gluvok import (
    _build_entry_payload,
    get_device_headers,
    post_to_cloud,
)


class TestCloudPost(unittest.TestCase):
    def setUp(self):
        reset_state()
        self.orig_device_id = config.device_id
        self.orig_device_key = config.device_key
        self.orig_center_id = config.center_id
        config.device_id = 42
        config.device_key = "hardware123"
        config.center_id = 1

    def tearDown(self):
        config.device_id = self.orig_device_id
        config.device_key = self.orig_device_key
        config.center_id = self.orig_center_id
        reset_state()

    def test_get_device_headers(self):
        headers = get_device_headers()
        self.assertEqual(headers["x-device-id"], "42")
        self.assertEqual(headers["x-device-key"], "hardware123")

    def test_build_entry_payload_structure(self):
        session = {
            "weight": 14250.5,
            "anpr_plate": "MH12AB1234",
            "cam1_final_image": b"fake_cam1_bytes",
            "auxiliary_images": {1: b"fake_aux1_bytes", 2: b"fake_aux2_bytes"},
        }
        payload = _build_entry_payload(session)

        self.assertEqual(payload["detected_vehicle_number"], "MH12AB1234")
        self.assertEqual(payload["weight"], 14250.5)
        self.assertEqual(payload["center_id"], 1)
        self.assertEqual(len(payload["images"]), 3)
        self.assertTrue(payload["images"][0].startswith("data:image/jpeg;base64,"))
        self.assertNotIn("status", payload)

    @patch("src.integrations.gluvok.requests.post")
    def test_post_to_cloud_success_201(self, mock_post: Mock):
        mock_resp = Mock(status_code=201, content=b'{"data": {"id": 99}}')
        mock_resp.json.return_value = {"data": {"id": 99}}
        mock_post.return_value = mock_resp

        session = {
            "weight": 35200.0,
            "anpr_plate": "DL1CAB1234",
            "cam1_final_image": b"truck_img",
            "auxiliary_images": {},
        }
        post_to_cloud(session)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        self.assertIn("headers", call_kwargs)
        headers = call_kwargs["headers"]
        self.assertEqual(headers["x-device-id"], "42")
        self.assertEqual(headers["x-device-key"], "hardware123")
        self.assertEqual(headers["Content-Type"], "application/json")

        payload = call_kwargs["json"]
        self.assertEqual(payload["detected_vehicle_number"], "DL1CAB1234")
        self.assertEqual(payload["weight"], 35200.0)
        self.assertEqual(len(session), 0)

        events = get_system_events()
        self.assertTrue(any("Entry #99 created" in ev["message"] for ev in events))

    @patch("src.integrations.gluvok.requests.post")
    def test_post_to_cloud_aborts_when_credentials_missing(self, mock_post: Mock):
        config.device_key = ""
        session = {"weight": 1000.0, "anpr_plate": "MH12AB1234"}

        post_to_cloud(session)

        mock_post.assert_not_called()
        error_counts = get_error_counts()
        self.assertGreaterEqual(error_counts.get("CLOUD_AUTH_FAILED", 0), 1)

    @patch("src.integrations.gluvok.requests.post")
    def test_post_to_cloud_401_unauthorized(self, mock_post: Mock):
        mock_resp = Mock(status_code=401, content=b"Unauthorized", text="Unauthorized")
        mock_post.return_value = mock_resp

        session = {"weight": 1000.0, "anpr_plate": "MH12AB1234"}
        post_to_cloud(session)

        error_counts = get_error_counts()
        self.assertGreaterEqual(error_counts.get("CLOUD_AUTH_FAILED", 0), 1)

    @patch("src.integrations.gluvok.requests.post")
    def test_post_to_cloud_403_forbidden(self, mock_post: Mock):
        mock_resp = Mock(status_code=403, content=b"Forbidden", text="Device deactivated")
        mock_post.return_value = mock_resp

        session = {"weight": 1000.0, "anpr_plate": "MH12AB1234"}
        post_to_cloud(session)

        error_counts = get_error_counts()
        self.assertGreaterEqual(error_counts.get("CLOUD_AUTH_FORBIDDEN", 0), 1)

    @patch("src.integrations.gluvok.requests.post")
    def test_post_to_cloud_400_bad_request(self, mock_post: Mock):
        mock_resp = Mock(status_code=400, content=b"Bad Request", text="Invalid weight")
        mock_post.return_value = mock_resp

        session = {"weight": -10.0, "anpr_plate": "MH12AB1234"}
        post_to_cloud(session)

        error_counts = get_error_counts()
        self.assertGreaterEqual(error_counts.get("CLOUD_VALIDATION_ERROR", 0), 1)

    @patch("src.integrations.gluvok.requests.post")
    def test_post_to_cloud_500_server_error(self, mock_post: Mock):
        mock_resp = Mock(status_code=500, content=b"Server Error", text="Internal Error")
        mock_post.return_value = mock_resp

        session = {"weight": 5000.0, "anpr_plate": "MH12AB1234"}
        post_to_cloud(session)

        error_counts = get_error_counts()
        self.assertGreaterEqual(error_counts.get("CLOUD_UPLOAD_ERROR", 0), 1)

    @patch("src.integrations.gluvok.requests.post")
    def test_post_to_cloud_network_exception(self, mock_post: Mock):
        mock_post.side_effect = requests.ConnectionError("Connection refused")

        session = {"weight": 5000.0, "anpr_plate": "MH12AB1234"}
        post_to_cloud(session)

        error_counts = get_error_counts()
        self.assertGreaterEqual(error_counts.get("CLOUD_UPLOAD_ERROR", 0), 1)


if __name__ == "__main__":
    unittest.main()
