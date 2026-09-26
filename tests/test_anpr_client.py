import unittest
from unittest.mock import MagicMock, patch

import requests

from src.integrations.anpr import (
    get_highest_frequency_plate,
    send_frame_to_anpr_server,
)


class TestANPRClient(unittest.TestCase):
    def test_send_frame_empty_bytes(self):
        plate, status = send_frame_to_anpr_server(b"")
        self.assertIsNone(plate)
        self.assertEqual(status, "EMPTY_IMAGE")

        plate_none, status_none = send_frame_to_anpr_server(None)
        self.assertIsNone(plate_none)
        self.assertEqual(status_none, "EMPTY_IMAGE")

    @patch("src.integrations.anpr.requests.post")
    def test_send_frame_argus_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "filename": "frame.jpg",
            "humans_outside": 0,
            "humans_inside": 0,
            "results": [
                {
                    "plate": "RJ09GA0165",
                    "vehicle_type": "car",
                    "state": "Rajasthan",
                    "raw_text": "RJ09GA0165",
                    "confidence": 0.98,
                }
            ],
            "execution_time_ms": 115.4,
        }
        mock_post.return_value = mock_response

        fake_img = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        plate, status = send_frame_to_anpr_server(fake_img, server_url="http://127.0.0.1:8000/recognize")

        self.assertEqual(plate, "RJ09GA0165")
        self.assertEqual(status, "SUCCESS")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "http://127.0.0.1:8000/recognize")
        self.assertIn("file", kwargs["files"])

    @patch("src.integrations.anpr.requests.post")
    def test_send_frame_argus_empty_results(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "filename": "frame.jpg",
            "humans_outside": 0,
            "humans_inside": 0,
            "results": [],
            "execution_time_ms": 42.1,
        }
        mock_post.return_value = mock_response

        plate, status = send_frame_to_anpr_server(b"fake-bytes")
        self.assertIsNone(plate)
        self.assertEqual(status, "NO_PLATE_DETECTED")

    @patch("src.integrations.anpr.requests.post")
    def test_send_frame_fallback_flat_json(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "plate": "MH12AB1234",
            "confidence": 0.95,
        }
        mock_post.return_value = mock_response

        plate, status = send_frame_to_anpr_server(b"fake-bytes")
        self.assertEqual(plate, "MH12AB1234")
        self.assertEqual(status, "SUCCESS")

    @patch("src.integrations.anpr.requests.post")
    def test_send_frame_timeout(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("Read timeout")
        plate, status = send_frame_to_anpr_server(b"fake-bytes")
        self.assertIsNone(plate)
        self.assertEqual(status, "ANPR_TIMEOUT")

    @patch("src.integrations.anpr.requests.post")
    def test_send_frame_connection_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")
        plate, status = send_frame_to_anpr_server(b"fake-bytes")
        self.assertIsNone(plate)
        self.assertEqual(status, "ANPR_CONNECTION_ERROR")

    @patch("src.integrations.anpr.requests.post")
    def test_send_frame_argus_multi_vehicle_picks_first(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "filename": "4.jpg",
            "humans_outside": 0,
            "humans_inside": 0,
            "results": [
                {
                    "plate": "RJ43GA2012",
                    "vehicle_type": "truck",
                    "state": "Rajasthan",
                    "raw_text": "m RJ43GA2012 SUPER FAST",
                    "confidence": 0.9993,
                    "box": [512, 387, 575, 409],
                },
                {
                    "plate": "RJ43GA2012",
                    "vehicle_type": "truck",
                    "state": "Rajasthan",
                    "raw_text": "TATA RJ436A.2012",
                    "confidence": 0.8568,
                    "box": [131, 400, 207, 423],
                },
            ],
            "execution_time_ms": 1915.68,
        }
        mock_post.return_value = mock_response

        plate, status = send_frame_to_anpr_server(b"fake-bytes")
        self.assertEqual(plate, "RJ43GA2012")
        self.assertEqual(status, "SUCCESS")

    @patch("src.integrations.anpr.requests.post")
    def test_send_frame_argus_multi_vehicle_different_plates_takes_first(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "filename": "multi.jpg",
            "humans_outside": 0,
            "humans_inside": 0,
            "results": [
                {
                    "plate": "RJ43GA2012",
                    "vehicle_type": "truck",
                    "confidence": 0.99,
                },
                {
                    "plate": "DL01AB9999",
                    "vehicle_type": "car",
                    "confidence": 0.95,
                },
            ],
            "execution_time_ms": 1500.0,
        }
        mock_post.return_value = mock_response

        plate, status = send_frame_to_anpr_server(b"fake-bytes")
        # results array is already sorted by Argus; results[0] is authoritative
        self.assertEqual(plate, "RJ43GA2012")
        self.assertEqual(status, "SUCCESS")

    @patch("src.integrations.anpr.requests.post")
    def test_send_frame_argus_first_plate_none_yields_no_plate(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "filename": "multi_unreadable.jpg",
            "results": [
                {
                    "plate": None,
                    "vehicle_type": "truck",
                    "confidence": 0.30,
                },
                {
                    "plate": "DL01AB9999",
                    "vehicle_type": "car",
                    "confidence": 0.95,
                },
            ],
            "execution_time_ms": 1200.0,
        }
        mock_post.return_value = mock_response

        plate, status = send_frame_to_anpr_server(b"fake-bytes")
        # Since results[0] is best candidate and has no plate, return NO_PLATE_DETECTED
        self.assertIsNone(plate)
        self.assertEqual(status, "NO_PLATE_DETECTED")

    @patch("src.integrations.anpr.requests.post")
    def test_send_frame_argus_all_empty_plates(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "filename": "multi_unreadable.jpg",
            "results": [
                {"plate": None, "vehicle_type": "truck"},
                {"plate": "", "vehicle_type": "car"},
                {"plate": "N/A", "vehicle_type": "bike"},
            ],
            "execution_time_ms": 1200.0,
        }
        mock_post.return_value = mock_response

        plate, status = send_frame_to_anpr_server(b"fake-bytes")
        self.assertIsNone(plate)
        self.assertEqual(status, "NO_PLATE_DETECTED")

    def test_highest_frequency_voting(self):
        samples = ["MH12AB1234", "MH12AB1234", "MH12AB1234", "MH12AB1235", "DL01AB9999"]
        winner = get_highest_frequency_plate(samples)
        self.assertEqual(winner, "MH12AB1234")

    def test_highest_frequency_empty_list(self):
        winner = get_highest_frequency_plate([])
        self.assertEqual(winner, "NO_PLATE_DETECTED")

        winner_none = get_highest_frequency_plate([None, "", "   "])
        self.assertEqual(winner_none, "NO_PLATE_DETECTED")


if __name__ == "__main__":
    unittest.main()
