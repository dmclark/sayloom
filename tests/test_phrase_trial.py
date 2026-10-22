"""Provider-free checks at the trial's HTTP and private-record boundaries."""

import asyncio
import json
import time
from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from local_text.app import create_app
from local_text.phrase_trial import trial_router


def test_opt_in_activation_and_withdrawal(initialized_settings, tmp_path):
    settings = replace(initialized_settings, trial_directory=tmp_path / "trial")
    with TestClient(create_app(settings)) as client:
        state = client.get("/api/trial").json()
        assert state["status"] == "not_started"
        assert state["include"] is False
        assert (
            client.post("/api/trial/passages", json={"text": "Synthetic passage"}).status_code
            == 409
        )
        client.post("/api/trial/control", json={"action": "start"}).raise_for_status()
        client.put("/api/trial/preference", json={"include": True}).raise_for_status()
        passage = client.post("/api/trial/passages", json={"text": "Synthetic passage"}).json()
        assert passage["input"] == passage["final_text"] == "Synthetic passage"
        assert passage["assignment"] in {"manual", "alternatives"}
        assert passage["feedback"]["spoken"] == "unconfirmed"
        client.delete(f"/api/trial/passages/{passage['id']}").raise_for_status()
        assert client.get(f"/api/trial/passages/{passage['id']}").status_code == 404
        state = client.get("/api/trial").json()
        assert state["withdrawals"] == 1
        assert state["include"] is True
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/trial").json()["include"] is True


def fixture_app(root, handler):
    app = FastAPI()
    app.include_router(trial_router(root, "synthetic-credential", httpx.MockTransport(handler)))
    return app


def begin(client, text="🧵 pole request then pole request"):
    client.post("/api/trial/control", json={"action": "start"}).raise_for_status()
    client.put("/api/trial/preference", json={"include": True}).raise_for_status()
    return client.post("/api/trial/passages", json={"text": text}).json()["id"]


def provider_response(suggestions):
    return httpx.Response(
        200,
        json={
            "model": "gpt-6-luna",
            "status": "completed",
            "service_tier": "default",
            "usage": {"input_tokens": 700, "output_tokens": 120},
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": json.dumps({"suggestions": suggestions})}
                    ],
                }
            ],
        },
    )


def test_occurrence_only_one_request_and_provider_neutral_steps(tmp_path):
    def provider(request):
        body = json.loads(request.content)
        assert body["input"][1] == {"role": "user", "content": "🧵 pole request then pole request"}
        assert body["store"] is False and body["tools"] == []
        return provider_response(
            [{"phrase": "pole request", "occurrence": 2, "alternatives": ["pull request"]}]
        )

    with TestClient(fixture_app(tmp_path, provider)) as client:
        passage_id = begin(client)
        path = f"/api/trial/passages/{passage_id}"
        result = client.post(path + "/alternatives").json()
        assert result["final_text"] == "🧵 pole request then pole request"
        assert result["suggestions"] == [
            {
                "phrase": "pole request",
                "occurrence": 2,
                "alternatives": ["pull request"],
                "start": 21,
                "end": 33,
            }
        ]
        assert result["shown_suggestions"] == []
        client.post(path + "/events", json={"action": "shown"}).raise_for_status()
        client.post(
            path + "/events",
            json={"action": "apply", "final_text": "🧵 pole request then pull request"},
        ).raise_for_status()
        result = client.post(
            path + "/events",
            json={"action": "reverse", "final_text": "🧵 pole request then pole request"},
        ).json()
        assert [step["action"] for step in result["steps"]] == ["apply", "reverse"]
        assert result["shown_suggestions"] == result["suggestions"]
        assert client.post(path + "/alternatives").status_code == 409
        client.post(path + "/events", json={"action": "feedback", "spoken": "unsure"})
        assert client.get(path).status_code == 404
        assert client.get("/api/trial").json()["exclusions"] == 1
    # The durable budget keeps cost but no live passage, suggestions or linkage.
    ledger = json.loads((tmp_path / "budget.json").read_text())
    assert ledger["requests"][0]["charged_usd"] == "0.0001475"
    assert "pole request" not in json.dumps(ledger) and passage_id not in json.dumps(ledger)


def test_manual_crossover_submits_current_passage_and_keeps_original(tmp_path, monkeypatch):
    monkeypatch.setattr("local_text.phrase_trial.secrets.choice", lambda arms: "manual")

    def provider(request):
        assert json.loads(request.content)["input"][1]["content"] == "New pole request"
        return provider_response(
            [{"phrase": "pole request", "occurrence": 1, "alternatives": ["pull request"]}]
        )

    with TestClient(fixture_app(tmp_path, provider)) as client:
        passage_id = begin(client, "Original recognition")
        path = f"/api/trial/passages/{passage_id}"
        client.post(path + "/events", json={"action": "edit_started"}).raise_for_status()
        client.post(
            path + "/events", json={"action": "edit", "final_text": "New pole request"}
        ).raise_for_status()
        result = client.post(path + "/alternatives").json()
        assert result["input"] == "Original recognition"
        assert result["request_input"] == "New pole request"
        assert result["switched_at"] >= result["started_at"]
        assert result["suggestions"][0]["start"] == 4
        assert client.post(path + "/alternatives").status_code == 409


@pytest.mark.parametrize("failure", ["http", "invalid", "timeout"])
def test_failure_never_retries_and_preserves_reservation(tmp_path, failure):
    def provider(request):
        if failure == "timeout":
            raise TimeoutError()
        if failure == "http":
            return httpx.Response(429, json={"error": "private provider body"})
        return provider_response([{"phrase": "absent", "occurrence": 1, "alternatives": ["new"]}])

    with TestClient(fixture_app(tmp_path, provider)) as client:
        passage_id = begin(client)
        path = f"/api/trial/passages/{passage_id}"
        result = client.post(path + "/alternatives").json()
        assert result["generation"] == ("timeout" if failure == "timeout" else "failed")
        assert result["suggestions"] == []
        assert client.post(path + "/alternatives").status_code == 409
        assert client.get("/api/trial").json()["charged_usd"] == (
            "0.0001475" if failure == "invalid" else "0.01"
        )


@pytest.mark.parametrize(
    "suggestions",
    [
        [],
        [
            {"phrase": "a", "occurrence": 1, "alternatives": ["x"]},
            {"phrase": "b", "occurrence": 1, "alternatives": ["y"]},
        ],
    ],
)
def test_abstention_and_adjacent_unicode_occurrences_are_valid(tmp_path, suggestions):
    with TestClient(
        fixture_app(tmp_path, lambda request: provider_response(suggestions))
    ) as client:
        passage_id = begin(client, "🧵ab")
        result = client.post(f"/api/trial/passages/{passage_id}/alternatives").json()
        assert result["generation"] == "completed"
        assert len(result["suggestions"]) == len(suggestions)
        assert result["final_text"] == "🧵ab"
        if suggestions:
            assert [(item["start"], item["end"]) for item in result["suggestions"]] == [
                (2, 3),
                (3, 4),
            ]


def test_shared_ceiling_and_expiry_cannot_be_reset_by_restart(tmp_path):
    def forbidden(request):
        pytest.fail("Provider must not be reached")

    # Existing screening and uncertain reservations count toward the same ceiling.
    (tmp_path / "budget.json").write_text(
        json.dumps(
            {
                "version": 1,
                "batches": ["screen"],
                "requests": [{"phase": "screen", "charged_usd": "4.995", "status": "uncertain"}],
            }
        )
    )
    app = fixture_app(tmp_path, forbidden)
    with TestClient(app) as client:
        passage_id = begin(client)
        assert client.post(f"/api/trial/passages/{passage_id}/alternatives").status_code == 409
        client.post("/api/trial/control", json={"action": "pause"})
        assert client.post("/api/trial/passages", json={"text": "x"}).status_code == 409
    state = json.loads((tmp_path / "trial.json").read_text())
    state.update(status="active", ends_at=time.time() - 1)
    (tmp_path / "trial.json").write_text(json.dumps(state))
    with TestClient(fixture_app(tmp_path, forbidden)) as client:
        assert client.get("/api/trial").json()["status"] == "expired"
        assert client.post("/api/trial/control", json={"action": "start"}).status_code == 409
        assert client.post("/api/trial/passages", json={"text": "x"}).status_code == 409
        client.post("/api/trial/control", json={"action": "extend"}).raise_for_status()
        assert client.get("/api/trial").json()["charged_usd"] == "4.995"


def test_inflight_edit_discards_and_withdrawal_never_resurrects(tmp_path):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def provider(request):
            entered.set()
            await release.wait()
            return provider_response(
                [{"phrase": "pole request", "occurrence": 2, "alternatives": ["pull request"]}]
            )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fixture_app(tmp_path, provider)),
            base_url="http://test",
        ) as client:
            await client.post("/api/trial/control", json={"action": "start"})
            await client.put("/api/trial/preference", json={"include": True})
            for withdraw in (False, True):
                entered.clear()
                release.clear()
                response = await client.post(
                    "/api/trial/passages", json={"text": "pole request then pole request"}
                )
                path = f"/api/trial/passages/{response.json()['id']}"
                task = asyncio.create_task(client.post(path + "/alternatives"))
                await entered.wait()
                if withdraw:
                    await client.delete(path)
                else:
                    await client.post(path + "/events", json={"action": "edit_started"})
                    await client.post(
                        path + "/events",
                        json={"action": "edit", "final_text": "My manually corrected passage"},
                    )
                release.set()
                result = await task
                if withdraw:
                    assert result.status_code == 404
                    assert (await client.get(path)).status_code == 404
                else:
                    assert result.json()["suggestions"] == []
                    assert result.json()["final_text"] == "My manually corrected passage"

    asyncio.run(scenario())
