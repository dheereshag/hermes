"""manager.py — Thread-safe configuration manager."""
from __future__ import annotations

from typing import Any

from src.config import client_config as cc
from src.config.license import load_client_license
from src.config.runtime import RuntimeConfig


class ConfigManager:
    def __init__(self, db_path: str | None = None, lic_path: str = "data/client.lic") -> None:
        self.runtime = RuntimeConfig(db_path)
        self.license = load_client_license(lic_path) or {}

    def load_settings(self) -> None:
        self.runtime.reload()

    @property
    def center_id(self) -> int:
        return int(self.license.get("center_id", cc.CENTER_ID))

    @property
    def weight_threshold(self) -> float:
        return float(self.license.get("min_weight", cc.MIN_WEIGHT))

    min_weight = weight_threshold

    @property
    def device_id(self) -> str | int:
        return self.license.get("device_id", cc.DEVICE_ID)

    @property
    def device_key(self) -> str:
        return str(self.license.get("device_key", cc.DEVICE_KEY))

    @property
    def anpr_server_url(self) -> str:
        return str(self.license.get("anpr_server_url", cc.ANPR_SERVER_URL))

    @property
    def wifi_ssid(self) -> str: return str(self.runtime.get("wifi_ssid", cc.WIFI_SSID))
    @property
    def wifi_password(self) -> str: return str(self.runtime.get("wifi_password", cc.WIFI_PASSWORD))
    @property
    def serial_port(self) -> str: return str(self.runtime.get("serial_port", cc.SERIAL_PORT))
    @property
    def serial_baudrate(self) -> int: return int(self.runtime.get("serial_baudrate", cc.SERIAL_BAUDRATE))
    @property
    def anpr_camera_urls(self) -> list[str]: return list(self.runtime.get("anpr_camera_urls", cc.ANPR_CAMERA_URLS))
    @property
    def anpr_camera_url(self) -> str: return self.anpr_camera_urls[0] if self.anpr_camera_urls else ""
    @property
    def auxiliary_camera_urls(self) -> list[str]: return list(self.runtime.get("auxiliary_camera_urls", cc.AUXILIARY_CAMERA_URLS))

    def update_system_config(self, **kwargs: Any) -> None: self.runtime.update_system(**kwargs)
    def update_wifi_credentials(self, s: str, p: str) -> None: self.runtime.update_wifi(s, p)
    def clear_wifi_credentials(self) -> None: self.runtime.clear_wifi()

    def _build_data_dict(self) -> dict[str, Any]:
        return {
            "center_id": self.center_id, "min_weight": self.weight_threshold,
            "device_id": self.device_id, "device_key": self.device_key,
            "anpr_server_url": self.anpr_server_url, "serial_port": self.serial_port,
            "serial_baudrate": self.serial_baudrate, "wifi_ssid": self.wifi_ssid,
            "wifi_password": self.wifi_password, "anpr_camera_urls": self.anpr_camera_urls,
            "auxiliary_camera_urls": self.auxiliary_camera_urls,
        }
