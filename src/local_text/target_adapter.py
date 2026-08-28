"""Local filesystem boundary for Sayloom-owned generated Raycast commands."""

import hashlib
import os
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from local_text.targets import GeneratedCommand, command_filename


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


class TargetAdapter:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.expanduser()

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
