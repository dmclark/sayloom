"""Externally administered storage for private intended-meaning evidence."""

import json
import os
import stat
import unicodedata
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

MANIFEST_VERSION = "participant-package-manifest-v1"
PACKAGE_VERSION = "evidence-package-v1"
CONTRACT_VERSION = "intended-meaning-evidence-collection-v1"

_PERMITTED_USES = (
    "collection",
    "verification",
    "private_review",
    "classification",
    "partitioning",
    "derive_cleanup_evaluation_view",
    "derive_smart_evaluation_view",
)

_MANIFEST = "manifest.json"
_APPROVAL = "approval.json"
_DIRECTORIES = ("observations", "tombstones", ".checks")


class EvidencePackageError(RuntimeError):
    """A content-free external-package failure."""


@dataclass(frozen=True)
class PackageCreation:
    package_id: UUID
    participant_id: UUID
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
    participant_id = uuid4()
    manifest = _canonical_json(
        {
            "collection_contract_version": CONTRACT_VERSION,
            "created_at": _timestamp(created_at or datetime.now(UTC)),
            "manifest_version": MANIFEST_VERSION,
            "ownership": {
                "administrator_or_custodian_has_independent_rights": False,
                "owner_participant_id": str(participant_id),
                "participant_controls_package": True,
            },
            "package_id": str(package_id),
            "package_version": PACKAGE_VERSION,
            "participant_id": str(participant_id),
            "permitted_uses": list(_PERMITTED_USES),
            "retention": {
                "active_purposes_only": True,
                "extension_requires_owner_review": True,
                "owner_managed_backups_are_private_copies": True,
                "owner_managed_backups_follow_same_restrictions": True,
            },
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
    return PackageCreation(
        package_id=package_id,
        participant_id=participant_id,
        approval_digest=sha256(manifest).hexdigest(),
    )


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
    manifest, _, _, manifest_reason = _manifest_state(root)
    if manifest_reason is not None:
        raise EvidencePackageError("package manifest is not compatible")
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


def _manifest_state(
    root: Path,
) -> tuple[dict[str, Any], str | None, str | None, str | None]:
    manifest_path = root / _MANIFEST
    if not manifest_path.is_file():
        return {}, None, None, "manifest_missing"
    try:
        manifest = _read_json(manifest_path)
    except EvidencePackageError:
        return {}, None, None, "manifest_incomplete"
    package_version = manifest.get("package_version")
    contract_version = manifest.get("collection_contract_version")
    package_version_value = package_version if isinstance(package_version, str) else None
    contract_version_value = contract_version if isinstance(contract_version, str) else None
    if (
        manifest.get("manifest_version") != MANIFEST_VERSION
        or package_version_value != PACKAGE_VERSION
        or contract_version_value != CONTRACT_VERSION
    ):
        return manifest, package_version_value, contract_version_value, "version"
    required_keys = {
        "collection_contract_version",
        "created_at",
        "manifest_version",
        "ownership",
        "package_id",
        "package_version",
        "participant_id",
        "permitted_uses",
        "retention",
    }
    ownership = manifest.get("ownership")
    retention = manifest.get("retention")
    if (
        set(manifest) != required_keys
        or not isinstance(ownership, dict)
        or set(ownership)
        != {
            "administrator_or_custodian_has_independent_rights",
            "owner_participant_id",
            "participant_controls_package",
        }
        or not isinstance(retention, dict)
        or set(retention)
        != {
            "active_purposes_only",
            "extension_requires_owner_review",
            "owner_managed_backups_are_private_copies",
            "owner_managed_backups_follow_same_restrictions",
        }
    ):
        return manifest, package_version_value, contract_version_value, "manifest_incomplete"
    try:
        package_id = UUID(manifest["package_id"])
        participant_id = UUID(manifest["participant_id"])
        created_at = datetime.fromisoformat(manifest["created_at"].replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return manifest, package_version_value, contract_version_value, "manifest_incomplete"
    terms_match = (
        package_id != participant_id
        and created_at.tzinfo is not None
        and ownership
        == {
            "administrator_or_custodian_has_independent_rights": False,
            "owner_participant_id": str(participant_id),
            "participant_controls_package": True,
        }
        and manifest.get("permitted_uses") == list(_PERMITTED_USES)
        and retention
        == {
            "active_purposes_only": True,
            "extension_requires_owner_review": True,
            "owner_managed_backups_are_private_copies": True,
            "owner_managed_backups_follow_same_restrictions": True,
        }
    )
    return (
        manifest,
        package_version_value,
        contract_version_value,
        None if terms_match else "manifest_mismatch",
    )


def _metadata_versions(
    root: Path,
) -> tuple[str | None, str | None, bool, str | None]:
    manifest, package_version, contract_version, manifest_reason = _manifest_state(root)
    if manifest_reason is not None:
        return package_version, contract_version, False, manifest_reason
    try:
        approval = _read_json(root / _APPROVAL)
    except EvidencePackageError:
        return package_version, contract_version, False, None
    approved = (
        approval.get("approved") is True
        and approval.get("package_id") == manifest.get("package_id")
        and approval.get("package_version") == package_version
        and approval.get("contract_version") == contract_version
        and approval.get("manifest_sha256") == sha256(_read(root / _MANIFEST)).hexdigest()
    )
    return package_version, contract_version, approved, None


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
    manifest_reason: str | None = None
    external_location = not _inside_git(root)
    try:
        package_version, contract_version, approved, manifest_reason = _metadata_versions(root)
    except EvidencePackageError:
        manifest_reason = "manifest_incomplete"
    owned, restrictive = _permission_state(root)
    append_only, hash_and_reread = _probe_capabilities(root)
    if manifest_reason is not None:
        reason = manifest_reason
    elif not approved:
        reason = "not_approved"
    elif not external_location:
        reason = "location"
    elif not owned:
        reason = "ownership"
    elif not restrictive:
        reason = "permissions"
    else:
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


def write_exclusion(
    root: Path,
    observation_id: UUID,
    disposition: str,
    *,
    excluded_at: datetime | None = None,
) -> ObservationReceipt:
    """Write and verify an immutable exclusion containing no private content."""
    _require_ready(root)
    content = _canonical_json(
        {
            "artifact_type": "exclusion",
            "disposition": disposition,
            "excluded_at": _timestamp(excluded_at or datetime.now(UTC)),
            "observation_id": str(observation_id),
            "package_version": PACKAGE_VERSION,
        }
    )
    digest = sha256(content).hexdigest()
    path = root / "observations" / f"{observation_id}.json"
    _write_exclusive(path, content)
    _verify_bytes(path, content, digest)
    return ObservationReceipt(observation_id=observation_id, sha256=digest)


def find_exact_repeats(root: Path, original: str, intended: str) -> tuple[UUID, ...]:
    """Return provisional matches without persisting grouping information."""
    _require_ready(root)
    expected = (_repeat_normalize(original), _repeat_normalize(intended))
    matches: list[UUID] = []
    try:
        paths = sorted((root / "observations").glob("*.json"))
    except OSError as exc:
        raise EvidencePackageError("artifact reread failed") from exc
    for path in paths:
        artifact = _read_json(path)
        if artifact.get("artifact_type") != "eligible_observation":
            continue
        record = artifact.get("record")
        if not isinstance(record, dict):
            raise EvidencePackageError("package metadata is invalid")
        stored_original = record.get("original")
        stored_intended = record.get("intended")
        if not isinstance(stored_original, str) or not isinstance(stored_intended, str):
            raise EvidencePackageError("package metadata is invalid")
        if (_repeat_normalize(stored_original), _repeat_normalize(stored_intended)) != expected:
            continue
        try:
            matches.append(UUID(str(artifact["observation_id"])))
        except (KeyError, TypeError, ValueError) as exc:
            raise EvidencePackageError("package metadata is invalid") from exc
    return tuple(matches)


def _repeat_normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


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
    if not observation.is_file() and not tombstone.is_file():
        raise EvidencePackageError("observation does not exist")
    if (
        observation.is_file()
        and _read_json(observation).get("artifact_type") != "eligible_observation"
    ):
        raise EvidencePackageError("observation is not withdrawable")
    content = _canonical_json(
        {
            "artifact_type": "withdrawal_tombstone",
            "observation_id": str(observation_id),
            "package_version": PACKAGE_VERSION,
            "withdrawn_at": _timestamp(withdrawn_at or datetime.now(UTC)),
        }
    )
    if tombstone.exists():
        existing = _read(tombstone)
        try:
            retained = json.loads(existing)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise EvidencePackageError("package metadata is invalid") from exc
        if (
            not isinstance(retained, dict)
            or set(retained)
            != {"artifact_type", "observation_id", "package_version", "withdrawn_at"}
            or retained.get("artifact_type") != "withdrawal_tombstone"
            or retained.get("observation_id") != str(observation_id)
            or retained.get("package_version") != PACKAGE_VERSION
            or not isinstance(retained.get("withdrawn_at"), str)
        ):
            raise EvidencePackageError("package metadata is invalid")
    else:
        _write_exclusive(tombstone, content)
        _verify_bytes(tombstone, content, sha256(content).hexdigest())
    try:
        observation.unlink()
        _fsync_directory(observation.parent)
    except FileNotFoundError:
        if not tombstone.exists():
            raise EvidencePackageError("observation does not exist") from None
    except OSError as exc:
        raise EvidencePackageError("private content removal failed") from exc
    return WithdrawalReceipt(observation_id=observation_id)
