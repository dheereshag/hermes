"""build.py — Local Nuitka compilation script for bespoke client builds."""
from __future__ import annotations

import glob
import os
import subprocess
import sys


def build_client_package(output_dir: str = "compiled_dist") -> int:
    """Compiles src/ package into a native C-extension shared library."""
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--module",
        "--include-package=src",
        "--nofollow-imports",
        "--remove-output",
        "--lto=yes",
        "--python-flag=no_docstrings",
        f"--output-dir={output_dir}",
        "src",
    ]
    print(f"[Build] Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print("[Build] Compilation failed!", file=sys.stderr)
        return result.returncode

    artifacts = glob.glob(os.path.join(output_dir, "src*.so"))
    print(f"\n[Build] Success! Compiled native artifact(s): {artifacts}")
    print("[Build] To run with compiled module: cp compiled_dist/src*.so . && uv run python main.py")
    return 0


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "compiled_dist"
    sys.exit(build_client_package(out))
