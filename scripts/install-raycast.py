#!/usr/bin/env python3
"""Install development Raycast command aliases for Sayloom."""

import argparse
from pathlib import Path

DEFAULT_DIRECTORY = Path("~/.config/raycast/scripts")


def repository_root() -> Path:
    return Path(__file__).resolve().parent.parent


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def command_sources() -> list[Path]:
    return sorted(
        source
        for source in (repository_root() / "raycast").glob("*.sh")
        if "# @raycast.schemaVersion" in source.read_text()
    )


def install(directory: Path) -> None:
    directory = directory.expanduser()
    if directory.exists() and not directory.is_dir():
        fail(f"Raycast Script Commands path is not a directory: {directory}")

    sources = command_sources()
    aliases = [(source, directory / f"dev-{source.name}") for source in sources]
    for source, destination in aliases:
        if destination.is_symlink():
            try:
                linked_source = destination.resolve(strict=True)
            except OSError:
                fail(f"refusing to replace broken symlink: {destination}")
            if linked_source != source.resolve():
                fail(f"refusing to replace symlink to another source: {destination}")
        elif destination.exists():
            fail(f"refusing to replace existing entry: {destination}")

    directory.mkdir(parents=True, exist_ok=True)
    installed = 0
    for source, destination in aliases:
        if not destination.is_symlink():
            destination.symlink_to(source.resolve())
            installed += 1
    verified = len(aliases) - installed
    print(
        f"Installed {installed}; verified {verified} existing development "
        f"Raycast aliases in {directory}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    arguments = parser.parse_args()
    install(arguments.directory)


if __name__ == "__main__":
    main()
