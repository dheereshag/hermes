import os
import tempfile
import unittest

from src.core.wifi_vault import (
    clear_saved_wifi_networks,
    delete_saved_wifi_network,
    get_saved_wifi_networks,
    get_wifi_password,
    save_wifi_network,
)


class TestWifiVault(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_hermes.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_retrieve_wifi_password(self):
        save_wifi_network("Plant_5G", "SecretPass123", db_path=self.db_path)
        pwd = get_wifi_password("Plant_5G", db_path=self.db_path)
        self.assertEqual(pwd, "SecretPass123")
        self.assertIsNone(get_wifi_password("NonExistent", db_path=self.db_path))

    def test_get_saved_wifi_networks_masks_passwords(self):
        save_wifi_network("Net_A", "PassA", db_path=self.db_path)
        save_wifi_network("Net_B", "PassB", db_path=self.db_path)

        networks = get_saved_wifi_networks(db_path=self.db_path)
        self.assertEqual(len(networks), 2)
        ssids = [n["ssid"] for n in networks]
        self.assertIn("Net_A", ssids)
        self.assertIn("Net_B", ssids)
        for net in networks:
            self.assertNotIn("password", net)
            self.assertIn("created_at", net)
            self.assertIn("last_connected_at", net)

    def test_save_wifi_network_upsert_updates_password(self):
        save_wifi_network("Factory_WiFi", "OldPass", db_path=self.db_path)
        self.assertEqual(get_wifi_password("Factory_WiFi", db_path=self.db_path), "OldPass")

        save_wifi_network("Factory_WiFi", "NewPass", db_path=self.db_path)
        self.assertEqual(get_wifi_password("Factory_WiFi", db_path=self.db_path), "NewPass")

    def test_delete_and_clear_saved_wifi_networks(self):
        save_wifi_network("Temp_Net", "Pass1", db_path=self.db_path)
        save_wifi_network("Keep_Net", "Pass2", db_path=self.db_path)

        deleted = delete_saved_wifi_network("Temp_Net", db_path=self.db_path)
        self.assertTrue(deleted)
        self.assertIsNone(get_wifi_password("Temp_Net", db_path=self.db_path))
        self.assertFalse(delete_saved_wifi_network("NonExistent", db_path=self.db_path))

        clear_saved_wifi_networks(db_path=self.db_path)
        self.assertEqual(len(get_saved_wifi_networks(db_path=self.db_path)), 0)


if __name__ == "__main__":
    unittest.main()
