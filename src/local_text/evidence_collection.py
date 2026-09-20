"""Process-local arming and frozen snapshots for intended-meaning collection."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from local_text.evidence_package import (
    CONTRACT_VERSION,
    PACKAGE_VERSION,
    EvidencePackageError,
    check_readiness,
    verify_observation,
    write_observation,
)

SOURCE_ATTESTATION_VERSION = "voiceitt-source-attestation-v1"
CORRECTION_CONTRACT_VERSION = "smart-correction-v1"
LEASE_LIFETIME = timedelta(minutes=30)
ELIGIBLE_DISPOSITIONS = {
    "ready_as_is",
    "presentation_cleanup_needed",
    "edit_intended",
}


class EvidenceCollectionError(RuntimeError):
    """A content-free collection protocol failure."""


@dataclass(frozen=True)
class CollectionLease:
    token: UUID
    expires_at: datetime
    source_attestation_version: str
    package_version: str
    package_contract_version: str


@dataclass(frozen=True)
class FrozenObservation:
    observation_id: UUID
    lease_token: UUID
    original: str
    task_context: str | None
    profile_enabled: bool
    relevant_profile_evidence: tuple[str, ...]
    prompt_version_id: int
    prompt_content_sha256: str
    triggered_at: datetime
    source_attestation_version: str
    package_version: str
    package_contract_version: str


class EvidenceCollection:
    """Own ephemeral leases and snapshots while private artifacts stay external."""

    def __init__(self, package_root: Path | None) -> None:
        self._package_root = package_root
        self._lease: CollectionLease | None = None
        self._frozen: dict[UUID, FrozenObservation] = {}

    def readiness(self) -> dict[str, object]:
        if self._package_root is None:
            return {
                "ready": False,
                "reason": "unconfigured",
                "package_version": None,
                "contract_version": None,
            }
        readiness = check_readiness(self._package_root)
        return {
            "ready": readiness.ready,
            "reason": readiness.reason,
            "package_version": readiness.package_version,
            "contract_version": readiness.contract_version,
        }

    def arm(self, *, attested: bool, now: datetime | None = None) -> CollectionLease:
        readiness = self.readiness()
        if not readiness["ready"]:
            raise EvidenceCollectionError("evidence collection is not ready")
        if not attested:
            raise EvidenceCollectionError("fresh source attestation is required")
        current = now or datetime.now(UTC)
        self._lease = CollectionLease(
            token=uuid4(),
            expires_at=current + LEASE_LIFETIME,
            source_attestation_version=SOURCE_ATTESTATION_VERSION,
            package_version=PACKAGE_VERSION,
            package_contract_version=CONTRACT_VERSION,
        )
        self._frozen.clear()
        return self._lease

    def disarm(self) -> None:
        self._lease = None
        self._frozen.clear()

    def trigger(
        self,
        *,
        lease_token: UUID,
        original: str,
        task_context: str | None,
        profile_enabled: bool,
        relevant_profile_evidence: tuple[str, ...],
        prompt_version_id: int,
        prompt_content_sha256: str,
        now: datetime | None = None,
    ) -> FrozenObservation:
        lease = self._require_lease(lease_token, now=now)
        if not original.strip():
            raise EvidenceCollectionError("an Original is required")
        observation = FrozenObservation(
            observation_id=uuid4(),
            lease_token=lease.token,
            original=original,
            task_context=task_context if task_context and task_context.strip() else None,
            profile_enabled=profile_enabled,
            relevant_profile_evidence=relevant_profile_evidence,
            prompt_version_id=prompt_version_id,
            prompt_content_sha256=prompt_content_sha256,
            triggered_at=now or datetime.now(UTC),
            source_attestation_version=lease.source_attestation_version,
            package_version=lease.package_version,
            package_contract_version=lease.package_contract_version,
        )
        self._frozen = {observation.observation_id: observation}
        return observation

    def confirm(
        self,
        *,
        lease_token: UUID,
        observation_id: UUID,
        disposition: str,
        intended: str,
        now: datetime | None = None,
    ) -> FrozenObservation:
        self._require_lease(lease_token, now=now)
        observation = self._frozen.get(observation_id)
        if observation is None or observation.lease_token != lease_token:
            raise EvidenceCollectionError("the frozen observation is stale")
        if disposition not in ELIGIBLE_DISPOSITIONS:
            raise EvidenceCollectionError("the disposition is not eligible")
        if not intended.strip():
            raise EvidenceCollectionError("Intended text is required")
        if disposition != "edit_intended" and intended != observation.original:
            raise EvidenceCollectionError("this disposition requires Intended to equal Original")
        confirmed_at = now or datetime.now(UTC)
        private_record: dict[str, Any] = {
            "original": observation.original,
            "intended": intended,
            "disposition": disposition,
            "context": {"task_context": observation.task_context},
            "profile": {
                "enabled": observation.profile_enabled,
                "relevant_evidence": list(observation.relevant_profile_evidence),
            },
            "correction_contract_version": CORRECTION_CONTRACT_VERSION,
            "prompt_contract": {
                "version_id": observation.prompt_version_id,
                "content_sha256": observation.prompt_content_sha256,
            },
            "source_attestation_version": observation.source_attestation_version,
            "package_version": observation.package_version,
            "package_contract_version": observation.package_contract_version,
            "triggered_at": _timestamp(observation.triggered_at),
            "confirmed_at": _timestamp(confirmed_at),
        }
        try:
            if self._package_root is None:
                raise EvidencePackageError("evidence package is not ready")
            receipt = write_observation(
                self._package_root, observation.observation_id, private_record
            )
            verify_observation(self._package_root, receipt)
        except EvidencePackageError as exc:
            self.disarm()
            raise EvidenceCollectionError("observation storage verification failed") from exc
        del self._frozen[observation_id]
        return observation

    def _require_lease(
        self, lease_token: UUID, *, now: datetime | None = None
    ) -> CollectionLease:
        current = now or datetime.now(UTC)
        lease = self._lease
        if lease is None or lease.token != lease_token or lease.expires_at <= current:
            self.disarm()
            raise EvidenceCollectionError("the evidence collection lease is not active")
        if not self.readiness()["ready"]:
            self.disarm()
            raise EvidenceCollectionError("evidence collection is not ready")
        return lease


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
