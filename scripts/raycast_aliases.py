"""Safe installation and repointing of development Raycast aliases."""

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DIRECTORY = Path("~/.config/raycast/scripts")


@dataclass(frozen=True)
class AliasPlan:
    directory: Path
    aliases: tuple[tuple[Path, Path], ...]
    replacements: tuple[tuple[Path, Path], ...]
    removals: tuple[Path, ...] = ()


def command_sources(repository: Path) -> list[Path]:
    return sorted(
        source
        for source in (repository / "raycast").glob("*.sh")
        if "# @raycast.schemaVersion" in source.read_text()
    )


def _linked_path(destination: Path) -> Path:
    linked = destination.readlink()
    if not linked.is_absolute():
        linked = destination.parent / linked
    return linked


def _is_managed_checkout_alias(destination: Path, repository: Path) -> bool:
    if not destination.is_symlink():
        return False
    linked = _linked_path(destination)
    if destination.name != f"dev-{linked.name}" or linked.parent.name != "raycast":
        return False
    if linked.parent.resolve() == (repository / "raycast").resolve():
        return True
    try:
        content = linked.read_text()
    except OSError:
        return False
    return (
        "# @raycast.schemaVersion" in content
        and "# @raycast.packageName Sayloom Development" in content
    )


def plan_install(
    directory: Path,
    repository: Path,
    *,
    repoint_managed: bool = False,
    installed_only: bool = False,
) -> AliasPlan:
    directory = directory.expanduser()
    if directory.exists() and not directory.is_dir():
        raise ValueError(f"Raycast Script Commands path is not a directory: {directory}")

    aliases = tuple(
        (source.resolve(), directory / f"dev-{source.name}")
        for source in command_sources(repository)
    )
    if installed_only and not directory.exists():
        return AliasPlan(directory, aliases, ())

    managed_aliases = (
        {
            destination
            for destination in directory.iterdir()
            if _is_managed_checkout_alias(destination, repository)
        }
        if directory.exists()
        else set()
    )
    desired_destinations = {destination for _source, destination in aliases}
    removals = tuple(sorted(managed_aliases - desired_destinations)) if repoint_managed else ()

    replacements: list[tuple[Path, Path]] = []
    for source, destination in aliases:
        if destination.is_symlink():
            if _linked_path(destination).resolve() == source:
                continue
            if repoint_managed and _is_managed_checkout_alias(destination, repository):
                replacements.append((source, destination))
                continue
            try:
                destination.resolve(strict=True)
            except OSError:
                replacements.append((source, destination))
                continue
            raise ValueError(f"refusing to replace symlink to another source: {destination}")
        if destination.exists():
            raise ValueError(f"refusing to replace existing entry: {destination}")
        if not installed_only or managed_aliases:
            replacements.append((source, destination))
    return AliasPlan(directory, aliases, tuple(replacements), removals)


def apply_plan(plan: AliasPlan) -> tuple[int, int]:
    if not plan.replacements and not plan.removals:
        return 0, len(plan.aliases)
    plan.directory.mkdir(parents=True, exist_ok=True)
    for source, destination in plan.replacements:
        temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
        try:
            temporary.symlink_to(source)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    for destination in plan.removals:
        destination.unlink()
    return len(plan.replacements), len(plan.aliases) - len(plan.replacements)
