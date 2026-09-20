import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from local_text.app import create_app
from local_text.cleanup import CleanupService, ProviderOutput
from local_text.config import Settings
from local_text.evidence_package import approve_package, create_package


def configured_package(tmp_path: Path) -> tuple[Path, Path]:
    evaluation_directory = tmp_path / "evaluation"
    evaluation_directory.mkdir(mode=0o700)
    package = evaluation_directory / "intended-meaning-evidence"
    creation = create_package(package)
    approve_package(package, creation.approval_digest)
    return evaluation_directory, package


def test_confirmed_observation_is_verified_before_smart_receives_only_frozen_input(
    initialized_settings: Settings, tmp_path: Path
) -> None:
    evaluation_directory, package = configured_package(tmp_path)
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

    settings = replace(initialized_settings, evaluation_data_directory=evaluation_directory)
    service = CleanupService(provider=Provider(), model=Provider.model, timeout_seconds=1)
    with TestClient(create_app(settings, service)) as client:
        readiness = client.get("/api/config").json()["evidence_collection"]
        assert readiness["ready"] is True

        rejected = client.post(
            "/api/evidence-collection/arm",
            json={"source_attestation_confirmed": False},
        )
        assert rejected.status_code == 409

        lease = client.post(
            "/api/evidence-collection/arm",
            json={"source_attestation_confirmed": True},
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


@pytest.mark.parametrize(
    ("default_mode", "action_selector", "disposition", "intended_text", "result_status"),
    [
        ("smart", "#run-cleanup", "edit_intended", "Send the report.", "prepared"),
        (
            "conservative",
            "#run-smart-correction",
            "edit_intended",
            "Send the report.",
            "prepared",
        ),
        ("smart", "#run-cleanup", "ready_as_is", "STALE BROWSER VALUE", "prepared"),
        (
            "smart",
            "#run-cleanup",
            "presentation_cleanup_needed",
            "STALE BROWSER VALUE",
            "provider_error",
        ),
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
    script = TestClient(create_app(initialized_settings)).get("/static/app.js").text
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
  querySelectorAll(selector) { return selector.includes("evidence-disposition") ? radios : []; }
  querySelector(selector) {
    return selector.includes("evidence-disposition")
      ? radios.find((item) => item.checked) : null;
  }
}
const elements = {};
const radios = ["ready_as_is", "presentation_cleanup_needed", "edit_intended"].map((value) => {
  const radio = new Element();
  radio.name = "evidence-disposition"; radio.value = value;
  return radio;
});
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
    cleanup_enabled_by_default: true, default_correction_mode: process.argv[2],
    cleanup_configuration: { status: "unavailable", routes: [], disclosure: {} },
    evidence_collection: { ready: true }, evaluation_configuration: { available: false },
  });
  if (url === "/api/outgoing-state") return response({ revision: 1 });
  if (url === "/api/evidence-collection/arm") return response({ lease_token: "lease-1" });
  if (url === "/api/evidence-collection/trigger") {
    return response({ observation_id: "observation-1" });
  }
  if (url === "/api/evidence-collection/confirm") {
    if (body.disposition !== "edit_intended" && body.intended_text !== "Send teh report.") {
      return response({ detail: {
        code: "invalid_evidence_request",
        message: "The request did not match the evidence collection contract.",
        retry_action: "Review the current form values and retry.",
      } }, 422);
    }
    if (process.argv[6] === "provider_error") return response({
      prepared_text: "Send teh report.", status: "provider_error", lexical_repairs: [],
      provider: "synthetic", model: "synthetic-model", attempts: [],
      error: { code: "cleanup_provider_error", message: "Smart cleanup failed.",
        retry_action: "Retry Smart cleanup or continue with Original." },
    });
    return response({
      prepared_text: "Send the report.", status: "prepared", lexical_repairs: [{
        operation: "replacement", original_span: { start: 5, end: 8, text: "teh" },
        prepared_span: { start: 5, end: 8, text: "the" }, context: "Send the report.",
        queue_position: 1, inspection_reason: "Prepared replaces wording; verify meaning.",
      }],
    });
  }
  if (url === "/api/cleanup" && body.correction_mode === "conservative") {
    return response({ prepared_text: body.original_text, status: "unchanged" });
  }
  if (url === "/api/cleanup") throw new Error("Smart candidate requested before confirmation");
  throw new Error(`Unexpected request: ${url}`);
};
const window = {
  clearTimeout, setTimeout, requestAnimationFrame(callback) { callback(); }, addEventListener() {},
  matchMedia() { return { matches: false, addEventListener() {} }; },
};
const context = {
  document, window, fetch, AbortController, Promise, console,
  navigator: { clipboard: {} },
};
const settle = async () => {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
};
(async () => {
  vm.runInNewContext(process.argv[1], context); await settle();
  elements["#original-text"].value = "Send teh report.";
  await elements["#original-text"].dispatch("input", { isTrusted: true });
  elements["#smart-task-context"].value = "Synthetic project update";
  if (process.argv[2] === "conservative") {
    await elements["#run-cleanup"].dispatch("click"); await settle();
  }
  await elements["#evidence-collection-toggle"].dispatch("click");
  elements["#evidence-source-attestation"].checked = true;
  await elements["#evidence-attestation-form"].dispatch("submit"); await settle();
  elements["#prepared-text"].value = "STALE PREPARED";
  await elements[process.argv[3]].dispatch("click"); await settle();
  const before = {
    prepared: elements["#prepared-text"].value,
    dialogOpen: elements["#evidence-judgment-dialog"].open,
    preparedSelectionDisabled: elements["#select-prepared"].disabled,
    candidateRequests: requests.filter(
      (item) => (item.url === "/api/cleanup" && item.body.correction_mode === "smart")
        || item.url.endsWith("/confirm"),
    ).length,
  };
  const disposition = process.argv[4];
  const selectedRadio = radios.find((radio) => radio.value === disposition);
  selectedRadio.checked = true;
  await elements["#evidence-judgment-form"].dispatch("change", { target: selectedRadio });
  elements["#evidence-intended-text"].value = process.argv[5];
  await elements["#evidence-judgment-form"].dispatch("submit"); await settle();
  process.stdout.write(JSON.stringify({
    before,
    dialogOpenAfter: elements["#evidence-judgment-dialog"].open,
    armedLabel: elements["#evidence-collection-state"].textContent,
    prepared: elements["#prepared-text"].value,
    status: elements["#cleanup-status"].dataset.state,
    repairCount: elements["#prepared-text"].dataset.repairCount,
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
    assert observed["dialogOpenAfter"] is False
    assert observed["armedLabel"] == "Armed · Voiceitt source attested for this session"
    if result_status == "prepared":
        assert observed["prepared"] == "Send the report."
        assert observed["repairCount"] == "1"
    else:
        assert observed["prepared"] == "Send teh report."
        assert observed["status"] == "error"
    assert [request["url"] for request in observed["requests"]] == [
        "/api/evidence-collection/arm",
        "/api/evidence-collection/trigger",
        "/api/evidence-collection/confirm",
    ]
    trigger, confirmation = observed["requests"][1:]
    assert trigger["body"] == {
        "lease_token": "lease-1",
        "original_text": "Send teh report.",
        "task_context": "Synthetic project update",
    }
    expected_intended = "Send the report." if disposition == "edit_intended" else "Send teh report."
    assert confirmation["body"]["intended_text"] == expected_intended
    assert "intended_text" not in trigger["body"]
