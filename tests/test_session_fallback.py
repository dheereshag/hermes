import unittest
from unittest.mock import patch

from src.core.session import SessionPhase, WeighbridgeSessionManager


class TestSessionErrorFallback(unittest.TestCase):
    def setUp(self):
        self.sm = WeighbridgeSessionManager()

    def tearDown(self):
        self.sm.reset_session()

    @patch("src.core.session.send_frame_to_anpr_server")
    @patch("src.core.session.fetch_image_bytes")
    def test_session_recognition_failure_sends_no_plate_detected_and_includes_image(self, mock_fetch, mock_send):
        fake_truck_frame = b"\xff\xd8\xff\xe0\x00\x10JFIF_TRUCK_FRAME"
        mock_fetch.return_value = fake_truck_frame
        mock_send.return_value = (None, "NO_PLATE_DETECTED")

        self.sm.start_session()
        self.assertEqual(self.sm.phase, SessionPhase.PHASE_STABILIZING)

        # Simulate 2 ANPR frames captured with no plate detected
        self.sm._anpr_frame_buffers.setdefault(1, []).append(fake_truck_frame)
        self.sm._anpr_statuses.append("NO_PLATE_DETECTED")

        # Weight stabilized
        self.sm.on_weight_stabilized(36500.0)
        self.sm._post_stability_start_time = 0.0  # Force timeout expired

        pkg = self.sm.check_session_progress()
        self.assertIsNotNone(pkg)
        assert pkg is not None

        # 1. Verify NO_PLATE_DETECTED is assigned as the plate string
        self.assertEqual(pkg["anpr_plate"], "NO_PLATE_DETECTED")
        self.assertEqual(pkg["weight"], 36500.0)

        # 2. Verify the truck image is still present in the final package
        self.assertEqual(pkg["camera_snapshots"]["anpr_1"], fake_truck_frame)

    @patch("src.core.session.send_frame_to_anpr_server")
    @patch("src.core.session.fetch_image_bytes")
    def test_session_prefers_valid_plate_over_transient_errors(self, mock_fetch, mock_send):
        fake_truck_frame = b"\xff\xd8\xff\xe0\x00\x10JFIF_TRUCK_FRAME"
        mock_fetch.return_value = fake_truck_frame

        self.sm.start_session()

        # Simulate 1 transient error frame and 2 valid plate frames
        self.sm._anpr_frame_buffers.setdefault(1, []).append(fake_truck_frame)
        self.sm._anpr_statuses.append("NO_PLATE_DETECTED")

        self.sm._anpr_plates.append("RJ09GA0165")
        self.sm._anpr_statuses.append("SUCCESS")

        self.sm._anpr_plates.append("RJ09GA0165")
        self.sm._anpr_statuses.append("SUCCESS")

        self.sm.on_weight_stabilized(42000.0)
        self.sm._post_stability_start_time = 0.0

        pkg = self.sm.check_session_progress()
        self.assertIsNotNone(pkg)
        assert pkg is not None

        # Plate winner should be the valid plate
        self.assertEqual(pkg["anpr_plate"], "RJ09GA0165")
        self.assertEqual(pkg["camera_snapshots"]["anpr_1"], fake_truck_frame)

    @patch("src.core.session.send_frame_to_anpr_server")
    @patch("src.core.session.capture_anpr_snapshots")
    def test_multi_anpr_camera_ocr_consensus(self, mock_anpr_snaps, mock_send):
        frame_front = b"front_plate_frame"
        frame_rear = b"rear_plate_frame"
        mock_anpr_snaps.return_value = [
            (1, "http://anpr1/front", frame_front),
            (2, "http://anpr2/rear", frame_rear),
        ]
        # Front was noisy; Rear clearly detected plate
        mock_send.side_effect = (
            lambda img: ("HR26DK8333", "SUCCESS") if img == frame_rear else (None, "NO_PLATE_DETECTED")
        )

        self.sm.start_session()
        self.sm._capture_and_record_anpr_sample()

        self.assertEqual(len(self.sm._anpr_plates), 1)
        self.assertEqual(self.sm._anpr_plates[0], "HR26DK8333")

        self.sm.on_weight_stabilized(50100.0)
        self.sm._post_stability_start_time = 0.0

        pkg = self.sm.check_session_progress()
        self.assertIsNotNone(pkg)
        assert pkg is not None
        self.assertEqual(pkg["anpr_plate"], "HR26DK8333")

    @patch("src.core.session.capture_all_camera_snapshots")
    def test_full_fleet_snapshots_on_stabilization(self, mock_fleet_snaps):
        mock_fleet_snaps.return_value = {
            "anpr_1": b"front_jpeg",
            "anpr_2": b"rear_jpeg",
            "aux_1": b"cabin_jpeg",
            "aux_2": b"bed_jpeg",
        }
        self.sm.start_session()
        self.sm._anpr_plates.append("MH04AB9999")
        self.sm.on_weight_stabilized(28400.0)
        self.sm._post_stability_start_time = 0.0

        pkg = self.sm.check_session_progress()
        self.assertIsNotNone(pkg)
        assert pkg is not None
        self.assertEqual(pkg["anpr_plate"], "MH04AB9999")
        self.assertIn("camera_snapshots", pkg)
        self.assertEqual(len(pkg["camera_snapshots"]), 4)
        self.assertEqual(pkg["camera_snapshots"]["anpr_1"], b"front_jpeg")
        self.assertEqual(pkg["camera_snapshots"]["anpr_2"], b"rear_jpeg")
        self.assertEqual(pkg["camera_snapshots"]["aux_1"], b"cabin_jpeg")
        self.assertEqual(pkg["camera_snapshots"]["aux_2"], b"bed_jpeg")

    @patch("src.core.session.send_frame_to_anpr_server")
    @patch("src.core.session.capture_anpr_snapshots")
    def test_session_empty_results_from_argus_sends_no_plate_detected(self, mock_anpr_snaps, mock_send):
        fake_frame = b"fake_frame_bytes"
        mock_anpr_snaps.return_value = [(1, "http://anpr1/front", fake_frame)]
        mock_send.return_value = (None, "NO_PLATE_DETECTED")

        self.sm.start_session()
        self.sm._capture_and_record_anpr_sample()

        self.assertEqual(len(self.sm._anpr_plates), 0)
        self.assertEqual(self.sm._anpr_statuses, ["NO_PLATE_DETECTED"])

        self.sm.on_weight_stabilized(42000.0)
        self.sm._post_stability_start_time = 0.0

        pkg = self.sm.check_session_progress()
        self.assertIsNotNone(pkg)
        assert pkg is not None
        self.assertEqual(pkg["anpr_plate"], "NO_PLATE_DETECTED")


if __name__ == "__main__":
    unittest.main()
