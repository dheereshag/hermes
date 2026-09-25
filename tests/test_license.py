"""test_license.py — Unit tests for Ed25519 offline license verification."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature

from scripts.keygen import DEFAULT_PRIV_KEY
from src.config.license import (
    DEFAULT_PUB_KEY,
    load_client_license,
    sign_license,
    verify_license,
)
from src.config.manager import ConfigManager


@pytest.fixture
def sample_payload() -> dict[str, object]:
    return {
        "device_id": "test_pi_99",
        "device_key": "secret_key_123",
        "center_id": 42,
        "min_weight": 85.5,
        "anpr_server_url": "http://192.168.1.100:8000/recognize",
    }


def test_license_signing_and_verification(sample_payload: dict[str, object]) -> None:
    signed_json = sign_license(sample_payload, DEFAULT_PRIV_KEY)
    verified = verify_license(signed_json, DEFAULT_PUB_KEY)
    assert verified == sample_payload


def test_tampered_payload_rejected(sample_payload: dict[str, object]) -> None:
    signed_json = sign_license(sample_payload, DEFAULT_PRIV_KEY)
    tampered_data = json.loads(signed_json)
    tampered_data["payload"]["center_id"] = 999  # Tamper with collection center ID
    with pytest.raises(InvalidSignature):
        verify_license(json.dumps(tampered_data), DEFAULT_PUB_KEY)


def test_invalid_signature_rejected(sample_payload: dict[str, object]) -> None:
    signed_json = sign_license(sample_payload, DEFAULT_PRIV_KEY)
    data = json.loads(signed_json)
    data["signature"] = "00" * 64  # Bogus 64-byte signature
    with pytest.raises(InvalidSignature):
        verify_license(json.dumps(data), DEFAULT_PUB_KEY)


def test_load_client_license_missing_file() -> None:
    assert load_client_license("/nonexistent/path/client.lic") is None


def test_config_manager_with_license(tmp_path: Path, sample_payload: dict[str, object]) -> None:
    lic_file = tmp_path / "client.lic"
    lic_file.write_text(sign_license(sample_payload, DEFAULT_PRIV_KEY), encoding="utf-8")
    db_file = tmp_path / "test.db"

    mgr = ConfigManager(db_path=str(db_file), lic_path=str(lic_file))
    assert mgr.center_id == 42
    assert mgr.device_id == "test_pi_99"
    assert mgr.device_key == "secret_key_123"
    assert mgr.weight_threshold == 85.5
    assert mgr.anpr_server_url == "http://192.168.1.100:8000/recognize"


def test_config_manager_fallback_without_license(tmp_path: Path) -> None:
    db_file = tmp_path / "test_fallback.db"
    mgr = ConfigManager(db_path=str(db_file), lic_path="/nonexistent/client.lic")
    assert mgr.center_id == 5
    assert mgr.device_id == "pi1"
    assert mgr.device_key == "hardware123"
