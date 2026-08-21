#!/usr/bin/env python3
"""Render a state-scoped launchd plist without changing machine state."""

import argparse
from pathlib import Path
from xml.sax.saxutils import escape

from development_state import DEFAULT_STATE_ROOT, load_state, repository_root


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    parser.add_argument("--state", required=True)
    arguments = parser.parse_args()
    state = load_state(arguments.state_root, arguments.state)
    root = repository_root()
    template = root.joinpath(
        "launchd/local.local-text.development.plist.template"
    ).read_text()
    print(
        template.replace("__REPOSITORY_ROOT__", escape(str(root)))
        .replace("__STATE_ROOT__", escape(str(arguments.state_root.expanduser().resolve())))
        .replace("__STATE_NAME__", escape(state.name))
        .replace("__STATE_DIRECTORY__", escape(state.state_directory))
        .replace("__LABEL__", escape(state.label))
        .replace("__PORT__", str(state.port)),
        end="",
    )


if __name__ == "__main__":
    main()
