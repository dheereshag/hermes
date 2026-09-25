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
    if (code := subprocess.run(cmd, check=False).returncode) != 0:
        print(f"[Deploy] Command failed: {' '.join(cmd)}", file=sys.stderr)
        sys.exit(code)


def deploy_remote(host: str, target: str = "/opt/hermes", lic: str = "data/client.lic") -> None:
    print(f"[Deploy] 1. Preparing {target} and checking uv on {host}...")
    prep = (
        f"sudo mkdir -p {target} && sudo chown -R $USER:$USER {target}; "
        "export PATH=\"$HOME/.local/bin:$HOME/.cargo/bin:$PATH\"; "
        "command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh"
    )
    run_cmd(["ssh", "-t", host, f"bash -c '{prep}'"])
    print(f"[Deploy] 2. Syncing source to {host}:{target}...")
    run_cmd(["rsync", "-avz", "--delete", *EXCLUDES, "./", f"{host}:{target}/"])
    print(f"[Deploy] 3. Building native binary on {host} and purging source code...")
    build = (
        "set -e; export PATH=\"$HOME/.local/bin:$HOME/.cargo/bin:$PATH\"; "
        f"cd {target} && uv sync && uv run python scripts/build.py --output-dir={target}; "
        f"find {target} -maxdepth 1 -name '*.py' -delete && find {target}/src -name '*.py' -delete; "
        f"rm -rf {target}/scripts {target}/tests {target}/docs; "
        f"echo '[Deploy] Source purged! Only compiled binary remains at {target}.'"
    )
    run_cmd(["ssh", "-t", host, f"bash -c '{build}'"])
    if os.path.exists(lic):
        print(f"[Deploy] 4. Uploading license {lic} -> {target}/data/client.lic...")
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
