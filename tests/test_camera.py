import unittest
from unittest.mock import patch

from src.devices.camera import capture_all_camera_snapshots


class TestCameraDriver(unittest.TestCase):
    @patch("src.devices.camera.fetch_image_bytes")
    def test_capture_all_camera_snapshots_success(self, mock_fetch):
        def fake_fetch(url: str, timeout: float = 3.0) -> bytes | None:
            if "front" in url:
                return b"front_jpeg"
            if "rear" in url:
                return b"rear_jpeg"
            if "cabin" in url:
                return b"cabin_jpeg"
            return b"generic_jpeg"

        mock_fetch.side_effect = fake_fetch
        anpr_urls = ["http://127.0.0.1:8001/front", "http://127.0.0.1:8001/rear"]
        aux_urls = ["http://127.0.0.1:8001/cabin"]

        res = capture_all_camera_snapshots(anpr_urls, aux_urls)
        self.assertEqual(len(res), 3)
        self.assertEqual(res["anpr_1"], b"front_jpeg")
        self.assertEqual(res["anpr_2"], b"rear_jpeg")
        self.assertEqual(res["aux_1"], b"cabin_jpeg")

    def test_capture_all_camera_snapshots_empty(self):
        res = capture_all_camera_snapshots([], [])
        self.assertEqual(res, {})

    @patch("src.devices.camera.fetch_image_bytes")
    def test_capture_all_camera_snapshots_partial_failure(self, mock_fetch):
        mock_fetch.side_effect = lambda url, timeout=3.0: b"front" if "front" in url else None
        res = capture_all_camera_snapshots(["http://cam/front"], ["http://cam/aux_broken"])
        self.assertEqual(res["anpr_1"], b"front")
        self.assertIsNone(res["aux_1"])


if __name__ == "__main__":
    unittest.main()
