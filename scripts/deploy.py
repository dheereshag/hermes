"""deploy.py — Single-command Pi deployment: build, purge source & .git, start."""
from __future__ import annotations

import argparse
import os
import shutil
import sys


def purge_source_and_git() -> None:
    """Removes .git, docs, tests, main.py, and all Python source files."""
    for p in (".git", ".github", "tests", "docs", "compiled_dist", "main.py"):
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        elif os.path.isfile(p):
            os.remove(p)
    for root, dirs, files in os.walk("src", topdown=False):
        for f in files:
            if f.endswith((".py", ".pyc", ".pyi")):
                os.remove(os.path.join(root, f))
        for d in dirs:
            dir_path = os.path.join(root, d)
            if d == "__pycache__" or not os.listdir(dir_path):
                shutil.rmtree(dir_path, ignore_errors=True)


def deploy(skip_prompt: bool = False) -> None:
    """Compiles Hermes, moves binaries to root, purges sources, and launches."""
    if not skip_prompt:
        ans = input("[WARNING] Purge .git and all .py files? Type 'DEPLOY': ")
        if ans.strip() != "DEPLOY":
            print("[Deploy] Aborted.")
            sys.exit(1)

    sys.path.insert(0, os.getcwd())
    from scripts.build import build_binary

    if build_binary("build_tmp") != 0:
        sys.exit(1)
    for f in ("hermes", "hermes.sh"):
        src_path = os.path.join("build_tmp", f)
        if os.path.exists(src_path):
            shutil.move(src_path, f)
            os.chmod(f, 0o755)
    shutil.rmtree("build_tmp", ignore_errors=True)
    purge_source_and_git()
    shutil.rmtree("scripts", ignore_errors=True)
    print("\n[Deploy] Complete. Launching compiled Hermes natively...\n")
    runner = "./hermes.sh" if os.path.exists("hermes.sh") else "./hermes"
    os.execv(runner, [runner])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hermes Pi Clean Deployer")
    parser.add_argument("--yes", action="store_true", help="Bypass confirm prompt")
    deploy(parser.parse_args().yes)
