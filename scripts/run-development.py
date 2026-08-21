#!/usr/bin/env python3
"""Start one explicitly selected development state without mutating it."""

import argparse
import os
from pathlib import Path

from development_state import (
    DEFAULT_STATE_ROOT,
    fail,
    load_state,
    repository_root,
    state_environment,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    parser.add_argument("--state", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--port", type=int, required=True)
    arguments = parser.parse_args()

    state = load_state(arguments.state_root, arguments.state)
    if arguments.label != state.label or arguments.port != state.port:
        fail("runtime label or port does not match the selected state manifest")
    environment = state_environment(state, load_configuration=True)
    environment["LOCAL_TEXT_DEVELOPMENT_STATE_NAME"] = state.name
    root = repository_root()
    os.execve(
        root / ".venv/bin/uvicorn",
        [
            "uvicorn",
            "local_text.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(state.port),
            "--app-dir",
            str(root / "src"),
        ],
        environment,
    )


if __name__ == "__main__":
    main()
