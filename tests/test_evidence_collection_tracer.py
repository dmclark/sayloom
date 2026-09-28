import json
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from local_text.app import create_app
from local_text.cleanup import CleanupService, ProviderOutput
from local_text.config import Settings
from local_text.evidence_collection import (
    CollectionLease,
    EvidenceCollection,
    EvidenceCollectionError,
)
from local_text.evidence_package import EvidencePackageError, approve_package, create_package


def configured_package(tmp_path: Path) -> tuple[Path, Path]:
    evaluation_directory = tmp_path / "evaluation"
    evaluation_directory.mkdir(mode=0o700)
    package = evaluation_directory / "intended-meaning-evidence"
    creation = create_package(package)
    approve_package(package, creation.approval_digest)
    return evaluation_directory, package


def armed_collection(tmp_path: Path) -> tuple[EvidenceCollection, Path, CollectionLease]:
    _evaluation_directory, package = configured_package(tmp_path)
    collection = EvidenceCollection(package)
    lease = collection.arm(
        browser_session_id=uuid4(),
        attested=True,
        now=datetime.now(UTC),
    )
    return collection, package, lease


def trigger(
    collection: EvidenceCollection,
    lease: CollectionLease,
    original: str = "Synthetic source",
):
    return collection.trigger(
        lease_token=lease.token,
        original=original,
        task_context="Synthetic context",
        profile_enabled=False,
        relevant_profile_evidence=(),
        prompt_version_id=1,
        prompt_content_sha256="a" * 64,
        correction_mode="smart",
        now=datetime.now(UTC),
    )


def test_all_dispositions_remain_distinct_and_exclusions_are_content_free(tmp_path: Path) -> None:
    collection, package, lease = armed_collection(tmp_path)
    dispositions = (
        "ready_as_is",
        "presentation_cleanup_needed",
        "edit_intended",
        "not_voiceitt",
        "cannot_reliably_reconstruct",
        "exclude",
    )

    for disposition in dispositions:
        frozen = trigger(collection, lease)
        intended = "Synthetic intent" if disposition == "edit_intended" else "Synthetic source"
        if disposition in {"not_voiceitt", "cannot_reliably_reconstruct", "exclude"}:
            intended = None
        collection.confirm(
            lease_token=lease.token,
            observation_id=frozen.observation_id,
            disposition=disposition,
            intended=intended,
        )

    artifacts = [
        json.loads(path.read_text())
        for path in (package / "observations").glob("*.json")
    ]
    eligible = [
        item["record"]
        for item in artifacts
        if item["artifact_type"] == "eligible_observation"
    ]
    excluded = [item for item in artifacts if item["artifact_type"] == "exclusion"]
    assert {item["disposition"] for item in eligible} == set(dispositions[:3])
    equal_text = {
        item["disposition"]: item["intended"]
        for item in eligible
        if item["disposition"] != "edit_intended"
    }
    assert equal_text == {
        "ready_as_is": "Synthetic source",
        "presentation_cleanup_needed": "Synthetic source",
    }
    assert {item["disposition"] for item in excluded} == set(dispositions[3:])
    assert all("record" not in item for item in excluded)
    assert all("Synthetic" not in json.dumps(item) for item in excluded)


def test_cancel_edit_staleness_empty_input_and_expiry_never_release_a_receipt(
    tmp_path: Path,
) -> None:
    collection, package, lease = armed_collection(tmp_path)
    cancelled = trigger(collection, lease)
    collection.cancel(lease_token=lease.token)

    with pytest.raises(EvidenceCollectionError, match="stale"):
        collection.confirm(
            lease_token=lease.token,
            observation_id=cancelled.observation_id,
            disposition="ready_as_is",
            intended="Synthetic source",
        )
    with pytest.raises(EvidenceCollectionError, match="Original"):
        trigger(collection, lease, " \n\t")
    assert list((package / "observations").iterdir()) == []

    frozen = trigger(collection, lease)
    confirmation = collection.confirm(
        lease_token=lease.token,
        observation_id=frozen.observation_id,
        disposition="ready_as_is",
        intended="Synthetic source",
    )
    assert collection.outgoing_allowed(
        original="Synthetic source",
        lease_token=lease.token,
        receipt_token=confirmation.receipt.token,
    )
    collection.cancel(lease_token=lease.token)
    assert not collection.outgoing_allowed(
        original="Synthetic source",
        lease_token=lease.token,
        receipt_token=confirmation.receipt.token,
    )
    assert not collection.outgoing_allowed(
        original="Synthetic source",
        lease_token=lease.token,
        receipt_token=None,
        now=lease.expires_at + timedelta(seconds=1),
    )


def test_stale_browser_cannot_stop_a_newer_session(tmp_path: Path) -> None:
    collection, _package, first_lease = armed_collection(tmp_path)
    second_lease = collection.arm(
        browser_session_id=uuid4(),
        attested=True,
        now=datetime.now(UTC),
    )
    collection.begin_browser_session(
        uuid4(),
        previous_lease_token=first_lease.token,
    )

    with pytest.raises(EvidenceCollectionError, match="not active"):
        collection.stop(lease_token=first_lease.token)
    assert trigger(collection, second_lease).lease_token == second_lease.token


@pytest.mark.parametrize("failure_point", ["write", "reread_or_hash"])
def test_storage_failures_disarm_without_releasing_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_point: str
) -> None:
    collection, _package, lease = armed_collection(tmp_path)
    frozen = trigger(collection, lease)

    def fail(*_args, **_kwargs):
        raise EvidencePackageError("synthetic package failure")

    target = "write_observation" if failure_point == "write" else "verify_observation"
    monkeypatch.setattr(f"local_text.evidence_collection.{target}", fail)
    with pytest.raises(EvidenceCollectionError, match="storage verification failed"):
        collection.confirm(
            lease_token=lease.token,
            observation_id=frozen.observation_id,
            disposition="ready_as_is",
            intended="Synthetic source",
        )
    assert not collection.outgoing_allowed(
        original="Synthetic source",
        lease_token=lease.token,
        receipt_token=None,
    )


def test_ambiguous_or_lost_readiness_disarms_active_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collection, _package, lease = armed_collection(tmp_path)
    monkeypatch.setattr(
        collection,
        "readiness",
        lambda: {
            "ready": False,
            "reason": "ambiguous",
            "package_version": None,
            "contract_version": None,
        },
    )

    with pytest.raises(EvidenceCollectionError, match="not ready"):
        trigger(collection, lease)
    assert not collection.outgoing_allowed(
        original="Synthetic source",
        lease_token=lease.token,
        receipt_token=None,
    )


def test_withdrawal_uses_tombstone_and_invalidates_receipt(tmp_path: Path) -> None:
    collection, package, lease = armed_collection(tmp_path)
    frozen = trigger(collection, lease)
    confirmation = collection.confirm(
        lease_token=lease.token,
        observation_id=frozen.observation_id,
        disposition="edit_intended",
        intended="Synthetic intent",
    )
    later = trigger(collection, lease, "Another synthetic source")
    collection.confirm(
        lease_token=lease.token,
        observation_id=later.observation_id,
        disposition="ready_as_is",
        intended="Another synthetic source",
    )

    collection.withdraw(
        observation_id=frozen.observation_id,
        now=datetime.now(UTC),
    )

    assert not (package / "observations" / f"{frozen.observation_id}.json").exists()
    tombstone = json.loads(
        (package / "tombstones" / f"{frozen.observation_id}.json").read_text()
    )
    assert set(tombstone) == {
        "artifact_type",
        "observation_id",
        "package_version",
        "withdrawn_at",
    }
    assert not collection.outgoing_allowed(
        original="Synthetic source",
        lease_token=lease.token,
        receipt_token=confirmation.receipt.token,
    )


def test_confirmed_observation_is_verified_before_smart_receives_only_frozen_input(
    initialized_settings: Settings, tmp_path: Path
) -> None:
    _evaluation_directory, package = configured_package(tmp_path)
    provider_calls: list[dict[str, object]] = []

    class Provider:
        provider_id = "synthetic"
        model = "synthetic-model"

        async def clean(
            self,
            original_text: str,
            system_prompt: str,
            *,
            task_context: str | None = None,
            relevant_curated_knowledge: tuple[str, ...] = (),
        ) -> ProviderOutput:
            artifact_count = len(list((package / "observations").glob("*.json")))
            provider_calls.append(
                {
                    "original_text": original_text,
                    "task_context": task_context,
                    "profile": relevant_curated_knowledge,
                    "artifact_count": artifact_count,
                    "system_prompt": system_prompt,
                }
            )
            return ProviderOutput(
                text="Send the report.",
                provider_id=self.provider_id,
                model_id=self.model,
                elapsed_ms=1,
            )

    settings = replace(initialized_settings, evidence_package_directory=package)
    service = CleanupService(provider=Provider(), model=Provider.model, timeout_seconds=1)
    with TestClient(create_app(settings, service)) as client:
        readiness = client.get("/api/config").json()["evidence_collection"]
        assert readiness["ready"] is True
        browser_session_id = str(uuid4())

        rejected = client.post(
            "/api/evidence-collection/arm",
            json={
                "browser_session_id": browser_session_id,
                "source_attestation_confirmed": False,
            },
        )
        assert rejected.status_code == 409

        lease = client.post(
            "/api/evidence-collection/arm",
            json={
                "browser_session_id": browser_session_id,
                "source_attestation_confirmed": True,
            },
        ).json()
        trigger_payload = {
            "lease_token": lease["lease_token"],
            "original_text": "Send teh report.",
            "task_context": "Synthetic project update",
            "curated_knowledge_enabled": True,
            "relevant_curated_knowledge": ["Teh → the", "Project Atlas"],
        }
        trigger = client.post("/api/evidence-collection/trigger", json=trigger_payload)

        assert trigger.status_code == 200
        assert provider_calls == []
        assert list((package / "observations").iterdir()) == []
        trigger_payload["task_context"] = "Later mutable context"
        trigger_payload["relevant_curated_knowledge"] = ["Later mutable profile"]

        confirmation = client.post(
            "/api/evidence-collection/confirm",
            json={
                "lease_token": lease["lease_token"],
                "observation_id": trigger.json()["observation_id"],
                "disposition": "edit_intended",
                "intended_text": "Send the report.",
            },
        )

    assert confirmation.status_code == 200
    assert confirmation.json()["prepared_text"] == "Send the report."
    assert provider_calls == [
        {
            "original_text": "Send teh report.",
            "task_context": "Synthetic project update",
            "profile": ("Teh → the", "Project Atlas"),
            "artifact_count": 1,
            "system_prompt": provider_calls[0]["system_prompt"],
        }
    ]
    assert "Send the report." not in str(provider_calls)
    artifacts = list((package / "observations").glob("*.json"))
    assert len(artifacts) == 1
    record = json.loads(artifacts[0].read_text())["record"]
    assert record["original"] == "Send teh report."
    assert record["intended"] == "Send the report."
    assert record["context"] == {"task_context": "Synthetic project update"}
    assert record["profile"] == {
        "enabled": True,
        "relevant_evidence": ["Teh → the", "Project Atlas"],
    }
    assert record["correction_contract_version"] == "smart-correction-v1"
    assert record["source_attestation_version"] == "voiceitt-source-attestation-v1"
    assert record["package_version"] == "evidence-package-v1"
    assert record["package_contract_version"] == "intended-meaning-evidence-collection-v1"
    assert set(record["prompt_contract"]) == {"version_id", "content_sha256"}
    assert record["triggered_at"].endswith("Z")
    assert record["confirmed_at"].endswith("Z")


def test_application_restart_discards_lease_and_receipt_and_requires_fresh_attestation(
    initialized_settings: Settings, tmp_path: Path
) -> None:
    _evaluation_directory, package = configured_package(tmp_path)
    settings = replace(initialized_settings, evidence_package_directory=package)
    browser_session_id = str(uuid4())

    with TestClient(create_app(settings)) as first_client:
        lease = first_client.post(
            "/api/evidence-collection/arm",
            json={
                "browser_session_id": browser_session_id,
                "source_attestation_confirmed": True,
            },
        ).json()["lease_token"]
        frozen = first_client.post(
            "/api/evidence-collection/trigger",
            json={
                "lease_token": lease,
                "original_text": "Synthetic source",
                "correction_mode": "smart",
            },
        ).json()
        receipt = first_client.post(
            "/api/evidence-collection/confirm",
            json={
                "lease_token": lease,
                "observation_id": frozen["observation_id"],
                "disposition": "not_voiceitt",
                "intended_text": None,
            },
        ).json()["evidence_receipt"]

    with TestClient(create_app(settings)) as restarted_client:
        stale_trigger = restarted_client.post(
            "/api/evidence-collection/trigger",
            json={
                "lease_token": lease,
                "original_text": "Synthetic source",
                "correction_mode": "smart",
            },
        )
        outgoing = {
            "cleanup_enabled": True,
            "original_text": "Synthetic source",
            "prepared_text": "",
            "outgoing_text": "Synthetic source",
            "outgoing_kind": "original",
            "status": "waiting",
            "correction_mode": "smart",
            "evidence_lease_token": lease,
            "evidence_receipt": receipt,
        }
        assert restarted_client.put("/api/outgoing-state", json=outgoing).status_code == 200
        stale_outgoing = restarted_client.get("/api/outgoing-state")
        unattested_arm = restarted_client.post(
            "/api/evidence-collection/arm",
            json={
                "browser_session_id": browser_session_id,
                "source_attestation_confirmed": False,
            },
        )
        fresh_arm = restarted_client.post(
            "/api/evidence-collection/arm",
            json={
                "browser_session_id": browser_session_id,
                "source_attestation_confirmed": True,
            },
        )
        outgoing["evidence_lease_token"] = fresh_arm.json()["lease_token"]
        restarted_client.put("/api/outgoing-state", json=outgoing)
        stale_receipt = restarted_client.get("/api/outgoing-state")

    assert stale_trigger.status_code == 409
    assert stale_outgoing.status_code == 409
    assert unattested_arm.status_code == 409
    assert unattested_arm.json()["detail"]["message"] == "fresh source attestation is required"
    assert fresh_arm.status_code == 200
    assert fresh_arm.json()["lease_token"] != lease
    assert stale_receipt.status_code == 409


def test_outgoing_state_requires_current_receipt_and_never_queues_delivery(
    initialized_settings: Settings, tmp_path: Path
) -> None:
    _evaluation_directory, package = configured_package(tmp_path)
    settings = replace(initialized_settings, evidence_package_directory=package)
    client = TestClient(create_app(settings))
    browser_session_id = str(uuid4())
    client.get("/api/config", headers={"X-Evidence-Browser-Session": browser_session_id})
    lease = client.post(
        "/api/evidence-collection/arm",
        json={
            "browser_session_id": browser_session_id,
            "source_attestation_confirmed": True,
        },
    ).json()
    outgoing = {
        "cleanup_enabled": True,
        "original_text": "Synthetic source",
        "prepared_text": "",
        "outgoing_text": "Synthetic source",
        "outgoing_kind": "original",
        "status": "waiting",
        "correction_mode": "smart",
        "evidence_lease_token": lease["lease_token"],
        "evidence_receipt": None,
    }
    assert client.put("/api/outgoing-state", json=outgoing).status_code == 200
    blocked = client.get("/api/outgoing-state")
    assert blocked.status_code == 409
    assert blocked.json() == {
        "detail": "Complete intended-meaning confirmation in Sayloom, then retry."
    }
    assert "Synthetic source" not in blocked.text
    assert client.post("/api/outgoing-delivery").status_code == 404

    frozen = client.post(
        "/api/evidence-collection/trigger",
        json={
            "lease_token": lease["lease_token"],
            "original_text": "Synthetic source",
            "correction_mode": "smart",
        },
    ).json()
    confirmed = client.post(
        "/api/evidence-collection/confirm",
        json={
            "lease_token": lease["lease_token"],
            "observation_id": frozen["observation_id"],
            "disposition": "not_voiceitt",
            "intended_text": None,
        },
    ).json()
    assert confirmed["artifact_type"] == "exclusion"
    outgoing["evidence_receipt"] = confirmed["evidence_receipt"]
    client.put("/api/outgoing-state", json=outgoing)
    released = client.get("/api/outgoing-state")
    assert released.status_code == 200
    assert released.json()["outgoing_text"] == "Synthetic source"

    client.get(
        "/api/config",
        headers={
            "X-Evidence-Browser-Session": str(uuid4()),
            "X-Evidence-Previous-Lease": lease["lease_token"],
        },
    )
    assert client.get("/api/outgoing-state").status_code == 409
    outgoing["evidence_lease_token"] = None
    outgoing["evidence_receipt"] = None
    client.put("/api/outgoing-state", json=outgoing)
    assert client.get("/api/outgoing-state").status_code == 200


def test_stale_config_reload_cannot_disarm_a_newer_browser_lease(
    initialized_settings: Settings, tmp_path: Path
) -> None:
    _evaluation_directory, package = configured_package(tmp_path)
    settings = replace(initialized_settings, evidence_package_directory=package)
    client = TestClient(create_app(settings))
    first_session = str(uuid4())
    first_lease = client.post(
        "/api/evidence-collection/arm",
        json={
            "browser_session_id": first_session,
            "source_attestation_confirmed": True,
        },
    ).json()["lease_token"]
    second_session = str(uuid4())
    second_lease = client.post(
        "/api/evidence-collection/arm",
        json={
            "browser_session_id": second_session,
            "source_attestation_confirmed": True,
        },
    ).json()["lease_token"]

    stale_reload = client.get(
        "/api/config",
        headers={
            "X-Evidence-Browser-Session": first_session,
            "X-Evidence-Previous-Lease": first_lease,
        },
    )
    trigger_response = client.post(
        "/api/evidence-collection/trigger",
        json={
            "lease_token": second_lease,
            "original_text": "Synthetic source",
            "correction_mode": "smart",
        },
    )

    assert stale_reload.status_code == 200
    assert trigger_response.status_code == 200


@pytest.mark.parametrize(
    ("default_mode", "action_selector", "disposition", "intended_text", "result_status"),
    [
        ("smart", "#run-cleanup", "edit_intended", "Send the report.", "prepared"),
        (
            "conservative",
            "#run-cleanup",
            "edit_intended",
            "Send the report.",
            "prepared",
        ),
        (
            "conservative",
            "#run-cleanup",
            "presentation_cleanup_needed",
            "STALE BROWSER VALUE",
            "provider_error",
        ),
        ("smart", "#run-cleanup", "ready_as_is", "STALE BROWSER VALUE", "prepared"),
        (
            "smart",
            "#run-cleanup",
            "presentation_cleanup_needed",
            "STALE BROWSER VALUE",
            "provider_error",
        ),
        ("smart", "#run-cleanup", "not_voiceitt", "STALE BROWSER VALUE", "prepared"),
        (
            "smart",
            "#run-cleanup",
            "cannot_reliably_reconstruct",
            "STALE BROWSER VALUE",
            "prepared",
        ),
        ("smart", "#run-cleanup", "exclude", "STALE BROWSER VALUE", "prepared"),
        ("smart", "#copy-outgoing", "edit_intended", "Send the report.", "prepared"),
    ],
)
def test_browser_armed_smart_conceals_candidate_until_confirmation(
    initialized_settings: Settings,
    default_mode: str,
    action_selector: str,
    disposition: str,
    intended_text: str,
    result_status: str,
) -> None:
    client = TestClient(create_app(initialized_settings))
    script = client.get("/static/app.js").text
    assert "/api/outgoing-delivery" not in script
    assert "scheduleDeliveryPoll" not in script
    harness = r"""
const vm = require("vm");
class Element {
  constructor() {
    this.value = ""; this.checked = false; this.disabled = false; this.hidden = false;
    this.readOnly = false; this.open = false; this.dataset = {}; this.listeners = {};
    this.options = [{ textContent: "" }]; this.children = []; this.attributes = {};
    this.textContent = ""; this.lastElementChild = { textContent: "" };
    this.style = { setProperty() {} };
    this.classList = { add() {}, remove() {}, toggle() {}, contains() { return false; } };
  }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  async dispatch(type, event = {}) {
    event.target ||= this; event.preventDefault ||= () => {};
    for (const callback of this.listeners[type] || []) await callback(event);
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || (name === "aria-valuenow" ? "55" : null); }
  removeAttribute(name) { delete this.attributes[name]; }
  append(...children) { this.children.push(...children); }
  setPointerCapture() {}
  setSelectionRange() {}
  getBoundingClientRect() { return { top: 0, left: 0, width: 100, height: 100 }; }
  focus() { document.activeElement = this; }
  select() {}
  showModal() { this.open = true; }
  close() { this.open = false; }
  reportValidity() { return true; }
  toggleAttribute() {}
  querySelectorAll() { return []; }
  querySelector() { return null; }
}
const elements = {};
const document = {
  activeElement: null,
  querySelector(selector) { return elements[selector] ||= new Element(); },
  createElement() { return new Element(); },
  addEventListener() {},
};
const requests = [];
const copied = [];
const routineLogs = [];
let confirmationReceipt = false;
let outgoingReads = 0;
let copyConflictReturned = false;
const response = (body, status = 200) => ({
  ok: status >= 200 && status < 300, status, json: async () => body,
});
const fetch = async (url, options = {}) => {
  const body = options.body ? JSON.parse(options.body) : null;
  requests.push({ url, method: options.method || "GET", body });
  if (url === "/api/config") return response({
    preparation_default: process.argv[2],
    cleanup_configuration: { status: "unavailable", routes: [], disclosure: {} },
    evidence_collection: { ready: true }, evaluation_configuration: { available: true },
  });
  if (url === "/api/outgoing-state") {
    if (options.method === "PUT") return response({ revision: 1 });
    outgoingReads += 1;
    if (
      process.argv[3] === "#copy-outgoing"
      && confirmationReceipt
      && !copyConflictReturned
    ) {
      copyConflictReturned = true;
      return response({
        detail: "Complete intended-meaning confirmation in Sayloom, then retry.",
      }, 409);
    }
    return response({ revision: 1, outgoing_text: "Send the report." });
  }
  if (url === "/api/evidence-collection/arm") return response({ lease_token: "lease-1" });
  if (url === "/api/evidence-collection/trigger") {
    return response({ observation_id: "observation-1" });
  }
  if (url === "/api/evidence-collection/confirm") {
    const exclusion = ["not_voiceitt", "cannot_reliably_reconstruct", "exclude"]
      .includes(body.disposition);
    if (
      body.disposition !== "edit_intended"
      && !exclusion
      && body.intended_text !== "Send teh report."
    ) {
      return response({ detail: {
        code: "invalid_evidence_request",
        message: "The request did not match the evidence collection contract.",
        retry_action: "Review the current form values and retry.",
      } }, 422);
    }
    if (process.argv[6] === "provider_error") return response({
      prepared_text: "Send teh report.", status: "provider_error", lexical_repairs: [],
      provider: "synthetic", model: "synthetic-model", attempts: [],
      evidence_receipt: "receipt-1", observation_id: "observation-1",
      artifact_type: "eligible_observation", exact_repeat_suggestions: [],
      error: { code: "cleanup_provider_error", message: "Smart cleanup failed.",
        retry_action: "Retry Smart cleanup or continue with Original." },
    });
    confirmationReceipt = true;
    return response({
      evidence_receipt: "receipt-1", observation_id: "observation-1",
      artifact_type: ["not_voiceitt", "cannot_reliably_reconstruct", "exclude"]
        .includes(body.disposition) ? "exclusion" : "eligible_observation",
      exact_repeat_suggestions: [],
      prepared_text: "Send the report.", status: "prepared", lexical_repairs: [{
        operation: "replacement", original_span: { start: 5, end: 8, text: "teh" },
        prepared_span: { start: 5, end: 8, text: "the" }, context: "Send the report.",
        queue_position: 1, inspection_reason: "Prepared replaces wording; verify meaning.",
      }],
    });
  }
  if (url === "/api/cleanup" && body.correction_mode === "conservative") {
    return response({
      prepared_text: body.original_text, status: "unchanged",
      provider: "synthetic", model: "synthetic-model",
      attempts: [{
        provider: "synthetic", model: "synthetic-model", route_index: 0, outcome: "success",
      }],
      evaluation: {
        capture_proof: "synthetic-proof", completed_at: "2026-01-01T00:00:00Z",
        prompt_version_id: 1, prompt_content_sha256: "synthetic-prompt-hash",
        cleanup_schema_version: "synthetic-cleanup-schema",
      },
    });
  }
  if (url === "/api/cleanup") throw new Error("Smart candidate requested before confirmation");
  throw new Error(`Unexpected request: ${url}`);
};
const window = {
  clearTimeout,
  setTimeout(callback, delay) {
    const timer = setTimeout(callback, delay); timer.unref(); return timer;
  },
  requestAnimationFrame(callback) { callback(); }, addEventListener() {},
  matchMedia() { return { matches: false, addEventListener() {} }; },
};
const context = {
  document, window, fetch, AbortController, Promise,
  console: {
    log(...values) { routineLogs.push(values.join(" ")); },
    warn(...values) { routineLogs.push(values.join(" ")); },
    error(...values) { routineLogs.push(values.join(" ")); },
  },
  navigator: { clipboard: { async writeText(value) { copied.push(value); } } },
};
const settle = async () => {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
};
(async () => {
  vm.runInNewContext(process.argv[1], context); await settle();
  let ordinaryEvaluationEnabled = false;
  if (process.argv[2] === "conservative") {
    elements["#original-text"].value = "Ordinary synthetic source.";
    await elements["#original-text"].dispatch("input", { isTrusted: true });
    await elements["#run-cleanup"].dispatch("click"); await settle();
    ordinaryEvaluationEnabled = !elements["#save-evaluation-case"].disabled;
  }
  await elements["#evidence-collection-toggle"].dispatch("click");
  elements["#evidence-source-attestation"].checked = true;
  await elements["#evidence-attestation-form"].dispatch("submit"); await settle();
  const armedEvaluationDisabled = elements["#save-evaluation-case"].disabled;
  const evidenceRequestStart = requests.length;
  elements["#original-text"].value = "Send teh report.";
  await elements["#original-text"].dispatch("input", { isTrusted: true });
  if (process.argv[2] === "smart") {
    elements["#smart-task-context"].value = "Synthetic project update";
  } else {
    elements["#smart-task-context"].value = "Stale hidden Smart context";
  }
  elements["#prepared-text"].value = "STALE PREPARED";
  await elements[process.argv[3]].dispatch("click"); await settle();
  const before = {
    prepared: elements["#prepared-text"].value,
    dialogOpen: elements["#evidence-judgment-dialog"].open,
    preparedSelectionDisabled: elements["#select-prepared"].disabled,
    candidateRequests: requests.slice(evidenceRequestStart).filter(
      (item) => (item.url === "/api/cleanup" && item.body.correction_mode === "smart")
        || item.url.endsWith("/confirm"),
    ).length,
  };
  const disposition = process.argv[4];
  const dispositionSelect = elements["#evidence-disposition"];
  dispositionSelect.name = "evidence-disposition";
  dispositionSelect.value = disposition;
  await elements["#evidence-judgment-form"].dispatch("change", { target: dispositionSelect });
  elements["#evidence-intended-text"].value = process.argv[5];
  await elements["#evidence-judgment-form"].dispatch("submit"); await settle();
  let copyConflict = null;
  if (process.argv[3] === "#copy-outgoing") {
    await elements["#copy-outgoing"].dispatch("click"); await settle();
    copyConflict = {
      copied: [...copied],
      message: elements["#copy-outgoing-state"].textContent,
      outgoingReads,
    };
    await elements["#copy-outgoing"].dispatch("click"); await settle();
  }
  process.stdout.write(JSON.stringify({
    before,
    ordinaryEvaluationEnabled,
    armedEvaluationDisabled,
    copyConflict,
    dialogOpenAfter: elements["#evidence-judgment-dialog"].open,
    armedLabel: elements["#evidence-collection-state"].textContent,
    prepared: elements["#prepared-text"].value,
    status: elements["#outgoing-kind"].dataset.state,
    repairCount: elements["#prepared-text"].dataset.repairCount,
    copied,
    outgoingReads,
    routineLogs,
    requests: requests.filter((item) => item.url.startsWith("/api/evidence-collection")),
  }));
})().catch((error) => { process.stderr.write(error.stack); process.exit(1); });
"""
    result = subprocess.run(
        [
            "node",
            "-e",
            harness,
            script,
            default_mode,
            action_selector,
            disposition,
            intended_text,
            result_status,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)

    assert observed["before"] == {
        "prepared": "",
        "dialogOpen": True,
        "preparedSelectionDisabled": True,
        "candidateRequests": 0,
    }
    assert observed["ordinaryEvaluationEnabled"] is (default_mode == "conservative")
    assert observed["armedEvaluationDisabled"] is True
    assert observed["dialogOpenAfter"] is False
    assert observed["armedLabel"] == "Armed · Voiceitt source attested for this session"
    if result_status == "prepared":
        assert observed["prepared"] == "Send the report."
        if default_mode == "smart":
            assert observed["repairCount"] == "1"
    elif result_status == "provider_error":
        assert observed["prepared"] == "Send teh report."
        assert observed["status"] == "error"
    else:
        assert observed["prepared"] == ""
        assert observed["status"] == "waiting"
    assert observed["copied"] == (
        ["Send the report."] if action_selector == "#copy-outgoing" else []
    )
    if action_selector == "#copy-outgoing":
        assert observed["copyConflict"] == {
            "copied": [],
            "message": "Complete intended-meaning confirmation in Sayloom, then retry.",
            "outgoingReads": 2,
        }
        assert observed["outgoingReads"] == 3
        assert "Send teh report." not in observed["copyConflict"]["message"]
    else:
        assert observed["copyConflict"] is None
        assert observed["outgoingReads"] == 1
    assert observed["routineLogs"] == []
    expected_evidence_requests = [
        "/api/evidence-collection/arm",
        "/api/evidence-collection/cancel",
        "/api/evidence-collection/trigger",
    ]
    expected_evidence_requests.append("/api/evidence-collection/confirm")
    assert [request["url"] for request in observed["requests"]] == expected_evidence_requests
    trigger = observed["requests"][2]
    assert trigger["body"] == {
        "lease_token": "lease-1",
        "original_text": "Send teh report.",
        "task_context": "Synthetic project update" if default_mode == "smart" else None,
        "correction_mode": default_mode,
    }
    confirmation = observed["requests"][3]
    expected_intended = (
        None
        if disposition in {"not_voiceitt", "cannot_reliably_reconstruct", "exclude"}
        else "Send the report."
        if disposition == "edit_intended"
        else "Send teh report."
    )
    assert confirmation["body"]["intended_text"] == expected_intended
    assert "intended_text" not in trigger["body"]


def test_browser_collection_failure_requires_explicit_recovery_choice(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))
    script = client.get("/static/app.js").text
    page = client.get("/").text
    assert ">Retry collection<" in page
    assert ">Use without collecting<" in page
    assert ">Cancel<" in page
    harness = r"""
const vm = require("vm");
class Element {
  constructor() {
    this.value = ""; this.checked = false; this.disabled = false; this.hidden = false;
    this.readOnly = false; this.required = false; this.open = false; this.dataset = {};
    this.listeners = {}; this.options = [{ textContent: "" }]; this.children = [];
    this.attributes = {}; this.textContent = ""; this.lastElementChild = { textContent: "" };
    this.style = { setProperty() {} };
    this.classList = { add() {}, remove() {}, toggle() {}, contains() { return false; } };
  }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  async dispatch(type, event = {}) {
    event.target ||= this; event.preventDefault ||= () => {};
    for (const callback of this.listeners[type] || []) await callback(event);
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || (name === "aria-valuenow" ? "55" : null); }
  removeAttribute(name) { delete this.attributes[name]; }
  append(...children) { this.children.push(...children); }
  setPointerCapture() {}
  setSelectionRange() {}
  getBoundingClientRect() { return { top: 0, left: 0, width: 100, height: 100 }; }
  focus() { document.activeElement = this; }
  select() {}
  showModal() { this.open = true; }
  close() { this.open = false; }
  reportValidity() { return true; }
  toggleAttribute() {}
  querySelectorAll() { return []; }
  querySelector() { return null; }
}
const elements = {};
const document = {
  activeElement: null,
  querySelector(selector) { return elements[selector] ||= new Element(); },
  createElement() { return new Element(); },
  addEventListener() {},
};
const requests = [];
const response = (body, status = 200) => ({
  ok: status >= 200 && status < 300, status, json: async () => body,
});
const fetch = async (url, options = {}) => {
  const body = options.body ? JSON.parse(options.body) : null;
  requests.push({ url, method: options.method || "GET", body });
  if (url === "/api/config") return response({
    preparation_default: "smart",
    cleanup_configuration: { status: "unavailable", routes: [], disclosure: {} },
    evidence_collection: { ready: true }, evaluation_configuration: { available: false },
  });
  if (url === "/api/outgoing-state") return response({ revision: requests.length });
  if (url === "/api/evidence-collection/arm") return response({ lease_token: "lease-1" });
  if (url === "/api/evidence-collection/trigger") {
    return response({ observation_id: "observation-1" });
  }
  if (url === "/api/evidence-collection/confirm") return response({ detail: {
    code: "evidence_collection_unavailable",
    message: "observation storage verification failed",
    retry_action: "Stop collection, verify readiness, then attest and arm again.",
  } }, 409);
  if (url.startsWith("/api/evidence-collection/arm?")) return response({}, 204);
  if (url === "/api/cleanup") return response({
    prepared_text: "Send the report.", status: "prepared", lexical_repairs: [{
      operation: "replacement", original_span: { start: 5, end: 8, text: "teh" },
      prepared_span: { start: 5, end: 8, text: "the" }, context: "Send the report.",
      queue_position: 1, inspection_reason: "Prepared replaces wording; verify meaning.",
    }],
  });
  throw new Error(`Unexpected request: ${url}`);
};
const timer = { unref() {} };
const window = {
  clearTimeout() {}, setTimeout() { return timer; },
  requestAnimationFrame(callback) { callback(); },
  addEventListener() {}, matchMedia() { return { matches: false, addEventListener() {} }; },
};
const context = { document, window, fetch, AbortController, Promise, console, navigator: {} };
const settle = async () => {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
};
(async () => {
  vm.runInNewContext(process.argv[1], context); await settle();
  elements["#original-text"].value = "Send teh report.";
  await elements["#original-text"].dispatch("input", { isTrusted: true });
  await elements["#evidence-collection-toggle"].dispatch("click");
  elements["#evidence-source-attestation"].checked = true;
  await elements["#evidence-attestation-form"].dispatch("submit"); await settle();
  await elements["#run-cleanup"].dispatch("click"); await settle();
  const dispositionSelect = elements["#evidence-disposition"];
  dispositionSelect.name = "evidence-disposition";
  dispositionSelect.value = "edit_intended";
  await elements["#evidence-judgment-form"].dispatch("change", { target: dispositionSelect });
  elements["#evidence-intended-text"].value = "Send the report.";
  await elements["#evidence-judgment-form"].dispatch("submit"); await settle();
  const failed = {
    dialogOpen: elements["#evidence-failure-dialog"].open,
    prepared: elements["#prepared-text"].value,
    message: elements["#evidence-failure-message"].textContent,
    cleanupRequests: requests.filter((item) => item.url === "/api/cleanup").length,
  };
  await elements["#continue-without-evidence"].dispatch("click"); await settle();
  process.stdout.write(JSON.stringify({
    failed,
    recovered: {
      dialogOpen: elements["#evidence-failure-dialog"].open,
      prepared: elements["#prepared-text"].value,
      cleanupRequests: requests.filter((item) => item.url === "/api/cleanup").length,
    },
  }));
})().catch((error) => { process.stderr.write(error.stack); process.exit(1); });
"""
    result = subprocess.run(
        ["node", "-e", harness, script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["failed"] == {
        "dialogOpen": True,
        "prepared": "",
        "message": (
            "observation storage verification failed Stop collection, verify readiness, "
            "then attest and arm again."
        ),
        "cleanupRequests": 0,
    }
    assert observed["recovered"] == {
        "dialogOpen": False,
        "prepared": "Send the report.",
        "cleanupRequests": 1,
    }
