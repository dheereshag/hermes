from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

CONFIG_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config.json"
)


class ConfigManager:
    def __init__(self, file_path: str = CONFIG_FILE_PATH):
        self.file_path = file_path
        self.wifi_ssid = ""
        self.wifi_password = ""
        self.center_id = 1
        self.weight_threshold = 50.0
        self.api_email = ""
        self.api_password = ""
        self.profile_id = -1
        self.anpr_server_url = ""
        self.serial_port = "/dev/ttyAMA0"
        self.serial_baudrate = 1200
        self.anpr_camera_url = "http://192.168.1.101/cgi-bin/snapshot.cgi"
        self.auxiliary_camera_urls: list[str] = [
            "http://192.168.1.102/cgi-bin/snapshot.cgi",
            "http://192.168.1.103/cgi-bin/snapshot.cgi",
            "http://192.168.1.104/cgi-bin/snapshot.cgi",
        ]
        self.load_settings()

    def load_settings(self) -> None:
        if not os.path.exists(self.file_path):
            logger.info(f"[Config] Config file '{self.file_path}' not found. Initializing with defaults.")
            self.save_settings(
                ssid="",
                password="",
                center_id=1,
                min_weight=50.0,
                api_email="",
                api_password="",
                anpr_url="",
            )
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)

            self.wifi_ssid = data.get("ssid", "")
            self.wifi_password = data.get("password", "")
            self.center_id = int(data.get("center_id", 1))
            self.weight_threshold = float(data.get("min_weight", 50.0))
            self.api_email = data.get("api_email") or data.get("sb_email", "")
            self.api_password = data.get("api_password") or data.get("sb_pass", "")
            self.profile_id = int(data.get("profile_id", -1))
            self.anpr_server_url = data.get("anpr_server_url", "")
            self.serial_port = data.get("serial_port", "/dev/ttyAMA0")
            self.serial_baudrate = int(data.get("serial_baudrate", 1200))
            self.anpr_camera_url = data.get(
                "anpr_camera_url", "http://192.168.1.101/cgi-bin/snapshot.cgi"
            )
            self.auxiliary_camera_urls = data.get("auxiliary_camera_urls", [
                "http://192.168.1.102/cgi-bin/snapshot.cgi",
                "http://192.168.1.103/cgi-bin/snapshot.cgi",
                "http://192.168.1.104/cgi-bin/snapshot.cgi",
            ])

            logger.info("Configurations loaded from JSON storage:")
            logger.info(f" -> SSID: {self.wifi_ssid}")
            logger.info(f" -> Operator Email: {self.api_email}")
            logger.info(f" -> Center ID: {self.center_id}")
            logger.info(f" -> Min Weight Threshold: {self.weight_threshold:.1f}")
            logger.info(f" -> Serial Port: {self.serial_port} @ {self.serial_baudrate} baud")
            logger.info(f" -> ANPR Camera: {self.anpr_camera_url}")
            logger.info(f" -> Auxiliary Cameras: {len(self.auxiliary_camera_urls)} configured")
            if self.anpr_server_url:
                logger.info(f" -> ANPR Server URL Override: {self.anpr_server_url}")
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"[Config] Error loading settings: {e}")

    def _build_data_dict(self) -> dict[str, Any]:
        """Build the complete config data dictionary for persistence."""
        return {
            "ssid": self.wifi_ssid,
            "password": self.wifi_password,
            "center_id": self.center_id,
            "min_weight": self.weight_threshold,
            "api_email": self.api_email,
            "api_password": self.api_password,
            "profile_id": self.profile_id,
            "anpr_server_url": self.anpr_server_url,
            "serial_port": self.serial_port,
            "serial_baudrate": self.serial_baudrate,
            "anpr_camera_url": self.anpr_camera_url,
            "auxiliary_camera_urls": self.auxiliary_camera_urls,
        }

    def _persist(self) -> None:
        """Write current state to config.json."""
        data = self._build_data_dict()
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info("[Config] New configurations written to persistent JSON storage.")
        except (OSError, TypeError, ValueError) as e:
            logger.error(f"[Config] Failed to save settings: {e}")

    def save_settings(
        self,
        ssid: str,
        password: str,
        center_id: int,
        min_weight: float,
        api_email: str,
        api_password: str,
        anpr_url: str | None = None,
    ) -> None:
        self.wifi_ssid = ssid
        self.wifi_password = password
        self.center_id = int(center_id)
        self.weight_threshold = float(min_weight)
        self.api_email = api_email
        self.api_password = api_password
        if anpr_url is not None:
            self.anpr_server_url = anpr_url
        self._persist()

    def update_system_config(
        self,
        min_weight: float | None = None,
        serial_port: str | None = None,
        serial_baudrate: int | None = None,
        anpr_camera_url: str | None = None,
        auxiliary_camera_urls: list[str] | None = None,
        anpr_server_url: str | None = None,
    ) -> None:
        """Update system configuration fields and persist to config.json."""
        if min_weight is not None:
            self.weight_threshold = float(min_weight)
        if serial_port is not None:
            self.serial_port = str(serial_port).strip()
        if serial_baudrate is not None:
            self.serial_baudrate = int(serial_baudrate)
        if anpr_camera_url is not None:
            self.anpr_camera_url = str(anpr_camera_url).strip()
        if auxiliary_camera_urls is not None:
            self.auxiliary_camera_urls = [str(u).strip() for u in auxiliary_camera_urls if str(u).strip()]
        if anpr_server_url is not None:
            self.anpr_server_url = str(anpr_server_url).strip()
        self._persist()
        logger.info("[Config] System configuration updated via web interface.")

    def update_profile_id(self, profile_id: int) -> None:
        self.profile_id = profile_id
        self._persist()

    def update_wifi_credentials(self, ssid: str, password: str) -> None:
        self.wifi_ssid = ssid
        self.wifi_password = password
        self._persist()
        logger.info(f"[Config] Wi-Fi credentials updated for SSID: '{self.wifi_ssid}'.")

    def clear_wifi_credentials(self) -> None:
        self.wifi_ssid = ""
        self.wifi_password = ""
        self._persist()
        logger.info("[Config] Wi-Fi credentials cleared.")


# Shared singleton instance
config = ConfigManager()
