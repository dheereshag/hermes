"""build.py — Local Nuitka compilation script for Hermes native binary."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys


def build_binary(output_dir: str = "dist") -> int:
    """Compiles main.py and src/ into a native executable binary."""
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--include-package=src",
        "--nofollow-imports",
        "--include-package-data=src.web",
        "--remove-output",
        "--python-flag=no_docstrings",
        f"--output-dir={output_dir}",
        "--output-filename=hermes",
        "main.py",
    ]
    print(f"[Build] Compiling Hermes native binary to '{output_dir}/'...")
    res = subprocess.run(cmd, check=False)
    if res.returncode != 0:
        print("[Build] Compilation failed!", file=sys.stderr)
        return res.returncode

    print(f"\n[Build] Success! Binary created at: {output_dir}/hermes")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes native compiler")
    parser.add_argument("--output-dir", default="dist", help="Output directory")
    parser.add_argument("--run", action="store_true", help="Run after build")
    args = parser.parse_args()

    code = build_binary(args.output_dir)
    if code == 0 and args.run:
        script = os.path.join(args.output_dir, "hermes.sh")
        target = script if os.path.exists(script) else os.path.join(args.output_dir, "hermes")
        print(f"[Build] Launching {target}...\n")
        sys.exit(subprocess.run([target], check=False).returncode)
    sys.exit(code)


if __name__ == "__main__":
    main()
