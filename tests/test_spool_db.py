from __future__ import annotations

import os
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from src.config.config_manager import config
from src.core.db import (
    acquire_next_spool_task,
    get_spool_images,
    get_spool_stats,
    init_db,
    mark_spool_acknowledged,
    mark_spool_retry,
    recover_stranded_leases,
    reset_db,
    spool_weighment,
)
from src.core.spool import SpoolWorker
from src.core.telemetry import reset_telemetry
from src.integrations.gluvok import (
    transmit_entry_multipart,
    verify_entry_in_cloud,
)


class TestSpoolDB(unittest.TestCase):
    def setUp(self):
        reset_telemetry()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_hermes.db")
        init_db(self.db_path)
        reset_db()

        self.orig_device_id = config.device_id
        self.orig_device_key = config.device_key
        self.orig_center_id = config.center_id
        config.device_id = "pi1"
        config.device_key = "hardware123"
        config.center_id = 1

    def tearDown(self):
        config.device_id = self.orig_device_id
        config.device_key = self.orig_device_key
        config.center_id = self.orig_center_id
        reset_db()
        self.temp_dir.cleanup()
        reset_telemetry()

    def test_spool_weighment_and_images(self):
        pkg = {
            "session_id": "SESS_TEST_001",
            "weight": 18540.5,
            "anpr_plate": "MH12AB1234",
            "cam1_final_image": b"fake_cam1_data",
            "auxiliary_images": {1: b"fake_aux1_data", 2: b"fake_aux2_data"},
        }
        session_id = spool_weighment(pkg)
        self.assertEqual(session_id, "SESS_TEST_001")

        images = get_spool_images(session_id)
        self.assertEqual(len(images), 3)
        self.assertEqual(images[0][0], "cam1")
        self.assertEqual(images[0][2], b"fake_cam1_data")

        stats = get_spool_stats()
        self.assertEqual(stats["pending"], 1)
        self.assertEqual(stats["uploading"], 0)
        self.assertEqual(stats["acknowledged"], 0)

    def test_duplicate_spool_prevented(self):
        pkg = {
            "session_id": "SESS_DUPLICATE_001",
            "weight": 25000.0,
            "anpr_plate": "DL1CAB1234",
            "cam1_final_image": b"data",
        }
        spool_weighment(pkg)
        # Second insert with identical session_id should be ignored
        spool_weighment(pkg)

        stats = get_spool_stats()
        self.assertEqual(stats["total"], 1)

    def test_acquire_task_lease_locking(self):
        pkg = {
            "session_id": "SESS_LEASE_001",
            "weight": 12000.0,
            "anpr_plate": "KA01AB1111",
            "cam1_final_image": b"img",
        }
        spool_weighment(pkg)

        # Worker 1 acquires lease
        task1 = acquire_next_spool_task(lease_seconds=30.0)
        self.assertIsNotNone(task1)
        assert task1 is not None
        self.assertEqual(task1["session_id"], "SESS_LEASE_001")

        # Worker 2 attempts to acquire at the same time: should return None due to active lease
        task2 = acquire_next_spool_task(lease_seconds=30.0)
        self.assertIsNone(task2)

        stats = get_spool_stats()
        self.assertEqual(stats["uploading"], 1)
        self.assertEqual(stats["pending"], 0)

    def test_mark_acknowledged(self):
        pkg = {"session_id": "SESS_ACK_001", "weight": 5000.0, "anpr_plate": "MH01AA0001"}
        spool_weighment(pkg)
        acquire_next_spool_task(lease_seconds=10.0)

        mark_spool_acknowledged("SESS_ACK_001", cloud_entry_id="CLOUD_999")

        stats = get_spool_stats()
        self.assertEqual(stats["acknowledged"], 1)
        self.assertEqual(stats["uploading"], 0)

    def test_mark_retry_with_backoff(self):
        pkg = {"session_id": "SESS_RETRY_001", "weight": 7000.0, "anpr_plate": "MH01AA0002"}
        spool_weighment(pkg)
        acquire_next_spool_task(lease_seconds=10.0)

        mark_spool_retry("SESS_RETRY_001", "Connection timed out")

        stats = get_spool_stats()
        self.assertEqual(stats["retry"], 1)
        self.assertEqual(stats["uploading"], 0)

    def test_recover_stranded_leases(self):
        pkg = {"session_id": "SESS_STRANDED_001", "weight": 8000.0, "anpr_plate": "MH01AA0003"}
        spool_weighment(pkg)
        # Acquire with 0-second lease so it immediately expires
        acquire_next_spool_task(lease_seconds=-1.0)

        recovered = recover_stranded_leases()
        self.assertEqual(recovered, 1)

        stats = get_spool_stats()
        self.assertEqual(stats["pending"], 1)
        self.assertEqual(stats["uploading"], 0)

    @patch("src.integrations.gluvok.requests.post")
    def test_transmit_entry_multipart_curl_format(self, mock_post: Mock):
        mock_resp = Mock(status_code=201, content=b'{"data": {"id": 105}}')
        mock_resp.json.return_value = {"data": {"id": 105}}
        mock_post.return_value = mock_resp

        success, entry_id, _err, is_timeout = transmit_entry_multipart(
            center_id=1,
            detected_vehicle_number="MH12AB1234",
            weight=18540.5,
            image_bytes=b"sample_image_data",
            filename="truck_001.jpg",
        )


        self.assertTrue(success)
        self.assertEqual(entry_id, "105")
        self.assertFalse(is_timeout)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs

        # 1. Verify HTTP Basic Auth (-u "pi1:hardware123")
        self.assertEqual(call_kwargs["auth"], ("pi1", "hardware123"))

        # 2. Verify form data fields (center_id, detected_vehicle_number, weight)
        self.assertEqual(call_kwargs["data"]["center_id"], "1")
        self.assertEqual(call_kwargs["data"]["detected_vehicle_number"], "MH12AB1234")
        self.assertEqual(call_kwargs["data"]["weight"], "18540.5")

        # 3. Verify NO session_id is sent in form data
        self.assertNotIn("session_id", call_kwargs["data"])

        # 4. Verify file attachment under 'file' key
        files = call_kwargs["files"]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0][0], "file")
        self.assertEqual(files[0][1][0], "truck_001.jpg")
        self.assertEqual(files[0][1][1], b"sample_image_data")
        self.assertEqual(files[0][1][2], "image/jpeg")

    @patch("src.integrations.gluvok.requests.post")
    def test_transmit_entry_multipart_without_image_preserves_multipart(self, mock_post: Mock):
        mock_resp = Mock(status_code=201, content=b'{"data": {"id": 106}}')
        mock_resp.json.return_value = {"data": {"id": 106}}
        mock_post.return_value = mock_resp

        success, entry_id, _err, is_timeout = transmit_entry_multipart(
            center_id=1,
            detected_vehicle_number="NO_PLATE_DETECTED",
            weight=380.0,
            image_bytes=None,
        )

        self.assertTrue(success)
        self.assertEqual(entry_id, "106")
        self.assertFalse(is_timeout)

        call_kwargs = mock_post.call_args.kwargs
        # Check that files is present so requests sets multipart/form-data
        files = call_kwargs["files"]
        self.assertIsNotNone(files)
        self.assertEqual(files[0][0], "file")
        self.assertEqual(files[0][1][1], b"")
        # Check that plate is sanitized to Indian plate format
        self.assertEqual(call_kwargs["data"]["detected_vehicle_number"], "MH00XX0000")

    @patch("src.integrations.gluvok.requests.get")
    def test_verify_entry_in_cloud_matches_tolerance(self, mock_get: Mock):
        mock_resp = Mock(status_code=200)
        mock_resp.json.return_value = {
            "data": [
                {"id": 420, "detected_vehicle_number": "MH12AB1234", "weight": 18541.0}
            ]
        }
        mock_get.return_value = mock_resp

        verified_id = verify_entry_in_cloud(
            center_id=1,
            detected_vehicle_number="MH12AB1234",
            weight=18540.5,
        )
        self.assertEqual(verified_id, "420")

    @patch("src.integrations.gluvok.requests.post")
    def test_transmit_entry_multipart_multiple_cameras(self, mock_post: Mock):
        mock_resp = Mock(status_code=201, content=b'{"data": {"id": 107}}')
        mock_resp.json.return_value = {"data": {"id": 107}}
        mock_post.return_value = mock_resp

        multi_images = [
            ("truck_cam1.jpg", b"cam1_bytes"),
            ("truck_aux_2.jpg", b"aux2_bytes"),
            ("truck_aux_3.jpg", b"aux3_bytes"),
            ("truck_anpr_2.jpg", b"anpr2_bytes"),
        ]

        success, entry_id, _err, is_timeout = transmit_entry_multipart(
            center_id=1,
            detected_vehicle_number="MH12AB1234",
            weight=18540.5,
            images=multi_images,
        )

        self.assertTrue(success)
        self.assertEqual(entry_id, "107")
        self.assertFalse(is_timeout)

        call_kwargs = mock_post.call_args.kwargs
        files = call_kwargs["files"]
        self.assertEqual(len(files), 4)
        for i, (expected_fn, expected_bytes) in enumerate(multi_images):
            self.assertEqual(files[i][0], "file")
            self.assertEqual(files[i][1][0], expected_fn)
            self.assertEqual(files[i][1][1], expected_bytes)
            self.assertEqual(files[i][1][2], "image/jpeg")

    def test_spool_worker_end_to_end(self):
        worker = SpoolWorker(poll_interval=0.1)

        pkg = {
            "session_id": "SESS_E2E_001",
            "weight": 32000.0,
            "anpr_plate": "MH14XY9999",
            "cam1_final_image": b"truck_photo",
            "auxiliary_images": {2: b"aux2_photo", "anpr_2": b"anpr2_photo"},
        }
        spool_weighment(pkg)

        with patch("src.integrations.gluvok.transmit_entry_multipart", return_value=(True, "CLOUD_100", None, False)) as mock_tx:
            worker.start()
            worker.notify_new_record()
            time.sleep(0.3)
            worker.stop()

            # Verify that transmit_entry_multipart was called with all images
            mock_tx.assert_called_once()
            called_images = mock_tx.call_args.kwargs.get("images")
            self.assertIsNotNone(called_images)
            assert isinstance(called_images, list)
            self.assertEqual(len(called_images), 3)  # cam1 + aux_2 + anpr_2

        stats = get_spool_stats()
        self.assertEqual(stats["acknowledged"], 1)
        self.assertEqual(stats["pending"], 0)


if __name__ == "__main__":
    unittest.main()
