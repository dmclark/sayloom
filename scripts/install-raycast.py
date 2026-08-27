#!/usr/bin/env python3
"""Install development Raycast command aliases for Sayloom."""

import argparse
from pathlib import Path

from raycast_aliases import DEFAULT_DIRECTORY, apply_plan, plan_install


def repository_root() -> Path:
    return Path(__file__).resolve().parent.parent


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def install(directory: Path) -> None:
    try:
        plan = plan_install(directory, repository_root())
    except ValueError as error:
        fail(str(error))
    installed, verified = apply_plan(plan)
    print(
        f"Installed {installed}; verified {verified} existing development "
        f"Raycast aliases in {plan.directory}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    arguments = parser.parse_args()
    install(arguments.directory)


if __name__ == "__main__":
    main()
