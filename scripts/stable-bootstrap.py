#!/usr/bin/env python3
"""Adopt an existing Stable installation from reviewed, exact published source.

Run this standalone file from outside the managed checkout with Python 3.12+.
No application environment, GitHub credentials or old-controller update is used.
"""

import argparse
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

UPSTREAM = "https://github.com/dmclark/sayloom.git"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True, help="reviewed full published-main commit SHA")
    arguments, forwarded = parser.parse_known_args()
    if not re.fullmatch(r"[0-9a-f]{40}", arguments.revision):
        parser.error("--revision must be a complete lowercase 40-character Git commit SHA")
    if sys.version_info < (3, 12):  # noqa: UP036 - standalone host prerequisite
        parser.error("Python 3.12 or newer is required; no system tooling will be installed")
    for executable in ("git", "uv", "launchctl", "lsof"):
        if not shutil.which(executable):
            parser.error(f"{executable} is required on PATH; install this prerequisite first")

    def git(*command: str) -> str:
        return subprocess.run(
            ["git", *command], check=True, capture_output=True, text=True, timeout=120
        ).stdout.strip()

    try:
        with tempfile.TemporaryDirectory(prefix="sayloom-bootstrap-") as directory:
            source = Path(directory) / "source"
            git("clone", "--branch", "main", "--single-branch", UPSTREAM, str(source))
            published = git("-C", str(source), "rev-parse", "HEAD")
            if published != arguments.revision and "--recovery" not in forwarded:
                parser.error(
                    "published main differs from the reviewed pin; review a new invocation"
                )
            git("-C", str(source), "checkout", "--detach", arguments.revision)
            # The downloaded standalone bootstrap must itself be the reviewed file.
            if (source / "scripts/stable-bootstrap.py").read_bytes() != Path(__file__).read_bytes():
                parser.error(
                    "bootstrap does not match the reviewed source; no installed files changed"
                )
            controller = source / "scripts/stable.py"
            print(
                f"Reviewed bootstrap source: {arguments.revision}; no installed checkout used.",
                flush=True,
            )
            sys.argv = [str(controller), "--adoption-revision", arguments.revision, *forwarded]
            runpy.run_path(str(controller), run_name="__main__")
    except (OSError, subprocess.SubprocessError) as exc:
        # Git output can contain private remote/configuration details. Do not echo it.
        print(
            f"error: bootstrap acquisition failed ({type(exc).__name__}); retry after checking "
            "network, prerequisites and the reviewed pin. Installed data was not replaced by "
            "the bootstrap acquisition step.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
