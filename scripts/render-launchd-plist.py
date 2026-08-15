#!/usr/bin/env python3
"""Render the launchd template to stdout without changing machine state."""

from pathlib import Path
from xml.sax.saxutils import escape

repository_root = Path(__file__).resolve().parent.parent
state_directory = Path.home() / "Library/Application Support/local-text/development"
template = repository_root.joinpath(
    "launchd/local.local-text.development.plist.template"
).read_text()

print(
    template.replace("__REPOSITORY_ROOT__", escape(str(repository_root))).replace(
        "__STATE_DIRECTORY__", escape(str(state_directory))
    ),
    end="",
)
