import threading
import time
import unittest
from unittest.mock import patch

from src.config import ConfigManager
from src.core.session import SessionPhase, WeighbridgeSessionManager
from src.core.stability import ScaleStabilityMachine


class TestThreadingIsolation(unittest.TestCase):
    def test_trigger_upload_is_non_blocking(self):
        from src.core.db import get_spool_stats, init_db, reset_db

        init_db()
        reset_db()
        machine = ScaleStabilityMachine()
        package = {"session_id": "TEST_SESSION_ASYNC", "weight": 25000.0, "anpr_plate": "MH12AB1234"}

        start_time = time.time()
        session_id = machine._trigger_upload(package)
        elapsed = time.time() - start_time

        # Trigger should return instantaneously (< 0.05s) to never stall scale UART
        self.assertLess(elapsed, 0.05)
        self.assertEqual(session_id, "TEST_SESSION_ASYNC")

        stats = get_spool_stats()
        self.assertEqual(stats["pending"], 1)
        reset_db()


    @patch("src.core.session.capture_all_camera_snapshots")
    def test_on_weight_stabilized_is_non_blocking(self, mock_capture):
        sm = WeighbridgeSessionManager()
        aux_captured_event = threading.Event()

        def slow_fleet_capture():
            time.sleep(0.2)
            aux_captured_event.set()
            return {"aux_1": b"FAKE_CAM2_JPEG"}

        mock_capture.side_effect = slow_fleet_capture

        sm.start_session()
        self.assertEqual(sm.phase, SessionPhase.PHASE_STABILIZING)

        start_time = time.time()
        sm.on_weight_stabilized(30000.0)

        elapsed = time.time() - start_time
        # on_weight_stabilized should return instantaneously (< 0.1s) without waiting 0.2s
        self.assertLess(elapsed, 0.1)
        self.assertIsNotNone(sm._fleet_snapshot_thread)
        assert sm._fleet_snapshot_thread is not None
        self.assertTrue(sm._fleet_snapshot_thread.name.startswith("FleetCapture_"))

        # Fast forward time to test finalization
        sm._post_stability_start_time = 0.0
        pkg = sm.check_session_progress()
        self.assertIsNotNone(pkg)
        assert pkg is not None
        self.assertIn("aux_1", pkg["camera_snapshots"])
        self.assertEqual(pkg["camera_snapshots"]["aux_1"], b"FAKE_CAM2_JPEG")
        sm.reset_session()

    def test_config_manager_concurrent_access(self):
        import json
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_db_file = os.path.join(temp_dir, "test_hermes.db")
            cm = ConfigManager(db_path=temp_db_file)
            errors: list[OSError | json.JSONDecodeError | ValueError | KeyError | RuntimeError] = []

            def writer_task(idx: int):
                try:
                    for i in range(10):
                        cm.update_system_config(
                            serial_port=f"/dev/ttyUSB{idx}",
                            serial_baudrate=1200 + (idx * 100),
                        )
                        cm.update_wifi_credentials(f"SSID_{idx}_{i}", f"PASS_{idx}_{i}")
                except (OSError, json.JSONDecodeError, ValueError, KeyError, RuntimeError) as e:
                    errors.append(e)

            def reader_task():
                try:
                    for _ in range(20):
                        _ = cm.weight_threshold
                        _ = cm.serial_baudrate
                        _ = cm.auxiliary_camera_urls
                        _ = cm._build_data_dict()
                        time.sleep(0.001)
                except (OSError, json.JSONDecodeError, ValueError, KeyError, RuntimeError) as e:
                    errors.append(e)

            threads = [
                threading.Thread(target=writer_task, args=(1,)),
                threading.Thread(target=writer_task, args=(2,)),
                threading.Thread(target=reader_task),
                threading.Thread(target=reader_task),
            ]

            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=3.0)

            self.assertEqual(len(errors), 0)


if __name__ == "__main__":
    unittest.main()
