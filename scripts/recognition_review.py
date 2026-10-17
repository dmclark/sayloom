"""Assemble a private, unconfirmed review queue from approved Amp JSON exports."""

import argparse
import fcntl
import json
import os
import re
import subprocess
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

REPOSITORY = Path(__file__).resolve().parents[1]
DEFAULT_DIRECTORY = REPOSITORY / ".amp/in/artifacts/recognition-review"
DEFAULT_THREADS = (
    "T-2f893922-15a9-4f75-a7f0-83d8e400f5ff",
    "T-01a13bea-ddb2-752f-a80d-f0cb7961635a",
    "T-01a14713-03f3-7275-8fc2-376b3467ab62",
    "T-fa662f0d-a7da-4aa3-9193-cd1f60899d2e",
    "T-01a14139-62fa-708c-bd1b-54fdb2a7531d",
)
THREAD_ID = re.compile(r"T-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
CUE = re.compile(
    r"\b(?:did you mean|do you mean|i (?:meant|said)|what i meant|"
    r"misheard|misrecognized|misrecognised|recognition error|"
    r"transcription error|voiceitt (?:changed|misunderstood))\b",
    re.IGNORECASE,
)
REJECTION = re.compile(
    r"^(?:no\b|not\b|wrong\b|incorrect\b|that(?:'s| is) (?:wrong|not)\b)",
    re.IGNORECASE,
)
LOCAL_ZONE = ZoneInfo("America/New_York")


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Message timestamps must include a timezone offset")
    return result.astimezone(UTC)


def window(start: str, end: str) -> tuple[datetime, datetime]:
    boundaries = tuple(
        datetime.combine(date.fromisoformat(value), time.min, LOCAL_ZONE).astimezone(UTC)
        for value in (start, end)
    )
    if boundaries[0] >= boundaries[1]:
        raise ValueError("Start must be earlier than end")
    return boundaries


def private_output(path: Path) -> Path:
    """Reject tracked or nonignored checkout destinations before retaining text."""
    if path.is_symlink():
        raise ValueError("Queue must not be a symlink")
    path = path.resolve()
    if path.is_relative_to(REPOSITORY):
        relative = str(path.relative_to(REPOSITORY))
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=REPOSITORY,
            capture_output=True,
        )
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", "--", relative],
            cwd=REPOSITORY,
        )
        if tracked.returncode == 0 or ignored.returncode != 0:
            raise ValueError("Queue inside the checkout must be ignored and untracked")
    return path


def messages(export: Path, thread: str, start: datetime, end: datetime) -> list[dict]:
    payload = json.loads(export.read_text())
    if payload.get("id") != thread:
        raise ValueError("Export thread identity does not match the allowlist")
    result = []
    seen = set()
    previous_id = None
    for message in payload["messages"]:
        role = message.get("role")
        blocks = message.get("content", [])
        if role not in {"user", "assistant"} or not any(
            block.get("type") == "text" for block in blocks
        ):
            continue
        identity = message.get("protocolMessageID")
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError("Export requires unique, stable protocolMessageID values")
        seen.add(identity)
        predecessor = previous_id
        previous_id = identity
        # Out-of-window metadata prevents false chains across gaps. Never inspect
        # out-of-window text, tool payloads, thinking blocks, or attachments.
        at = message.get("createdAt")
        if at is None:
            raise ValueError("Export message is missing createdAt; cannot enforce scope")
        if not start <= timestamp(at) < end:
            continue
        text = "\n".join(block["text"] for block in blocks if block.get("type") == "text")
        if not text.strip():
            continue
        sequence = message.get("messageId")
        if not isinstance(sequence, int):
            raise ValueError("Export requires numeric messageId ordering metadata")
        result.append(
            {
                "id": identity,
                "at": at,
                "role": role,
                "text": text,
                "previous_id": predecessor,
                "sequence": sequence,
            }
        )
    return result


def assemble(exports: Path, threads: list[str], start: str, end: str, output: Path) -> int:
    """Append new source evidence; never modify existing evidence or review records."""
    if not threads or any(not THREAD_ID.fullmatch(thread) for thread in threads):
        raise ValueError("Supply an explicit allowlist of valid Amp thread IDs")
    lower, upper = window(start, end)
    threads = list(dict.fromkeys(threads))
    print(f"Window: {start} (inclusive) to {end} (exclusive), America/New_York", flush=True)
    # Read only named exports, never enumerate an export directory or fetch threads.
    selected = {}
    for index, thread in enumerate(threads, 1):
        print(f"Reading [{index}/{len(threads)}] {thread}.json", flush=True)
        selected[thread] = messages(exports / f"{thread}.json", thread, lower, upper)
        print(f"  Selected {len(selected[thread])} in-window text messages", flush=True)
    output = private_output(output)
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "r+", encoding="utf-8") as queue:
        print(f"Waiting for queue lock: {output}", flush=True)
        fcntl.flock(queue, fcntl.LOCK_EX)
        if os.fstat(queue.fileno()).st_mode & 0o077:
            raise ValueError("Existing queue must be private (chmod 600)")
        original = queue.read()
        if original and not original.endswith("\n"):
            raise ValueError("Queue has an incomplete final line; repair it before retrying")
        records = [json.loads(line) for line in original.splitlines() if line.strip()]
        print(f"Loaded {len(records)} existing queue records", flush=True)
        sources = {}
        retained = {}
        for record in records:
            if record["type"] != "evidence":
                continue  # Human review records are opaque and are never rewritten.
            key = (record["thread_id"], record["source"]["id"])
            if key in sources and sources[key] != record["source"]:
                raise ValueError("Conflicting retained source identity")
            sources[key] = record["source"]
            retained[key] = record["candidate_id"]
        additions = []

        def append(thread: str, candidate: str, source: dict, relation: str) -> None:
            key = (thread, source["id"])
            if key in sources:
                if sources[key] != source:
                    raise ValueError("Source changed; reviewed evidence will not be replaced")
                return
            additions.append(
                {
                    "type": "evidence",
                    "candidate_id": candidate,
                    "thread_id": thread,
                    "source": source,
                    "relation": relation,
                    "classification": "unconfirmed",
                    "source_url": f"https://ampcode.com/threads/{thread}",
                }
            )
            sources[key] = source
            retained[key] = candidate

        for index, (thread, current) in enumerate(selected.items(), 1):
            print(f"Processing [{index}/{len(threads)}] {thread}.json", flush=True)
            before = len(additions)
            # Retained evidence was already authorized. It can anchor later replies,
            # but we do not reopen earlier exports or read out-of-window text.
            by_id = {key[1]: source for key, source in sources.items() if key[0] == thread}
            for source in current:
                previous = by_id.get(source["id"])
                if previous is not None and previous != source:
                    raise ValueError("Source changed; reviewed evidence will not be replaced")
                by_id[source["id"]] = source
            ordered = sorted(by_id.values(), key=lambda source: source["sequence"])
            context = []
            previous_id = None
            active = None
            for source in ordered:
                if source["previous_id"] != previous_id:
                    context = []
                    active = None
                previous_id = source["id"]
                key = (thread, source["id"])
                if key in retained:
                    active = retained[key]
                cue = CUE.search(source["text"])
                rejection = source["role"] == "user" and REJECTION.search(source["text"].strip())
                if cue and context and active is None:
                    active = next(
                        (
                            retained[(thread, item["id"])]
                            for item in context
                            if (thread, item["id"]) in retained
                        ),
                        f"{thread}:{context[0]['id']}",
                    )
                    for index, item in enumerate(context):
                        relation = (
                            "agent_interpretation"
                            if item["role"] == "assistant"
                            else ("observed" if index == 0 else "possible_clarification")
                        )
                        append(thread, active, item, relation)
                if active is not None:
                    relation = (
                        "agent_interpretation"
                        if source["role"] == "assistant"
                        else "possible_clarification"
                    )
                    append(thread, active, source, relation)
                if source["role"] == "user" and not cue and not rejection:
                    active = None
                    context = [source]
                else:
                    context.append(source)
                # Keep only bounded, contiguous prior context in memory. An
                # ordinary new user request resets it; rejections preserve it.
                context = context[-6:]
                while context and context[0]["role"] != "user":
                    context.pop(0)
            candidates = {
                retained[(thread, source["id"])]
                for source in current
                if (thread, source["id"]) in retained
            }
            print(
                f"  Candidates: {len(candidates)}; new evidence records: "
                f"{len(additions) - before} (pending save)",
                flush=True,
            )
        # Validate the complete batch before writing; repeated/overlapping runs
        # deduplicate by thread and protocol message identity, not text or dates.
        print(f"Saving {len(additions)} new evidence records", flush=True)
        queue.seek(0, os.SEEK_END)
        queue.write("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in additions))
        queue.flush()
        os.fsync(queue.fileno())
    return len(additions)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog="No arguments uses the approved five threads and fixed October 16 local day. "
        "Default paths are checkout-relative, not relative to the current directory. "
        "Exports must already exist; this command does not download threads.",
    )
    parser.add_argument(
        "--exports",
        default=DEFAULT_DIRECTORY / "exports",
        type=Path,
        help="Approved JSON export directory",
    )
    parser.add_argument(
        "--thread",
        action="append",
        default=argparse.SUPPRESS,
        help="Repeat for each allowed ID; replaces the approved five-thread whitelist "
        "listed in docs/recognition-review-queue.md",
    )
    parser.add_argument("--start", default="2026-10-16", help="Inclusive New York calendar date")
    parser.add_argument("--end", default="2026-10-17", help="Exclusive New York calendar date")
    parser.add_argument(
        "--output",
        default=DEFAULT_DIRECTORY / "queue.jsonl",
        type=Path,
        help="Approved private JSONL queue and state",
    )
    args = parser.parse_args()
    threads = getattr(args, "thread", list(DEFAULT_THREADS))
    try:
        count = assemble(args.exports, threads, args.start, args.end, args.output)
    except FileNotFoundError:
        parser.exit(
            1,
            "An approved export or directory is missing. Supply existing Amp JSON "
            "exports via --exports; this command never downloads threads.\n",
        )
    except (ValueError, KeyError, TypeError, OSError) as error:
        # Do not print exception details: malformed input errors may contain private text.
        parser.exit(1, f"Review assembly failed ({type(error).__name__}); no success claimed.\n")
    print(f"Appended {count} unconfirmed evidence records; existing records unchanged.", flush=True)
    print(f"Queue: {args.output.resolve()}", flush=True)


if __name__ == "__main__":
    main()
