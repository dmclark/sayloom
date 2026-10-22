#!/usr/bin/env python3
"""Launch the installed release snapshot. Never migrates, seeds or updates code."""

import os
from pathlib import Path

from development_state import load_environment_file


def main():
    root = Path(__file__).resolve().parent.parent
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("LOCAL_TEXT_")
        and key not in {"GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"}
    }
    environment.update(load_environment_file(Path.home() / ".config/local-text/stable/environment"))
    environment.update(
        {
            "LOCAL_TEXT_PROFILE": "release",
            "LOCAL_TEXT_STABLE_INSTANCE": "1",
            "LOCAL_TEXT_STATE_DIRECTORY": str(Path.home() / ".local/share/local-text/stable"),
            "LOCAL_TEXT_TRIAL_DIRECTORY": str(
                Path.home() / ".local/share/local-text/phrase-alternatives-trial"
            ),
            "LOCAL_TEXT_RAYCAST_DIRECTORY": str(Path.home() / ".config/raycast/scripts"),
        }
    )
    os.umask(0o077)
    os.execve(
        root / ".venv/bin/uvicorn",
        [
            "uvicorn",
            "local_text.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "7532",
            "--app-dir",
            str(root / "src"),
            "--no-access-log",
        ],
        environment,
    )


if __name__ == "__main__":
    main()
