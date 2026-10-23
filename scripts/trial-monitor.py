#!/usr/bin/env python3
"""Standalone experimental trial monitor. No app imports, locks, writes or history.

Run with Python 3.12+ (standard library only; uv/project installation is not needed):
    python3 scripts/trial-monitor.py --directory /path/to/trial-store

Serves loopback port 58432 by default. Ctrl-C stops the monitor, not the app.
The directory must be selected explicitly; this script does not discover app state.
"""

import argparse
import json
import math
import time
from collections import Counter
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")


def stamp(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        try:
            return datetime.fromtimestamp(value, TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
        except (ValueError, OverflowError, OSError):
            pass
    return None


def aggregate(root):
    result = {
        "checked_at": stamp(time.time()),
        "available": False,
        "message": "No trial store found",
        "status": "unknown",
        "retained": 0,
        "arms": {"manual": 0, "alternatives": 0, "unknown": 0},
        "days": {},
        "feedback": 0,
        "confirmed": 0,
        "effort": 0,
        "withdrawals": None,
        "exclusions": None,
        "include": None,
        "last_activity": None,
        "ends_at": None,
        "unreadable": 0,
        "undated": 0,
    }
    if not root.is_dir():
        return result
    result.update(available=True, message="Store present · read-only observation")
    activity = []

    def read(path):
        try:
            # Refuse symlink files; only explicitly selected JSON files are opened.
            if path.is_symlink():
                raise ValueError()
            with path.open() as stream:
                value = json.load(stream)
            if not isinstance(value, dict):
                raise ValueError()
            activity.append(path.stat().st_mtime)
            return value
        except (OSError, ValueError):
            result["unreadable"] += 1
            return None

    state_path = root / "trial.json"
    if state_path.exists():
        state = read(state_path)
        if state is not None:
            status = state.get("status")
            if status in {"not_started", "active", "paused", "stopped", "expired"}:
                result["status"] = status
            end = state.get("ends_at")
            result["ends_at"] = stamp(end)
            if result["status"] == "active" and stamp(end) and time.time() >= end:
                result["status"] = "expired"
            for key in ("withdrawals", "exclusions"):
                if type(state.get(key)) is int and state[key] >= 0:
                    result[key] = state[key]
            if type(state.get("include")) is bool:
                result["include"] = state["include"]
    days = Counter()
    try:
        paths = list(root.glob("passage-*.json"))
    except OSError:
        result.update(message="Store cannot be read", available=False)
        return result
    for path in paths:
        try:
            UUID(path.stem.removeprefix("passage-"))
        except ValueError:
            continue
        record = read(path)
        if record is None:
            continue
        result["retained"] += 1
        arm = record.get("assignment")
        result["arms"][arm if arm in {"manual", "alternatives"} else "unknown"] += 1
        started = stamp(record.get("started_at"))
        if started:
            days[started[:10]] += 1
        else:
            result["undated"] += 1
        feedback = record.get("feedback")
        if isinstance(feedback, dict):
            confirmed = feedback.get("spoken") == "confirmed"
            effort = feedback.get("effort") in {"less", "same", "more"}
            result["confirmed"] += confirmed
            result["effort"] += effort
            result["feedback"] += bool(confirmed or effort or feedback.get("note"))
    result["days"] = dict(sorted(days.items(), reverse=True))
    result["last_activity"] = stamp(max(activity)) if activity else None
    return result


HTML = r"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trial monitor · read-only prototype</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f6f8;color:#18212e;font:16px/1.5 system-ui,sans-serif}
main{max-width:960px;margin:auto;padding:36px 24px}h1{font-size:30px;margin:4px 0 8px;line-height:1.2}h2{font-size:18px;margin:0 0 12px}p{margin:8px 0}.muted{color:#536174}.eyebrow{font-size:12px;letter-spacing:.1em;font-weight:700;color:#425775}
.notice{background:#e8eef8;border-left:4px solid #486b9c;padding:12px 16px;margin:24px 0}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.card,section{background:white;border:1px solid #dce1e7;border-radius:8px;padding:20px}.value{font-size:34px;font-weight:650;margin:4px 0}.label{font-size:14px;color:#536174}.columns{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}section{margin-top:18px}.columns section{margin:0}dl{margin:0}dl div{display:flex;justify-content:space-between;gap:20px;border-bottom:1px solid #eef0f3;padding:9px 0}dt{color:#536174}dd{margin:0;text-align:right}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:9px 0;border-bottom:1px solid #eef0f3}th:last-child,td:last-child{text-align:right}footer{font-size:13px;color:#536174;margin:20px 0}#failure{color:#962a26;font-weight:650}
@media(max-width:600px){main{padding:24px 18px}.cards,.columns{grid-template-columns:1fr}.card{padding:16px}.value{font-size:30px}h1{font-size:27px}}
</style>
<main><div class="eyebrow">STANDALONE · READ-ONLY PROTOTYPE</div><h1>Phrase-alternatives trial</h1>
<p class="muted">A current view of retained data, refreshed every 10 seconds.</p>
<div class="notice"><strong id="source"></strong><br><span id="message">Reading store…</span></div>
<p id="failure" role="alert"></p>
<div class="cards"><div class="card"><div class="label">Retained passages</div><div class="value" id="retained">—</div><div class="label">Can decrease after deletion</div></div>
<div class="card"><div class="label">With feedback</div><div class="value" id="feedback">—</div><div class="label" id="coverage">Of retained passages</div></div>
<div class="card"><div class="label">Trial status</div><div class="value" style="font-size:26px" id="status">—</div><div class="label" id="include">Opt-in unknown</div></div></div>
<div class="columns"><section><h2>Randomized assignments</h2><dl><div><dt>Manual</dt><dd id="manual">—</dd></div><div><dt>Alternatives</dt><dd id="alternatives">—</dd></div><div><dt>Unknown arm</dt><dd id="unknown">—</dd></div></dl><p class="label">Original assignments, not actual exposure or completed work.</p></section>
<section><h2>Feedback & removals</h2><dl><div><dt>Spoken confirmed</dt><dd id="confirmed">—</dd></div><div><dt>Effort supplied</dt><dd id="effort">—</dd></div><div><dt>Withdrawals recorded</dt><dd id="withdrawals">—</dd></div><div><dt>Exclusions recorded</dt><dd id="exclusions">—</dd></div></dl><p class="label">Feedback = confirmation, effort, or note. Removal counters come from trial metadata.</p></section></div>
<section><h2>Retained passages by start day</h2><p class="label">America/New_York · Not a lifetime collection curve</p><table><thead><tr><th scope="col">Day</th><th scope="col">Retained</th></tr></thead><tbody id="days"></tbody></table><p class="label" id="undated"></p></section>
<section><h2>Activity</h2><dl><div><dt>Last known file update</dt><dd id="last_activity">—</dd></div><div><dt>Trial ends</dt><dd id="ends_at">—</dd></div><div><dt>Last successful check</dt><dd id="checked_at">—</dd></div></dl><p class="label" id="quality"></p></section>
<footer>No passage text, identifiers, or private paths are served. No snapshots or history are saved. Reads are unlocked and may briefly reflect concurrent changes. File updates are not proof of new collection. No efficacy conclusions.</footer></main>
<script>
const el=id=>document.getElementById(id);
async function refresh(){try{const r=await fetch('/aggregate',{cache:'no-store'});if(!r.ok)throw Error();const d=await r.json();
el('failure').textContent='';el('source').textContent=d.synthetic?'SYNTHETIC DEMO DATA':'Selected store · aggregate-only observation';el('message').textContent=d.message;
for(const k of ['retained','feedback','confirmed','effort','withdrawals','exclusions','last_activity','ends_at','checked_at'])el(k).textContent=d.available?(d[k]??'Unknown'):'—';
for(const k of ['manual','alternatives','unknown'])el(k).textContent=d.available?d.arms[k]:'—';
el('status').textContent=d.status.replaceAll('_',' ');el('include').textContent=d.include===null?'Opt-in unknown':d.include?'Opted in':'Not opted in';
el('coverage').textContent=d.available&&d.retained?`${Math.round(d.feedback/d.retained*100)}% of retained passages`:'No coverage denominator';
el('days').replaceChildren();for(const [day,count] of Object.entries(d.days)){const row=document.createElement('tr');for(const v of [day,count]){const cell=document.createElement('td');cell.textContent=v;row.append(cell)}el('days').append(row)}
if(!Object.keys(d.days).length){const row=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=2;cell.textContent=d.available?'No dated retained passages':'No trial store found';row.append(cell);el('days').append(row)}
el('undated').textContent=d.undated?`${d.undated} retained passages have no usable start date.`:'';
el('quality').textContent=d.unreadable?`${d.unreadable} files unreadable or changing; counts may be incomplete.`:'File update time includes state and retained passages; deleted activity cannot be reconstructed.';
}catch{el('failure').textContent='Refresh failed — displayed values may be stale.'}}
refresh();setInterval(refresh,10000);
</script></html>"""  # noqa: E501


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument(
        "--port", type=int, default=58432, help="Default: 58432; 0 selects an unused port"
    )
    parser.add_argument("--synthetic", action="store_true", help="Label a synthetic store")
    args = parser.parse_args()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # No request paths or raw exceptions in logs.

        def do_GET(self):
            if self.path == "/":
                body, kind = HTML.encode(), "text/html; charset=utf-8"
            elif self.path == "/aggregate":
                data = aggregate(args.directory.expanduser())
                data["synthetic"] = args.synthetic
                body, kind = json.dumps(data).encode(), "application/json"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                "connect-src 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(
        f"Read-only trial monitor listening on runner loopback port {server.server_port}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
