import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from local_text.app import create_app
from local_text.cleanup import OPENAI_GPT_56_LUNA, CleanupService, OpenAIAdapter, ProviderOutput
from local_text.database import ApplicationDatabase
from local_text.personal_corrections import PersonalCorrectionStore


def approve_synthetic_mapping(
    store: PersonalCorrectionStore,
    *,
    observed: str = "umber",
    intended: str = "Amber",
    context: str | None = "Synthetic parcel color",
) -> None:
    store.approve_replacement(
        approval_id=str(uuid4()),
        observed_text=observed,
        intended_text=intended,
        observed_sentence="Send the umber parcel.",
        intended_sentence="Send the Amber parcel.",
        applicability_context=context,
        source_mode="smart",
        prompt_version_id=1,
        correction_contract_version="personal-correction-v1",
    )


def event_types(path: Path) -> list[str]:
    with sqlite3.connect(path) as connection:
        return [
            row[0]
            for row in connection.execute(
                "SELECT event_type FROM personal_correction_events ORDER BY id"
            )
        ]


def test_store_retrieves_exact_normalized_alias_at_lexical_boundary_and_records_supply(
    initialized_settings,
) -> None:
    path = Path(initialized_settings.database_path)
    store = PersonalCorrectionStore(ApplicationDatabase(path))
    approve_synthetic_mapping(store, observed="  UMBER ")

    retrieval = store.retrieve_for_smart("Use\u00a0umber, then umber again.")

    assert [match.evidence for match in retrieval.matches] == [
        {
            "matched_alias": "  UMBER ",
            "intended_term": "Amber",
            "applicability_context": "Synthetic parcel color",
        }
    ]
    assert len(retrieval.matches[0].occurrences) == 2
    assert event_types(path) == [
        "alias_observed",
        "alias_observed",
        "profile_supplied",
    ]


def test_store_excludes_lexical_nonmatches_and_disabled_profile_or_entry(
    initialized_settings,
) -> None:
    path = Path(initialized_settings.database_path)
    store = PersonalCorrectionStore(ApplicationDatabase(path))
    approve_synthetic_mapping(store)

    assert store.retrieve_for_smart("The cucumber is synthetic.").matches == ()
    entry = store.read().entries[0]
    store.update_entry(
        entry.id,
        expected_revision=entry.revision,
        intended_term=entry.intended_term,
        aliases=tuple(alias.observed_alias for alias in entry.aliases),
        applicability_context=entry.applicability_context,
        enabled=False,
    )
    assert store.retrieve_for_smart("Use umber here.").matches == ()
    store.set_profile_enabled(False)
    assert store.retrieve_for_smart("Use umber here.").matches == ()
    assert event_types(path) == []


def test_supply_event_failure_rolls_back_the_whole_retrieval(
    initialized_settings,
) -> None:
    path = Path(initialized_settings.database_path)
    database = ApplicationDatabase(path)
    store = PersonalCorrectionStore(database)
    approve_synthetic_mapping(store)

    def fail_supply(_connection, _cursor, statement, parameters, _context, _many):
        if (
            statement.lstrip().upper().startswith("INSERT INTO PERSONAL_CORRECTION_EVENTS")
            and "profile_supplied" in parameters
        ):
            raise RuntimeError("synthetic supply event failure")

    event.listen(database.engine, "before_cursor_execute", fail_supply)
    try:
        with pytest.raises(RuntimeError, match="synthetic supply event failure"):
            store.retrieve_for_smart("Use umber here.")
    finally:
        event.remove(database.engine, "before_cursor_execute", fail_supply)

    assert event_types(path) == ["alias_observed"]


def test_store_records_intended_produced_only_for_overlapping_reviewable_replacement(
    initialized_settings,
) -> None:
    path = Path(initialized_settings.database_path)
    store = PersonalCorrectionStore(ApplicationDatabase(path))
    approve_synthetic_mapping(store)
    original = "Send the umber parcel. Amber appears elsewhere."
    retrieval = store.retrieve_for_smart(original)
    unrelated = SimpleNamespace(
        operation="replacement",
        original_span=SimpleNamespace(start=31, end=36),
        prepared_span=SimpleNamespace(text="Amber"),
    )
    matching = SimpleNamespace(
        operation="replacement",
        original_span=SimpleNamespace(start=9, end=14),
        prepared_span=SimpleNamespace(text="Amber"),
    )

    store.record_intended_produced(retrieval, [unrelated])
    assert event_types(path)[-1] == "profile_supplied"
    store.record_intended_produced(retrieval, [matching])
    assert event_types(path)[-1] == "intended_produced"


def test_smart_api_supplies_minimized_evidence_and_returns_reviewable_exact_correction(
    initialized_settings,
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {"prepared_text": "Send the Amber parcel."}
                                ),
                            }
                        ],
                    }
                ],
            },
        )

    async_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    service = CleanupService(
        OpenAIAdapter("synthetic-key", async_client),
        OPENAI_GPT_56_LUNA,
        timeout_seconds=1,
    )
    client = TestClient(create_app(initialized_settings, service))
    prompt_id = client.get("/api/config").json()["active_prompt_version_id"]
    approval = {
        "approval_id": str(uuid4()),
        "source_mode": "smart",
        "prompt_version_id": prompt_id,
        "correction_contract_version": "personal-correction-v1",
        "observed_sentence": "Private excluded observed sentence.",
        "intended_sentence": "Private excluded intended sentence.",
        "applicability_context": "Synthetic parcel color",
        "mapping": {
            "operation": "replacement",
            "observed_text": "umber",
            "intended_text": "Amber",
        },
    }
    assert client.post("/api/personal-corrections/episodes", json=approval).status_code == 201

    response = client.post(
        "/api/cleanup",
        json={"original_text": "Send the umber parcel.", "correction_mode": "smart"},
    )

    assert response.status_code == 200
    assert response.json()["prepared_text"] == "Send the Amber parcel."
    assert response.json()["lexical_repairs"][0]["operation"] == "replacement"
    request_body = json.loads(requests[0].content)
    evidence_frame = request_body["input"][1]["content"]
    assert evidence_frame == (
        '<REQUEST_EVIDENCE>\n{"original_text":"Send the umber parcel.",'
        '"task_context":"","relevant_curated_knowledge":[],"personal_corrections":'
        '[{"matched_alias":"umber","intended_term":"Amber",'
        '"applicability_context":"Synthetic parcel color"}]}\n</REQUEST_EVIDENCE>'
    )
    assert "Private excluded" not in evidence_frame
    assert "approval_id" not in evidence_frame
    assert "entry_id" not in evidence_frame
    assert event_types(Path(initialized_settings.database_path)) == [
        "alias_observed",
        "alias_observed",
        "profile_supplied",
        "intended_produced",
    ]


def test_profile_retrieval_failure_fails_open_without_private_diagnostics(
    initialized_settings, monkeypatch, caplog
) -> None:
    private_original = "Private synthetic umber sentence."
    calls: list[dict[str, object]] = []

    class Provider:
        provider_id = "gemini"
        model = "test-model"

        async def clean(self, original_text, system_prompt, **kwargs):
            calls.append(kwargs)
            return ProviderOutput(original_text, self.provider_id, self.model, 1)

    def fail_retrieval(self, original_text):
        raise RuntimeError("private profile failure detail")

    monkeypatch.setattr(PersonalCorrectionStore, "retrieve_for_smart", fail_retrieval)
    client = TestClient(
        create_app(initialized_settings, CleanupService(Provider(), "test-model", 1))
    )

    response = client.post(
        "/api/cleanup",
        json={"original_text": private_original, "correction_mode": "smart"},
    )

    assert response.status_code == 200
    assert response.json()["prepared_text"] == private_original
    assert calls == [{}]
    assert private_original not in caplog.text
    assert "private profile failure detail" not in caplog.text


def test_produced_event_failure_preserves_reviewable_smart_result(
    initialized_settings, monkeypatch, caplog
) -> None:
    store = PersonalCorrectionStore(
        ApplicationDatabase(Path(initialized_settings.database_path))
    )
    approve_synthetic_mapping(store)

    class Provider:
        provider_id = "gemini"
        model = "test-model"

        async def clean(self, original_text, system_prompt, **kwargs):
            return ProviderOutput(
                "Send the Amber parcel.", self.provider_id, self.model, 1
            )

    def fail_event(self, retrieval, repairs):
        raise RuntimeError("private post-result failure detail")

    monkeypatch.setattr(PersonalCorrectionStore, "record_intended_produced", fail_event)
    response = TestClient(
        create_app(initialized_settings, CleanupService(Provider(), "test-model", 1))
    ).post(
        "/api/cleanup",
        json={"original_text": "Send the umber parcel.", "correction_mode": "smart"},
    )

    assert response.status_code == 200
    assert response.json()["prepared_text"] == "Send the Amber parcel."
    assert response.json()["lexical_repairs"][0]["operation"] == "replacement"
    assert "private post-result failure detail" not in caplog.text


def test_conservative_never_reads_or_supplies_personal_corrections(
    initialized_settings, monkeypatch
) -> None:
    calls: list[dict[str, object]] = []

    class Provider:
        provider_id = "gemini"
        model = "test-model"

        async def clean(self, original_text, system_prompt, **kwargs):
            calls.append(kwargs)
            return ProviderOutput(original_text, self.provider_id, self.model, 1)

    def unexpected_retrieval(self, original_text):
        raise AssertionError("Conservative must not read Personal corrections")

    monkeypatch.setattr(PersonalCorrectionStore, "retrieve_for_smart", unexpected_retrieval)
    response = TestClient(
        create_app(initialized_settings, CleanupService(Provider(), "test-model", 1))
    ).post("/api/cleanup", json={"original_text": "Synthetic conservative source."})

    assert response.status_code == 200
    assert calls == [{}]
    assert "lexical_repairs" not in response.json()


def test_cleanup_api_rejects_caller_supplied_profile_rows_without_reflection(
    initialized_settings,
) -> None:
    submitted = "private caller-supplied intended term"
    response = TestClient(create_app(initialized_settings)).post(
        "/api/cleanup",
        json={
            "original_text": "Synthetic source.",
            "correction_mode": "smart",
            "personal_corrections": [{"intended_term": submitted}],
            "owner_id": "foreign",
        },
    )

    assert response.status_code == 422
    assert submitted not in response.text
