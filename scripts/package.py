"""package.py — Build generic native binary and package release tarball."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tarfile


def create_release_package(
    output_tar: str = "dist/hermes-release.tar.gz",
    install_dir: str | None = None,
) -> int:
    """Compiles native binary and packages clean release bundle (0 .py files)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    from scripts.build import build_binary

    staging = "dist/staging_pkg"
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)

    if (code := build_binary(staging)) != 0:
        return code

    for src, rel in (("src/web/templates", "src/web/templates"), ("src/web/static", "src/web/static")):
        shutil.copytree(src, os.path.join(staging, rel), dirs_exist_ok=True)

    os.makedirs(os.path.join(staging, "data"), exist_ok=True)
    shutil.copy("pyproject.toml", os.path.join(staging, "pyproject.toml"))

    if install_dir:
        os.makedirs(install_dir, exist_ok=True)
        shutil.copytree(staging, install_dir, dirs_exist_ok=True)
        print(f"[Package] Installed release files directly to: {install_dir}")

    os.makedirs(os.path.dirname(os.path.abspath(output_tar)), exist_ok=True)
    with tarfile.open(output_tar, "w:gz") as tar:
        for item in os.listdir(staging):
            tar.add(os.path.join(staging, item), arcname=item)

    shutil.rmtree(staging, ignore_errors=True)
    print(f"\n[Package] Success! Generic release bundle created: {output_tar}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes release packager")
    parser.add_argument("--output", default="dist/hermes-release.tar.gz", help="Output tar")
    parser.add_argument("--install", default=None, help="Direct install destination directory")
    args = parser.parse_args()
    sys.exit(create_release_package(args.output, args.install))


if __name__ == "__main__":
    main()
