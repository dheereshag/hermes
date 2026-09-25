"""deploy.py — 1-command remote Pi deploy: rsync, compile, install, purge source."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

EXCLUDES = [
    "--exclude=.venv", "--exclude=dist", "--exclude=__pycache__",
    "--exclude=.git", "--exclude=tests", "--exclude=docs", "--exclude=*.db",
]


def run_cmd(cmd: list[str]) -> None:
    res = subprocess.run(cmd, check=False)
    if res.returncode != 0:
        print(f"[Deploy] Command failed: {' '.join(cmd)}", file=sys.stderr)
        sys.exit(res.returncode)


def deploy_remote(host: str, target: str = "/opt/hermes", lic: str = "data/client.lic") -> None:
    tmp_build = "/tmp/hermes_build"
    print(f"[Deploy] 1. Syncing source to {host}:{tmp_build}...")
    run_cmd(["rsync", "-avz", "--delete", *EXCLUDES, "./", f"{host}:{tmp_build}/"])

    print(f"[Deploy] 2. Remote building binary on {host} and installing to {target}...")
    remote_cmds = (
        "set -e; "
        "export PATH=\"$HOME/.cargo/bin:$HOME/.local/bin:/usr/local/bin:$PATH\"; "
        "command -v uv >/dev/null || (curl -LsSf https://astral.sh/uv/install.sh | sh && export PATH=\"$HOME/.cargo/bin:$PATH\"); "
        f"sudo mkdir -p {target} && sudo chown -R $USER:$USER {target}; "
        f"cd {tmp_build} && uv run python scripts/package.py --install {target}; "
        f"cd {target} && uv sync; "
        f"rm -rf {tmp_build}; "
        f"echo '[Deploy] Source purged from {tmp_build}. Only binary remains at {target}.'; "
        "(sudo systemctl restart hermes 2>/dev/null || true)"
    )
    run_cmd(["ssh", "-t", host, f"bash -c '{remote_cmds}'"])

    if os.path.exists(lic):
        print(f"[Deploy] 3. Uploading license {lic} -> {target}/data/client.lic...")
        run_cmd(["ssh", host, f"mkdir -p {target}/data"])
        run_cmd(["scp", lic, f"{host}:{target}/data/client.lic"])

    print(f"\n[Deploy] Complete! Hermes deployed to {host}:{target} (0 .py files).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes 1-Command Pi Deployer")
    parser.add_argument("--host", required=True, help="Target SSH host (e.g. pi@192.168.1.50)")
    parser.add_argument("--target", default="/opt/hermes", help="Pi target dir")
    parser.add_argument("--license", default="data/client.lic", help="Client license path")
    args = parser.parse_args()
    deploy_remote(args.host, args.target, args.license)


if __name__ == "__main__":
    main()
