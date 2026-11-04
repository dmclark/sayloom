"""Assemble a private, unconfirmed review queue from approved Amp JSON exports."""

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPOSITORY = Path(__file__).resolve().parents[1]
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
    """Reject tracked or nonignored Git destinations before retaining private text."""
    if path.is_symlink():
        raise ValueError("Private destination must not be a symlink")
    path = path.resolve()
    parent = path.parent
    while not parent.exists():
        parent = parent.parent
    owner = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=parent, capture_output=True, text=True
    )
    if owner.returncode == 0:
        repository = Path(owner.stdout.strip())
        relative = str(path.relative_to(repository))
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=repository,
            capture_output=True,
        )
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", "--", relative],
            cwd=repository,
        )
        if tracked.returncode == 0 or ignored.returncode != 0:
            raise ValueError("Private destinations inside a checkout must be ignored and untracked")
    return path


def default_directory() -> Path:
    worktrees = subprocess.run(
        ["git", "worktree", "list", "--porcelain", "-z"],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        check=True,
    )
    # Git lists the primary worktree first, independent of the current branch.
    primary = Path(worktrees.stdout.split("\0", 1)[0].removeprefix("worktree "))
    return primary / ".amp/in/artifacts/recognition-review"


def acquire_exports(exports: Path, threads: list[str] | None, lower: datetime) -> None:
    """Discover remote candidates and atomically cache full exports in private files."""
    candidates = {}
    if threads is None:
        # Search is based on thread updates, not message dates. Use a conservative
        # lower bound and no upper bound so later activity cannot hide older text.
        query = f"author:me after:{(lower - timedelta(days=1)).date().isoformat()}"
        limit = 100
        while True:
            print(f"Discovering Amp threads (limit {limit})", flush=True)
            result = subprocess.run(
                ["amp", "threads", "search", query, "--limit", str(limit), "--json"],
                capture_output=True,
                text=True,
                check=True,
            )
            rows = json.loads(result.stdout)
            if not isinstance(rows, list):
                raise ValueError("Unsupported Amp search response")
            for row in rows:
                thread = row["id"]
                if not THREAD_ID.fullmatch(thread):
                    raise ValueError("Invalid remote thread identity")
                updated = timestamp(row["updatedAt"])
                if updated >= lower:
                    candidates[thread] = updated
            if len(rows) < limit:
                break
            limit *= 2
    else:
        if not threads or any(not THREAD_ID.fullmatch(thread) for thread in threads):
            raise ValueError("Supply valid Amp thread IDs")
        # Explicit IDs bypass date-based discovery; refresh them to include later replies.
        candidates = dict.fromkeys(threads)
    exports.mkdir(mode=0o700, parents=True, exist_ok=True)
    print(f"Remote candidates: {len(candidates)}; export cache: {exports.resolve()}", flush=True)
    for index, (thread, updated) in enumerate(candidates.items(), 1):
        destination = private_output(exports / f"{thread}.json")
        if destination.exists() and updated is not None:
            cached = json.loads(destination.read_text())
            if cached.get("id") != thread:
                raise ValueError("Cached export identity does not match its filename")
            if cached.get("updatedAt") and timestamp(cached["updatedAt"]) >= updated:
                print(f"Using cached [{index}/{len(candidates)}] {thread}.json", flush=True)
                continue
        print(f"Downloading [{index}/{len(candidates)}] {thread}.json (full thread)", flush=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w+", dir=exports, delete=False) as stream:
                temporary = Path(stream.name)
                subprocess.run(
                    ["amp", "threads", "export", thread],
                    stdout=stream,
                    stderr=subprocess.PIPE,
                    check=True,
                )
                stream.seek(0)
                payload = json.load(stream)
                if payload.get("id") != thread or not isinstance(payload.get("messages"), list):
                    raise ValueError("Unsupported Amp export response")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def messages(export: Path, thread: str, start: datetime, end: datetime) -> list[dict] | None:
    payload = json.loads(export.read_text())
    if payload.get("id") != thread:
        raise ValueError("Export thread identity does not match its filename")
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
            return None  # Discard the entire export, including any earlier selected text.
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


def assemble(exports: Path, threads: list[str] | None, start: str, end: str, output: Path) -> int:
    """Append new source evidence; never modify existing evidence or review records."""
    lower, upper = window(start, end)
    if threads is None:
        threads = sorted(
            path.stem
            for path in exports.iterdir()
            if path.suffix == ".json" and THREAD_ID.fullmatch(path.stem) and path.is_file()
        )
    if any(not THREAD_ID.fullmatch(thread) for thread in threads):
        raise ValueError("Supply valid Amp thread IDs")
    threads = list(dict.fromkeys(threads))
    print(f"Window: {start} (inclusive) to {end} (exclusive), America/New_York", flush=True)
    # Parse local exports once; only in-window text enters candidate processing.
    selected = {}
    skipped = 0
    for index, thread in enumerate(threads, 1):
        print(f"Reading [{index}/{len(threads)}] {thread}.json", flush=True)
        current = messages(exports / f"{thread}.json", thread, lower, upper)
        if current is None:
            skipped += 1
            print(
                f"Warning: skipping {thread}.json: missing message createdAt; "
                "cannot enforce the date window.",
                file=sys.stderr,
                flush=True,
            )
            continue
        print(f"  Selected {len(current)} in-window text messages", flush=True)
        if current:
            selected[thread] = current
    print(f"Selected {len(selected)}/{len(threads)} threads in the date window", flush=True)
    if skipped:
        print(f"Coverage incomplete: skipped {skipped} exports with missing timestamps", flush=True)
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
            print(f"Processing [{index}/{len(selected)}] {thread}.json", flush=True)
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
    directory = default_directory()
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog="Discover Amp threads and download missing or newer full exports, then select "
        "text messages in the date window. Use --local-only to disable downloads. "
        "The default window is the fixed October 16 local day. "
        "Exports and the review queue are shared in the primary worktree.",
    )
    parser.add_argument(
        "--exports",
        default=directory / "exports",
        type=Path,
        help="Shared private JSON export cache",
    )
    parser.add_argument(
        "--local-only", action="store_true", help="Read existing exports without contacting Amp"
    )
    parser.add_argument(
        "--thread",
        action="append",
        help="Restrict selection to this thread ID; repeat for multiple threads",
    )
    parser.add_argument("--start", default="2026-10-16", help="Inclusive New York calendar date")
    parser.add_argument("--end", default="2026-10-17", help="Exclusive New York calendar date")
    parser.add_argument(
        "--output",
        default=directory / "queue.jsonl",
        type=Path,
        help="Approved private JSONL queue and state",
    )
    args = parser.parse_args()
    try:
        lower, _ = window(args.start, args.end)
        private_output(args.output)
        if not args.local_only:
            acquire_exports(args.exports, args.thread, lower)
        count = assemble(args.exports, args.thread, args.start, args.end, args.output)
    except FileNotFoundError:
        parser.exit(
            1,
            "Amp CLI, export directory, or selected export is missing. Check your Amp "
            "installation and --exports path; --local-only requires existing exports.\n",
        )
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as error:
        # Do not print exception details: malformed input errors may contain private text.
        parser.exit(1, f"Review assembly failed ({type(error).__name__}); no success claimed.\n")
    print(f"Appended {count} unconfirmed evidence records; existing records unchanged.", flush=True)
    print(f"Queue: {args.output.resolve()}", flush=True)


if __name__ == "__main__":
    main()
