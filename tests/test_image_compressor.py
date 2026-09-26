import unittest

import cv2
import numpy as np

from src.config.constants import POST_STABILITY_DURATION
from src.core.session import WeighbridgeSessionManager
from src.core.stability import ScaleStabilityMachine, ScaleState
from src.services.image_compressor import compress_image_bytes


class TestImageCompressor(unittest.TestCase):
    def test_compress_none_or_empty(self):
        self.assertIsNone(compress_image_bytes(None))
        self.assertIsNone(compress_image_bytes(b""))

    def test_compress_corrupt_bytes_returns_original(self):
        corrupt = b"not_an_image_stream"
        res = compress_image_bytes(corrupt)
        self.assertEqual(res, corrupt)

    def test_compress_4k_image_downscaled_to_1920(self):
        # Create a synthetic 4K image (3840 x 2160)
        img_4k = np.zeros((2160, 3840, 3), dtype=np.uint8)
        # Draw some features
        cv2.putText(img_4k, "RJ45CX3690", (500, 1000), cv2.FONT_HERSHEY_SIMPLEX, 5, (255, 255, 255), 10)
        ok, raw_jpeg = cv2.imencode(".jpg", img_4k, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
        self.assertTrue(ok)
        raw_bytes = raw_jpeg.tobytes()

        compressed = compress_image_bytes(raw_bytes, max_dim=1920, quality=85)
        self.assertIsNotNone(compressed)
        assert compressed is not None

        # Verify decoded compressed image has max dimension <= 1920
        dec = cv2.imdecode(np.frombuffer(compressed, np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(dec)
        assert dec is not None
        h, w = dec.shape[:2]
        self.assertLessEqual(max(h, w), 1920)
        self.assertLess(len(compressed), len(raw_bytes))

    def test_compress_1080p_image_dimensions_preserved(self):
        # Create a 1920x1080 image
        img_1080 = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cv2.putText(img_1080, "PLATE", (200, 500), cv2.FONT_HERSHEY_SIMPLEX, 3, (255, 255, 255), 5)
        ok, raw_jpeg = cv2.imencode(".jpg", img_1080, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
        self.assertTrue(ok)
        raw_bytes = raw_jpeg.tobytes()

        compressed = compress_image_bytes(raw_bytes, max_dim=1920, quality=85)
        self.assertIsNotNone(compressed)
        assert compressed is not None

        dec = cv2.imdecode(np.frombuffer(compressed, np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(dec)
        assert dec is not None
        h, w = dec.shape[:2]
        self.assertEqual(w, 1920)
        self.assertEqual(h, 1080)


class TestMidStabilityAndShortPostStability(unittest.TestCase):
    def setUp(self):
        self.sm = WeighbridgeSessionManager()
        self.machine = ScaleStabilityMachine()

    def tearDown(self):
        self.sm.reset_session()
        self.machine.reset()

    def test_post_stability_duration_is_5_seconds(self):
        self.assertEqual(POST_STABILITY_DURATION, 5.0)

    def test_mid_stability_triggers_at_half_duration(self):
        self.machine.state = ScaleState.SCALE_STABILIZING
        self.machine._current_stable_candidate = 25000.0
        self.machine._candidate_start_time = 1000.0
        self.machine._mid_stability_triggered = False

        # At t = 1004.0 (elapsed = 4.0s < 5.0s halfway): should not trigger
        self.machine._evaluate_stability_window(25000.5, 1004.0)
        self.assertFalse(self.machine._mid_stability_triggered)
        self.assertEqual(self.machine.state, ScaleState.SCALE_STABILIZING)

        # At t = 1005.1 (elapsed = 5.1s >= 5.0s halfway): should trigger
        self.machine._evaluate_stability_window(25000.5, 1005.1)
        self.assertTrue(self.machine._mid_stability_triggered)
        self.assertEqual(self.machine.state, ScaleState.SCALE_STABILIZING)

        # At t = 1010.1 (elapsed = 10.1s >= 10.0s stability confirmed): stable recorded
        self.machine._evaluate_stability_window(25000.5, 1010.1)
        self.assertEqual(self.machine.state, ScaleState.SCALE_STABLE_RECORDED)

    def test_weight_shift_resets_mid_stability_trigger(self):
        self.machine.state = ScaleState.SCALE_STABILIZING
        self.machine._current_stable_candidate = 25000.0
        self.machine._candidate_start_time = 1000.0
        self.machine._mid_stability_triggered = True

        # Weight shifts by 50 kg (> 2.0 kg tolerance)
        self.machine._evaluate_stability_window(25050.0, 1007.0)
        self.assertFalse(self.machine._mid_stability_triggered)
        self.assertEqual(self.machine._current_stable_candidate, 25050.0)
