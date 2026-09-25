"""license.py — Ed25519 offline license verification and loading."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

logger = logging.getLogger(__name__)

DEFAULT_PUB_KEY = "8ea1608704d2351f0a9c3be6189c2f6f66760bd68878a5d0c980d5c82c2ec053"


def sign_license(payload: dict[str, Any], priv_key_hex: str) -> str:
    """Signs payload using Ed25519 private key and returns JSON license."""
    priv = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_key_hex))
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    sig = priv.sign(raw)
    return json.dumps({"payload": payload, "signature": sig.hex()}, indent=2)


def verify_license(data_str: str, pub_key_hex: str = DEFAULT_PUB_KEY) -> dict[str, Any]:
    """Verifies Ed25519 signature of license JSON and returns valid payload."""
    data = json.loads(data_str)
    payload = data.get("payload", {})
    sig = bytes.fromhex(data.get("signature", ""))
    pub = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_key_hex))
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    pub.verify(sig, raw)
    return payload


def load_client_license(path: str = "data/client.lic") -> dict[str, Any] | None:
    """Loads and verifies client license file if present on disk."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return verify_license(content)
    except (InvalidSignature, ValueError, KeyError) as e:
        logger.error(f"[License] Invalid or tampered license file '{path}': {e}")
        return None
