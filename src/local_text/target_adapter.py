"""Local filesystem boundary for Sayloom-owned generated Raycast commands."""

import hashlib
import os
import plistlib
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import ValidationError

from local_text.targets import (
    GeneratedCommand,
    SendStrategy,
    TargetDefinition,
    command_filename,
)

MAX_APPLICATION_PLIST_BYTES = 1_000_000


class InstallationState(StrEnum):
    NOT_INSTALLED = "not_installed"
    INSTALLED = "installed"
    NEEDS_UPDATE = "needs_update"
    COLLISION = "collision"


class TargetArtifactError(RuntimeError):
    def __init__(self, code: str, message: str, retry_action: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_action = retry_action


@dataclass(frozen=True)
class TargetObservation:
    installation: InstallationState
    availability: str = "not_verified"
    availability_action: str = "Check this application on the Mac that runs Raycast."
    permission: str = "not_verified"
    permission_action: str = "Run the command on that Mac and follow any macOS prompt."


@dataclass(frozen=True)
class DiscoveredApplication:
    display_name: str
    application_name: str
    application_bundle_id: str
    send_strategy: SendStrategy


class TargetAdapter:
    def __init__(
        self,
        directory: Path,
        *,
        application_directories: tuple[Path, ...] | None = None,
    ) -> None:
        self.directory = directory.expanduser()
        self.application_directories = (
            application_directories
            if application_directories is not None
            else (
                Path("/Applications"),
                Path.home() / "Applications",
                Path("/System/Applications"),
            )
        )

    def discover_applications(self) -> list[DiscoveredApplication]:
        applications: dict[str, DiscoveredApplication] = {}
        for directory in self.application_directories:
            if directory.is_symlink() or not directory.is_dir():
                continue
            bundles = (*directory.glob("*.app"), *directory.glob("*/*.app"))
            for bundle in bundles:
                application = self._read_application(bundle)
                if application is not None:
                    applications.setdefault(application.application_bundle_id, application)
        return sorted(
            applications.values(),
            key=lambda application: (
                application.display_name.casefold(),
                application.application_bundle_id,
            ),
        )

    @staticmethod
    def _read_application(bundle: Path) -> DiscoveredApplication | None:
        if bundle.parent.is_symlink() or bundle.is_symlink() or not bundle.is_dir():
            return None
        information = bundle / "Contents/Info.plist"
        try:
            if information.is_symlink() or not information.is_file():
                return None
            if information.stat().st_size > MAX_APPLICATION_PLIST_BYTES:
                return None
            with information.open("rb") as stream:
                metadata = plistlib.load(stream)
        except (OSError, plistlib.InvalidFileException):
            return None
        if not isinstance(metadata, dict):
            return None
        bundle_id = metadata.get("CFBundleIdentifier")
        application_name = metadata.get("CFBundleName") or bundle.stem
        display_name = metadata.get("CFBundleDisplayName") or application_name
        if not all(isinstance(value, str) for value in (bundle_id, application_name, display_name)):
            return None
        strategy = (
            SendStrategy.ITERM_WRITE
            if bundle_id == "com.googlecode.iterm2"
            else SendStrategy.SYNTHETIC_PASTE
        )
        try:
            definition = TargetDefinition(
                display_name=display_name,
                application_name=application_name,
                application_bundle_id=bundle_id,
                send_strategy=strategy,
            )
        except ValidationError:
            return None
        return DiscoveredApplication(
            display_name=definition.display_name,
            application_name=definition.application_name,
            application_bundle_id=definition.application_bundle_id,
            send_strategy=definition.send_strategy,
        )

    def _path(self, target_id: str) -> Path:
        return self.directory / command_filename(target_id)

    @staticmethod
    def _is_owned(path: Path, target_id: str) -> bool:
        if path.is_symlink() or not path.is_file():
            return False
        try:
            header = path.read_text()[:2_000]
        except (OSError, UnicodeError):
            return False
        return (
            f"# sayloom-owned-target: {target_id}\n" in header
            and f"# sayloom-generated-file: {path.name}\n" in header
        )

    def observe(self, target_id: str, generated: GeneratedCommand) -> TargetObservation:
        path = self._path(target_id)
        if not path.is_symlink() and not path.exists():
            return TargetObservation(InstallationState.NOT_INSTALLED)
        if not self._is_owned(path, target_id):
            return TargetObservation(InstallationState.COLLISION)
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return TargetObservation(InstallationState.COLLISION)
        state = (
            InstallationState.INSTALLED
            if digest == generated.sha256
            else InstallationState.NEEDS_UPDATE
        )
        return TargetObservation(state)

    def install(self, target_id: str, generated: GeneratedCommand) -> TargetObservation:
        path = self._path(target_id)
        current = self.observe(target_id, generated)
        if current.installation is InstallationState.COLLISION:
            raise TargetArtifactError(
                "unrelated_artifact",
                "The command destination is not a recognized Sayloom-owned artifact.",
                "Move or rename the unrelated entry, then retry installation.",
            )
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not self.directory.is_dir():
                raise OSError("command directory is not a directory")
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{path.name}.", dir=self.directory
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "w") as stream:
                    stream.write(generated.content)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.chmod(0o700)
                temporary.replace(path)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        except OSError as exc:
            raise TargetArtifactError(
                "install_failed",
                "Sayloom could not write the generated command.",
                "Check the Raycast Script Commands directory and retry.",
            ) from exc
        return self.observe(target_id, generated)

    def remove(self, target_id: str, generated: GeneratedCommand) -> None:
        path = self._path(target_id)
        current = self.observe(target_id, generated)
        if current.installation is InstallationState.NOT_INSTALLED:
            return
        if current.installation is InstallationState.COLLISION:
            raise TargetArtifactError(
                "unrelated_artifact",
                "The command destination is not a recognized Sayloom-owned artifact.",
                "Leave it in place or move it manually before retrying.",
            )
        try:
            path.unlink()
        except OSError as exc:
            raise TargetArtifactError(
                "remove_failed",
                "Sayloom could not remove its generated command.",
                "Check command-directory permissions and retry.",
            ) from exc
