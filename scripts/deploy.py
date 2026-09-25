"""deploy.py — 1-command remote Pi deploy: keygen, compile, systemd, purge source."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXCLUDES = ["--exclude=.venv", "--exclude=dist", "--exclude=__pycache__", "--exclude=.git", "--exclude=tests", "--exclude=docs", "--exclude=*.db"]


def run_cmd(cmd: list[str]) -> None:
    if (code := subprocess.run(cmd, check=False).returncode) != 0:
        print(f"[Deploy] Command failed: {' '.join(cmd)}", file=sys.stderr)
        sys.exit(code)


def deploy_remote(host: str, target: str = "/opt/hermes", lic: str = "data/client.lic") -> None:
    user = host.split("@")[0] if "@" in host else "gluvok"
    print(f"[Deploy] 1. Preparing {target} on {host}...")
    prep = f"sudo mkdir -p {target} && sudo chown -R $USER:$USER {target}; export PATH=\"$HOME/.local/bin:$PATH\"; command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh"
    run_cmd(["ssh", "-t", host, prep])
    print(f"[Deploy] 2. Syncing source to {host}:{target}...")
    run_cmd(["rsync", "-avz", "--delete", *EXCLUDES, "./", f"{host}:{target}/"])
    print(f"[Deploy] 3. Compiling binary into {target}/bin/ and purging source...")
    build = (
        f"set -e; export PATH=\"$HOME/.local/bin:$PATH\"; cd {target} && uv sync && uv run python scripts/build.py --output-dir={target}/bin && chmod +x {target}/run.sh {target}/bin/hermes; "
        f"rm -f {target}/bin/hermes.sh; find {target} -maxdepth 1 -name '*.py' -delete && find {target}/src -name '*.py' -delete; rm -rf {target}/scripts {target}/tests {target}/docs; "
        f"echo '[Deploy] Source purged! Only bin/hermes and run.sh remain at {target}.'"
    )
    run_cmd(["ssh", "-t", host, build])
    print("[Deploy] 4. Provisioning systemd service & client license...")
    svc = f"[Unit]\nDescription=Hermes\nAfter=network-online.target\n[Service]\nType=simple\nUser={user}\nWorkingDirectory={target}\nExecStart={target}/run.sh\nRestart=always\nRestartSec=5\nEnvironment=PYTHONUNBUFFERED=1\n[Install]\nWantedBy=multi-user.target\n"
    os.makedirs("dist", exist_ok=True)
    with open("dist/hermes.service", "w", encoding="utf-8") as f: f.write(svc)
    run_cmd(["scp", "dist/hermes.service", f"{host}:/tmp/hermes.service"])
    run_cmd(["ssh", "-t", host, f"sudo mv /tmp/hermes.service /etc/systemd/system/hermes.service && sudo systemctl daemon-reload && sudo systemctl enable --now hermes && mkdir -p {target}/data"])
    if os.path.exists(lic):
        run_cmd(["scp", lic, f"{host}:{target}/data/client.lic"])
        run_cmd(["ssh", "-t", host, "sudo systemctl restart hermes"])
    print(f"\n[Deploy] Complete! Hermes active & running 24/7 on {host} via {target}/run.sh.")


def main() -> None:
    p = argparse.ArgumentParser(description="Hermes 1-Command Pi Deployer")
    p.add_argument("--host", required=True); p.add_argument("--target", default="/opt/hermes"); p.add_argument("--license", default="data/client.lic")
    p.add_argument("--device-id"); p.add_argument("--device-key"); p.add_argument("--center-id", type=int); p.add_argument("--min-weight", type=float, default=70.0)
    a = p.parse_args()
    if a.device_id and a.device_key and a.center_id:
        from scripts.keygen import generate_client_license
        generate_client_license(a.device_id, a.device_key, a.center_id, a.min_weight, output_path=a.license)
    deploy_remote(a.host, a.target, a.license)


if __name__ == "__main__":
    main()
