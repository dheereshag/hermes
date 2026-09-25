"""keygen.py — CLI tool to generate and sign bespoke client licenses with Ed25519."""
from __future__ import annotations

import argparse
import os
import sys

DEFAULT_PRIV_KEY = "c6a6d2f6f84322a333c2958a8665f59fb13a56131826905e07da38221b6ed7dd"


def generate_client_license(
    device_id: str,
    device_key: str,
    center_id: int,
    min_weight: float = 70.0,
    priv_key: str = DEFAULT_PRIV_KEY,
    output_path: str = "data/client.lic",
) -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    from src.config.license import sign_license

    payload = {
        "device_id": device_id,
        "device_key": device_key,
        "center_id": center_id,
        "min_weight": min_weight,
    }
    content = sign_license(payload, priv_key)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[Keygen] Signed license for '{device_id}' -> {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes Client License Generator")
    parser.add_argument("--device-id", required=True, help="Client device ID (e.g. pi1)")
    parser.add_argument("--device-key", required=True, help="Client pre-shared key")
    parser.add_argument("--center-id", type=int, required=True, help="Collection center ID")
    parser.add_argument("--min-weight", type=float, default=70.0, help="Min weight threshold")
    parser.add_argument("--priv-key", default=DEFAULT_PRIV_KEY, help="Private key hex")
    parser.add_argument("--output", default="data/client.lic", help="Output path")
    args = parser.parse_args()

    generate_client_license(
        args.device_id, args.device_key, args.center_id,
        args.min_weight, args.priv_key, args.output,
    )


if __name__ == "__main__":
    main()
