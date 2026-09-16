from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

from src.config.constants import (
    DEFAULT_SERIAL_BAUDRATE,
    DEFAULT_SERIAL_PORT,
    DEFAULT_WEIGHT_THRESHOLD,
)

logger = logging.getLogger(__name__)

CONFIG_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config.json"
)


class ConfigManager:
    def __init__(self, file_path: str = CONFIG_FILE_PATH):
        self._lock = threading.RLock()
        self.file_path = file_path
        self.wifi_ssid = ""
        self.wifi_password = ""
        self.center_id = 1
        self.weight_threshold = DEFAULT_WEIGHT_THRESHOLD
        self.device_id = 1
        self.device_key = ""
        self.anpr_server_url = ""
        self.serial_port = DEFAULT_SERIAL_PORT
        self.serial_baudrate = DEFAULT_SERIAL_BAUDRATE
        self.anpr_camera_url = "http://192.168.1.101/cgi-bin/snapshot.cgi"
        self.auxiliary_camera_urls: list[str] = [
            "http://192.168.1.102/cgi-bin/snapshot.cgi",
            "http://192.168.1.103/cgi-bin/snapshot.cgi",
            "http://192.168.1.104/cgi-bin/snapshot.cgi",
        ]
        self.load_settings()

    def load_settings(self) -> None:
        with self._lock:
            if not os.path.exists(self.file_path):
                logger.info(f"[Config] Config file '{self.file_path}' not found. Initializing with defaults.")
                self.save_settings(
                    ssid="",
                    password="",
                    center_id=1,
                    min_weight=50.0,
                    device_id=1,
                    device_key="",
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
                self.device_id = int(data.get("device_id", 1))
                self.device_key = str(data.get("device_key", ""))
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
                logger.info(f" -> Device ID: {self.device_id}")
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
            "device_id": self.device_id,
            "device_key": self.device_key,
            "anpr_server_url": self.anpr_server_url,
            "serial_port": self.serial_port,
            "serial_baudrate": self.serial_baudrate,
            "anpr_camera_url": self.anpr_camera_url,
            "auxiliary_camera_urls": list(self.auxiliary_camera_urls),
        }

    def _persist(self) -> None:
        """Write current state to config.json."""
        with self._lock:
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
        device_id: int = 1,
        device_key: str = "",
        anpr_url: str | None = None,
    ) -> None:
        with self._lock:
            self.wifi_ssid = ssid
            self.wifi_password = password
            self.center_id = int(center_id)
            self.weight_threshold = float(min_weight)
            self.device_id = int(device_id)
            self.device_key = str(device_key)
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
        with self._lock:
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

    def update_device_credentials(self, device_id: int, device_key: str) -> None:
        with self._lock:
            self.device_id = int(device_id)
            self.device_key = str(device_key)
            self._persist()
            logger.info(f"[Config] Device credentials updated for Device ID: {self.device_id}.")

    def update_wifi_credentials(self, ssid: str, password: str) -> None:
        with self._lock:
            self.wifi_ssid = ssid
            self.wifi_password = password
            self._persist()
            logger.info(f"[Config] Wi-Fi credentials updated for SSID: '{self.wifi_ssid}'.")

    def clear_wifi_credentials(self) -> None:
        with self._lock:
            self.wifi_ssid = ""
            self.wifi_password = ""
            self._persist()
            logger.info("[Config] Wi-Fi credentials cleared.")


# Shared singleton instance
config = ConfigManager()
