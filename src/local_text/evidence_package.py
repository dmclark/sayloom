"""Externally administered storage for private intended-meaning evidence."""

import json
import os
import stat
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

PACKAGE_VERSION = "evidence-package-v1"
CONTRACT_VERSION = "intended-meaning-evidence-collection-v1"

_MANIFEST = "manifest.json"
_APPROVAL = "approval.json"
_DIRECTORIES = ("observations", "tombstones", ".checks")


class EvidencePackageError(RuntimeError):
    """A content-free external-package failure."""


@dataclass(frozen=True)
class PackageCreation:
    package_id: UUID
    approval_digest: str


@dataclass(frozen=True)
class PackageApproval:
    package_id: UUID
    approved: bool = True


@dataclass(frozen=True)
class PackageReadiness:
    ready: bool
    reason: str | None
    package_version: str | None
    contract_version: str | None
    external_location: bool
    approved: bool
    owned: bool
    restrictive_permissions: bool
    append_only_writes: bool
    hash_and_reread: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ObservationReceipt:
    observation_id: UUID
    sha256: str


@dataclass(frozen=True)
class WithdrawalReceipt:
    observation_id: UUID


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode()
    except (TypeError, ValueError) as exc:
        raise EvidencePackageError("artifact is not valid JSON data") from exc


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise EvidencePackageError("timestamp must include a timezone")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _inside_git(root: Path) -> bool:
    resolved = root.expanduser().resolve()
    return any((candidate / ".git").exists() for candidate in (resolved, *resolved.parents))


def _write_exclusive(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise EvidencePackageError("immutable artifact already exists") from exc
    except OSError as exc:
        raise EvidencePackageError("immutable artifact write failed") from exc
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as artifact:
            artifact.write(content)
            artifact.flush()
            os.fsync(artifact.fileno())
    except OSError as exc:
        path.unlink(missing_ok=True)
        raise EvidencePackageError("immutable artifact write failed") from exc
    _fsync_directory(path.parent)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise EvidencePackageError("package durability check failed") from exc


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise EvidencePackageError("artifact reread failed") from exc


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_read(path))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise EvidencePackageError("package metadata is invalid") from exc
    if not isinstance(value, dict):
        raise EvidencePackageError("package metadata is invalid")
    return value


def _verify_bytes(path: Path, expected: bytes, expected_hash: str) -> None:
    reread = _read(path)
    if reread != expected or sha256(reread).hexdigest() != expected_hash:
        raise EvidencePackageError("artifact verification failed")


def create_package(root: Path, *, created_at: datetime | None = None) -> PackageCreation:
    """Create an unapproved package without exposing it to the application runtime."""
    root = root.expanduser()
    if not root.is_absolute():
        raise EvidencePackageError("external package path must be absolute")
    if _inside_git(root):
        raise EvidencePackageError("external package must remain outside Git")
    package_id = uuid4()
    manifest = _canonical_json(
        {
            "package_id": str(package_id),
            "package_version": PACKAGE_VERSION,
            "contract_version": CONTRACT_VERSION,
            "created_at": _timestamp(created_at or datetime.now(UTC)),
        }
    )
    try:
        root.mkdir(mode=0o700)
        root.chmod(0o700)
        for name in _DIRECTORIES:
            directory = root / name
            directory.mkdir(mode=0o700)
            directory.chmod(0o700)
        _write_exclusive(root / _MANIFEST, manifest)
    except FileExistsError as exc:
        raise EvidencePackageError("external package already exists") from exc
    except OSError as exc:
        raise EvidencePackageError("external package creation failed") from exc
    return PackageCreation(package_id=package_id, approval_digest=sha256(manifest).hexdigest())


def approve_package(
    root: Path,
    approval_digest: str,
    *,
    approved_at: datetime | None = None,
) -> PackageApproval:
    """Approve the exact immutable manifest presented by external administration."""
    manifest_bytes = _read(root / _MANIFEST)
    if sha256(manifest_bytes).hexdigest() != approval_digest:
        raise EvidencePackageError("approval digest does not match the package manifest")
    manifest = _read_json(root / _MANIFEST)
    try:
        package_id = UUID(str(manifest["package_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidencePackageError("package metadata is invalid") from exc
    approval = _canonical_json(
        {
            "approved": True,
            "approved_at": _timestamp(approved_at or datetime.now(UTC)),
            "contract_version": CONTRACT_VERSION,
            "manifest_sha256": approval_digest,
            "package_id": str(package_id),
            "package_version": PACKAGE_VERSION,
        }
    )
    _write_exclusive(root / _APPROVAL, approval)
    return PackageApproval(package_id=package_id)


def _permission_state(root: Path) -> tuple[bool, bool]:
    try:
        paths = (root, *root.rglob("*"))
        owned = all(path.lstat().st_uid == os.getuid() and not path.is_symlink() for path in paths)
        restrictive = all(
            stat.S_IMODE(path.lstat().st_mode) == (0o700 if path.is_dir() else 0o600)
            for path in paths
        )
    except OSError:
        return False, False
    return owned, restrictive


def _metadata_versions(root: Path) -> tuple[str | None, str | None, bool]:
    manifest = _read_json(root / _MANIFEST)
    package_version = manifest.get("package_version")
    contract_version = manifest.get("contract_version")
    try:
        approval = _read_json(root / _APPROVAL)
    except EvidencePackageError:
        return str(package_version), str(contract_version), False
    approved = (
        approval.get("approved") is True
        and approval.get("package_id") == manifest.get("package_id")
        and approval.get("package_version") == package_version
        and approval.get("contract_version") == contract_version
        and approval.get("manifest_sha256") == sha256(_read(root / _MANIFEST)).hexdigest()
    )
    return str(package_version), str(contract_version), approved


def _probe_capabilities(root: Path) -> tuple[bool, bool]:
    probe = root / ".checks" / f"{uuid4()}.probe"
    content = b"external-package-capability-check\n"
    expected_hash = sha256(content).hexdigest()
    append_only = False
    hash_and_reread = False
    try:
        _write_exclusive(probe, content)
        _verify_bytes(probe, content, expected_hash)
        hash_and_reread = True
        try:
            _write_exclusive(probe, b"replacement\n")
        except EvidencePackageError as exc:
            append_only = str(exc) == "immutable artifact already exists"
    except EvidencePackageError:
        pass
    finally:
        probe.unlink(missing_ok=True)
    return append_only, hash_and_reread


def check_readiness(root: Path) -> PackageReadiness:
    """Return content-free package readiness without returning or logging its path."""
    package_version: str | None = None
    contract_version: str | None = None
    approved = False
    external_location = not _inside_git(root)
    try:
        package_version, contract_version, approved = _metadata_versions(root)
    except EvidencePackageError:
        return PackageReadiness(
            False,
            "unavailable",
            package_version,
            contract_version,
            external_location,
            False,
            False,
            False,
            False,
            False,
        )
    owned, restrictive = _permission_state(root)
    if package_version != PACKAGE_VERSION or contract_version != CONTRACT_VERSION:
        reason = "version"
    elif not approved:
        reason = "not_approved"
    elif not external_location:
        reason = "location"
    elif not owned:
        reason = "ownership"
    elif not restrictive:
        reason = "permissions"
    else:
        append_only, hash_and_reread = _probe_capabilities(root)
        reason = None if append_only and hash_and_reread else "capabilities"
        return PackageReadiness(
            reason is None,
            reason,
            package_version,
            contract_version,
            external_location,
            approved,
            owned,
            restrictive,
            append_only,
            hash_and_reread,
        )
    return PackageReadiness(
        False,
        reason,
        package_version,
        contract_version,
        external_location,
        approved,
        owned,
        restrictive,
        False,
        False,
    )


def _require_ready(root: Path) -> None:
    if not check_readiness(root).ready:
        raise EvidencePackageError("evidence package is not ready")


def write_observation(
    root: Path,
    observation_id: UUID,
    private_record: Mapping[str, Any],
) -> ObservationReceipt:
    """Write one new immutable observation and verify its exact stored bytes."""
    _require_ready(root)
    content = _canonical_json(
        {
            "artifact_type": "eligible_observation",
            "observation_id": str(observation_id),
            "package_version": PACKAGE_VERSION,
            "record": private_record,
        }
    )
    digest = sha256(content).hexdigest()
    path = root / "observations" / f"{observation_id}.json"
    _write_exclusive(path, content)
    _verify_bytes(path, content, digest)
    return ObservationReceipt(observation_id=observation_id, sha256=digest)


def verify_observation(root: Path, receipt: ObservationReceipt) -> bool:
    """Reread an observation and verify the hash in its receipt."""
    _require_ready(root)
    content = _read(root / "observations" / f"{receipt.observation_id}.json")
    if sha256(content).hexdigest() != receipt.sha256:
        raise EvidencePackageError("artifact verification failed")
    return True


def withdraw_observation(
    root: Path,
    observation_id: UUID,
    *,
    withdrawn_at: datetime | None = None,
) -> WithdrawalReceipt:
    """Remove private observation content and append a content-free tombstone."""
    _require_ready(root)
    observation = root / "observations" / f"{observation_id}.json"
    tombstone = root / "tombstones" / f"{observation_id}.json"
    if tombstone.exists():
        raise EvidencePackageError("withdrawal tombstone already exists")
    try:
        observation.unlink()
        _fsync_directory(observation.parent)
    except FileNotFoundError as exc:
        raise EvidencePackageError("observation does not exist") from exc
    except OSError as exc:
        raise EvidencePackageError("private content removal failed") from exc
    content = _canonical_json(
        {
            "artifact_type": "withdrawal_tombstone",
            "observation_id": str(observation_id),
            "package_version": PACKAGE_VERSION,
            "withdrawn_at": _timestamp(withdrawn_at or datetime.now(UTC)),
        }
    )
    _write_exclusive(tombstone, content)
    _verify_bytes(tombstone, content, sha256(content).hexdigest())
    return WithdrawalReceipt(observation_id=observation_id)
