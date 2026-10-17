"""Synthetic export-to-queue contract tests; no historical/private text."""

import json
import os
import select
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "recognition_review.py"
APPROVED_THREADS = [
    "T-2f893922-15a9-4f75-a7f0-83d8e400f5ff",
    "T-01a13bea-ddb2-752f-a80d-f0cb7961635a",
    "T-01a14713-03f3-7275-8fc2-376b3467ab62",
    "T-fa662f0d-a7da-4aa3-9193-cd1f60899d2e",
    "T-01a14139-62fa-708c-bd1b-54fdb2a7531d",
]


def message(number: int, role: str, at: str, text: str) -> dict:
    return {
        "messageId": number,
        "protocolMessageID": f"M-synthetic-{number}",
        "role": role,
        "createdAt": at,
        "content": [{"type": "text", "text": text}],
    }


def export(directory: Path, thread: str, messages: list[dict]) -> None:
    (directory / f"{thread}.json").write_text(json.dumps({"id": thread, "messages": messages}))


def run_cli(directory: Path, *arguments: str, script: Path = SCRIPT) -> subprocess.CompletedProcess:
    # Exercise the real CLI with network and non-Git child processes prohibited.
    # This catches accidental provider calls or delegation to external processors.
    runner = """
import pathlib, runpy, sys
def guard(event, args):
    if event.startswith('socket.'):
        raise AssertionError('Network access is forbidden')
    if event == 'subprocess.Popen' and pathlib.Path(args[0]).name != 'git':
        raise AssertionError('External text processing is forbidden')
sys.addaudithook(guard)
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
"""
    return subprocess.run(
        [sys.executable, "-c", runner, str(script), *arguments],
        cwd=directory,
        capture_output=True,
        text=True,
    )


def test_approved_defaults_work_from_another_directory_and_flags_replace_allowlist(tmp_path):
    for thread in APPROVED_THREADS:
        export(
            tmp_path,
            thread,
            [
                message(1, "user", "2026-10-16T12:00:00Z", "Open the cue for review."),
                message(2, "assistant", "2026-10-16T12:01:00Z", "Did you mean the queue?"),
            ],
        )
    output = tmp_path / "queue.jsonl"
    result = run_cli(tmp_path, "--exports", str(tmp_path), "--output", str(output))
    assert result.returncode == 0, result.stderr
    assert "Appended 10 unconfirmed" in result.stdout
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert {record["thread_id"] for record in records} == set(APPROVED_THREADS)

    # A named allowlist replaces defaults, rather than broadening it by addition.
    selected = tmp_path / "selected.jsonl"
    result = run_cli(
        tmp_path,
        "--exports",
        str(tmp_path),
        "--output",
        str(selected),
        "--thread",
        APPROVED_THREADS[2],
    )
    assert result.returncode == 0, result.stderr
    assert "Appended 2 unconfirmed" in result.stdout


@pytest.mark.parametrize(
    ("start", "end", "first", "last"),
    [
        ("2026-10-16", "2026-10-17", "2026-10-16T04:00:00Z", "2026-10-17T04:00:00Z"),
        ("2026-03-08", "2026-03-09", "2026-03-08T05:00:00Z", "2026-03-09T04:00:00Z"),
        ("2026-11-01", "2026-11-02", "2026-11-01T04:00:00Z", "2026-11-02T05:00:00Z"),
    ],
)
def test_local_calendar_boundaries_include_start_exclude_end_and_handle_dst(
    tmp_path,
    start,
    end,
    first,
    last,
):
    lower = datetime.fromisoformat(first)
    upper = datetime.fromisoformat(last)
    export(
        tmp_path,
        APPROVED_THREADS[0],
        [
            message(1, "user", (lower - timedelta(microseconds=1)).isoformat(), "Before the day."),
            message(2, "user", first, "Open the review cue."),
            message(
                3,
                "assistant",
                (lower + timedelta(seconds=1)).isoformat(),
                "Did you mean review queue?",
            ),
            message(
                4,
                "user",
                (upper - timedelta(microseconds=1)).isoformat(),
                "No, I meant the preview queue.",
            ),
            message(5, "assistant", last, "Did you mean the queue for preview?"),
        ],
    )
    output = tmp_path / "queue.jsonl"
    result = run_cli(
        tmp_path,
        "--exports",
        str(tmp_path),
        "--output",
        str(output),
        "--thread",
        APPROVED_THREADS[0],
        "--start",
        start,
        "--end",
        end,
    )
    assert result.returncode == 0, result.stderr
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert [record["source"]["id"] for record in records] == [
        "M-synthetic-2",
        "M-synthetic-3",
        "M-synthetic-4",
    ]


def test_later_replies_and_overlap_append_once_without_replacing_reviewed_wording(tmp_path):
    thread = APPROVED_THREADS[0]
    messages = [
        message(1, "user", "2026-10-16T23:59:58-04:00", "Open the forest queue."),
        message(2, "assistant", "2026-10-16T23:59:59-04:00", "Did you mean forecast queue?"),
        message(3, "user", "2026-10-17T00:00:01-04:00", "No, I meant the first queue."),
        message(4, "assistant", "2026-10-17T00:00:02-04:00", "Did you mean first, not forecast?"),
        message(5, "user", "2026-10-17T00:00:03-04:00", "Yes, the first queue."),
        message(6, "user", "2026-10-17T00:00:04-04:00", "Keep the unusual wording as written."),
    ]
    export(tmp_path, thread, messages)
    output = tmp_path / "queue.jsonl"
    args = ("--exports", str(tmp_path), "--output", str(output), "--thread", thread)
    first = run_cli(tmp_path, *args)
    assert first.returncode == 0, first.stderr
    initial = output.read_bytes()
    assert len(initial.splitlines()) == 2  # Later replies not silently included.
    review = (
        json.dumps(
            {
                "type": "review",
                "candidate_id": f"{thread}:M-synthetic-1",
                "classification": "unconfirmed",
                "reviewed_wording": "Leave pending for the owner.",
            }
        )
        + "\n"
    )
    with output.open("a") as queue:
        queue.write(review)
    original = output.read_bytes()
    later = run_cli(tmp_path, *args, "--start", "2026-10-17", "--end", "2026-10-18")
    assert later.returncode == 0, later.stderr
    assert "Appended 3 unconfirmed" in later.stdout
    complete = output.read_bytes()
    assert complete.startswith(original)
    records = [json.loads(line) for line in complete.splitlines()]
    evidence = [record for record in records if record["type"] == "evidence"]
    assert {record["candidate_id"] for record in evidence} == {f"{thread}:M-synthetic-1"}
    assert [record["source"]["text"] for record in evidence] == [
        message["content"][0]["text"] for message in messages[:5]
    ]
    assert all(record["classification"] == "unconfirmed" for record in evidence)
    assert all(
        record["source_url"] == f"https://ampcode.com/threads/{thread}" for record in evidence
    )
    for start in ("2026-10-17", "2026-10-16"):
        repeat = run_cli(tmp_path, *args, "--start", start, "--end", "2026-10-18")
        assert repeat.returncode == 0, repeat.stderr
        assert "Appended 0 unconfirmed" in repeat.stdout
        assert output.read_bytes() == complete

    # A source edit cannot silently change evidence that was already reviewed.
    messages[0]["content"][0]["text"] = "Edited source under the same identity."
    export(tmp_path, thread, messages)
    changed = run_cli(tmp_path, *args)
    assert changed.returncode == 1
    assert output.read_bytes() == complete


def test_excludes_unapproved_threads_nontext_payloads_and_accurate_unusual_wording(tmp_path):
    thread = APPROVED_THREADS[0]
    export(
        tmp_path,
        thread,
        [
            message(1, "user", "2026-10-16T08:00:00-04:00", "The green ideas sleep furiously."),
            message(2, "assistant", "2026-10-16T08:00:01-04:00", "Keeping that wording unchanged."),
            {
                "role": "user",
                "content": [{"type": "tool_result", "text": "I meant something else"}],
            },
            {"role": "assistant", "content": [{"type": "thinking", "text": "Did you mean blue?"}]},
        ],
    )
    # An unapproved file is not even parsed, regardless of its name/content.
    (tmp_path / f"{APPROVED_THREADS[1]}.json").write_text("NOT A JSON EXPORT")
    output = tmp_path / "queue.jsonl"
    result = run_cli(
        tmp_path,
        "--exports",
        str(tmp_path),
        "--output",
        str(output),
        "--thread",
        thread,
    )
    assert result.returncode == 0, result.stderr
    assert "Appended 0 unconfirmed" in result.stdout
    assert output.read_bytes() == b""
    assert output.stat().st_mode & 0o777 == 0o600


def test_later_agreement_does_not_bridge_an_unapproved_gap(tmp_path):
    thread = APPROVED_THREADS[0]
    export(
        tmp_path,
        thread,
        [
            message(1, "user", "2026-10-16T12:00:00-04:00", "Open the forest queue."),
            message(2, "assistant", "2026-10-16T12:01:00-04:00", "Did you mean first queue?"),
            message(3, "user", "2026-10-17T12:00:00-04:00", "An unrelated request outside scope."),
            message(4, "user", "2026-10-18T12:00:00-04:00", "Yes, please."),
        ],
    )
    output = tmp_path / "queue.jsonl"
    args = ("--exports", str(tmp_path), "--output", str(output), "--thread", thread)
    first = run_cli(tmp_path, *args)
    assert first.returncode == 0, first.stderr
    original = output.read_bytes()
    later = run_cli(tmp_path, *args, "--start", "2026-10-18", "--end", "2026-10-19")
    assert later.returncode == 0, later.stderr
    assert "Appended 0 unconfirmed" in later.stdout
    assert output.read_bytes() == original


@pytest.mark.parametrize("missing", ["protocolMessageID", "createdAt", "messageId"])
def test_missing_identity_or_date_metadata_fails_without_creating_queue(tmp_path, missing):
    source = message(1, "user", "2026-10-16T12:00:00-04:00", "Private text must not enter errors.")
    del source[missing]
    thread = APPROVED_THREADS[0]
    export(tmp_path, thread, [source])
    output = tmp_path / "queue.jsonl"
    result = run_cli(
        tmp_path,
        "--exports",
        str(tmp_path),
        "--output",
        str(output),
        "--thread",
        thread,
    )
    assert result.returncode == 1
    assert "Private text" not in result.stderr
    assert not output.exists()


def test_no_arguments_use_checkout_paths_even_when_started_from_scripts(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / SCRIPT.name
    shutil.copyfile(SCRIPT, script)
    (tmp_path / ".gitignore").write_text(".amp/\n")
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    exports = tmp_path / ".amp/in/artifacts/recognition-review/exports"
    exports.mkdir(parents=True)
    for thread in APPROVED_THREADS:
        export(
            exports,
            thread,
            [
                message(1, "user", "2026-10-16T12:00:00-04:00", "Open the cue."),
                message(2, "assistant", "2026-10-16T12:00:01-04:00", "Did you mean queue?"),
            ],
        )
    result = run_cli(scripts, script=script)
    assert result.returncode == 0, result.stderr
    assert "Appended 10 unconfirmed" in result.stdout
    output = exports.parent / "queue.jsonl"
    original = output.read_bytes()
    repeat = run_cli(tmp_path, script=script)
    assert repeat.returncode == 0, repeat.stderr
    assert "Appended 0 unconfirmed" in repeat.stdout
    assert output.read_bytes() == original
    assert not (scripts / ".amp").exists()


@pytest.mark.parametrize("early_cue", [True, False])
def test_rejected_interpretations_remain_in_one_chain_until_a_later_clarification(
    tmp_path,
    early_cue,
):
    thread = APPROVED_THREADS[0]
    export(
        tmp_path,
        thread,
        [
            message(1, "user", "2026-10-16T23:59:57-04:00", "Open the forest queue."),
            message(
                2,
                "assistant",
                "2026-10-16T23:59:58-04:00",
                "Did you mean forecast queue?" if early_cue else "Opening the forecast queue.",
            ),
            message(3, "user", "2026-10-16T23:59:59-04:00", "No, that's wrong."),
            message(4, "assistant", "2026-10-17T00:00:01-04:00", "You want the forest queue?"),
            message(5, "user", "2026-10-17T00:00:02-04:00", "No, I meant the first queue."),
        ],
    )
    output = tmp_path / "queue.jsonl"
    args = ("--exports", str(tmp_path), "--output", str(output), "--thread", thread)
    # Without an early cue, approve the whole exchange together so the tool need
    # not retain non-candidates as hidden pending state between runs.
    if early_cue:
        first = run_cli(tmp_path, *args)
        assert first.returncode == 0, first.stderr
        result = run_cli(tmp_path, *args, "--start", "2026-10-17", "--end", "2026-10-18")
    else:
        result = run_cli(tmp_path, *args, "--end", "2026-10-18")
    assert result.returncode == 0, result.stderr
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert {record["candidate_id"] for record in records} == {f"{thread}:M-synthetic-1"}
    assert [record["source"]["id"] for record in records] == [
        f"M-synthetic-{number}" for number in range(1, 6)
    ]
    assert all(record["classification"] == "unconfirmed" for record in records)


def test_cli_streams_file_progress_before_read_finishes_then_reports_counts(tmp_path):
    thread = APPROVED_THREADS[0]
    source_messages = [
        message(1, "user", "2026-10-16T12:00:00-04:00", "Open the cue for review."),
        message(2, "assistant", "2026-10-16T12:00:01-04:00", "Did you mean queue?"),
    ]
    # Pause the actual export read on stdin. Progress must be observable before
    # supplying any input, including when stdout is a pipe rather than a TTY.
    source_path = tmp_path / f"{thread}.json"
    source_path.symlink_to("/dev/stdin")
    output = tmp_path / "queue.jsonl"
    args = ("--exports", str(tmp_path), "--output", str(output), "--thread", thread)
    process = subprocess.Popen(
        [sys.executable, str(SCRIPT), *args],
        cwd=tmp_path,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    progress = b""
    try:
        while b"Reading [1/1]" not in progress:
            readable, _, _ = select.select([process.stdout], [], [], 5)
            assert readable, "No live file progress while the export read was pending"
            chunk = os.read(process.stdout.fileno(), 4096)
            assert chunk, "CLI exited before reporting file progress"
            progress += chunk
        remaining, errors = process.communicate(
            json.dumps({"id": thread, "messages": source_messages}).encode(),
            timeout=5,
        )
        assert process.returncode == 0, errors.decode()
        text = (progress + remaining).decode()
        assert "Selected 2 in-window text messages" in text
        assert "Processing [1/1]" in text
        assert "Candidates: 1; new evidence records: 2 (pending save)" in text
        assert "Appended 2 unconfirmed" in text
        assert str(output) in text
        assert all(item["content"][0]["text"] not in text for item in source_messages)
    finally:
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=5)

    # The same file is still processed visibly on a repeat; no new evidence is saved.
    source_path.unlink()
    export(tmp_path, thread, source_messages)
    repeat = run_cli(tmp_path, *args)
    assert repeat.returncode == 0, repeat.stderr
    assert "Candidates: 1; new evidence records: 0 (pending save)" in repeat.stdout
    assert "Appended 0 unconfirmed" in repeat.stdout
