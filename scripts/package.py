"""package.py — Build generic native binary and package release tarball."""
from __future__ import annotations

import os
import shutil
import sys
import tarfile


def create_release_package(output_tar: str = "dist/hermes-release.tar.gz") -> int:
    """Compiles native binary and packages clean release tarball (0 source code)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    from scripts.build import build_binary

    staging = "dist/staging_pkg"
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)

    code = build_binary(staging)
    if code != 0:
        return code

    for src_dir, dst_rel in (
        ("src/web/templates", "src/web/templates"),
        ("src/web/static", "src/web/static"),
    ):
        dst = os.path.join(staging, dst_rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copytree(src_dir, dst, dirs_exist_ok=True)

    os.makedirs(os.path.join(staging, "data"), exist_ok=True)
    shutil.copy("pyproject.toml", os.path.join(staging, "pyproject.toml"))

    os.makedirs(os.path.dirname(os.path.abspath(output_tar)), exist_ok=True)
    with tarfile.open(output_tar, "w:gz") as tar:
        for item in os.listdir(staging):
            tar.add(os.path.join(staging, item), arcname=item)

    shutil.rmtree(staging, ignore_errors=True)
    print(f"\n[Package] Success! Generic release bundle created: {output_tar}")
    print("[Package] Contains 0 .py files. Ready to deploy to client hardware.")
    return 0


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dist/hermes-release.tar.gz"
    sys.exit(create_release_package(out))
