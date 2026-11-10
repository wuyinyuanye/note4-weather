#!/usr/bin/env python3
"""Shanghai Disneyland API monitor (stdlib only).

This is a research probe, not a claim that upstream wait times are accurate.
Records raw values and separately determines whether a wait is usable:
  OPERATING + integer >=0 + updated within the freshness window.
Runs once per invocation; GitHub Actions controls the 15-minute schedule.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

PARK_ID = "ddc4357c-c148-4b36-9888-07894fe75e83"
BASE = "https://api.themeparks.wiki/v1"
FRESH_MINUTES = 12
OUTPUT = Path(os.getenv("PROBE_OUTPUT", "disney-probe-output"))


def utc_now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_date(raw):
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return value.astimezone(timezone.utc) if value.tzinfo else None
    except ValueError:
        return None


def get_json(path):
    url = BASE + path
    last_error = None
    for attempt in range(1, 4):
        start = time.monotonic()
        req = request.Request(
            url,
            headers={"Accept": "application/json",
                     "User-Agent": "ShanghaiDisneyQueueResearch/1.1 (GitHub Actions)"},
        )
        try:
            with request.urlopen(req, timeout=18) as response:
                body = response.read(3_000_000)
                headers = dict(response.headers.items())
                status = response.status
            parsed = json.loads(body)
            return parsed, {
                "url": url, "http_status": status, "attempt": attempt,
                "elapsed_seconds": round(time.monotonic() - start, 3),
                "bytes": len(body),
                "rate_limit_remaining": headers.get("RateLimit-Remaining"),
            }
        except error.HTTPError as exc:
            last_error = f"HTTP {exc.code} from {url}"
            if exc.code not in (408, 429, 500, 502, 503, 504):
                raise RuntimeError(last_error) from exc
            if attempt == 3:
                break
            retry_after = exc.headers.get("Retry-After")
            try:
                delay = min(max(float(retry_after), 2.0), 12.0)
            except (TypeError, ValueError):
                delay = 2.0 * attempt
            time.sleep(delay)
        except (error.URLError, socket.timeout, TimeoutError, OSError, ValueError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < 3:
                time.sleep(2.0 * attempt)
    raise RuntimeError(f"{url}: {last_error} after 3 attempts")


def add_summary(report):
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    line = (
        "Success" if report.get("ok") else "Request failure"
    )
    lines = [
        "## Shanghai Disneyland queue data check",
        f"- Checked UTC: {report['checked_at_utc']}",
        f"- API: **{line}**",
        f"- Data quality: **{report.get('data_quality', 'unknown')}**",
        f"- Returned entities: {report.get('item_count', 0)}",
        f"- Operating attractions: {report.get('operating_attractions', 0)}",
        f"- Standby waits (raw): {report.get('wait_value_count', 0)}",
        f"- Usable current waits: **{report.get('usable_wait_count', 0)}**",
        f"- Closed items retaining old wait values: {report.get('closed_with_wait', 0)}",
        f"- Missing/stale wait values: {report.get('unusable_wait_count', 0)}",
    ]
    if "error" in report:
        lines.append(f"- Error: `{report['error']}`")
    with open(target, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    observed_at = utc_now()
    report = {
        "checked_at_utc": iso(observed_at),
        "park_id": PARK_ID,
        "source": "ThemeParks.wiki",
        "fresh_threshold_minutes": FRESH_MINUTES,
        "ok": False,
        "calls": [],
    }
    try:
        park, meta = get_json(f"/entity/{PARK_ID}")
        report["calls"].append(meta)
        if not isinstance(park, dict) or "shanghai" not in str(park.get("name", "")).lower() or "disney" not in str(park.get("name", "")).lower():
            raise ValueError(f"Park identification mismatch: {str(park.get('name') if isinstance(park, dict) else park)[:100]}")
        report["park_name"] = park["name"]
        live, meta = get_json(f"/entity/{PARK_ID}/live")
        report["calls"].append(meta)
        if not isinstance(live, dict) or not isinstance(live.get("liveData"), list):
            raise ValueError("Unexpected live JSON: no liveData array")
        rows = []
        for entry in live["liveData"]:
            if not isinstance(entry, dict):
                continue
            queue = entry.get("queue")
            standby = queue.get("STANDBY") if isinstance(queue, dict) else None
            raw_wait = standby.get("waitTime") if isinstance(standby, dict) else None
            updated = parse_date(entry.get("lastUpdated"))
            age = round((observed_at - updated).total_seconds() / 60, 2) if updated else None
            status = entry.get("status")
            usable = (
                status == "OPERATING"
                and isinstance(raw_wait, int) and not isinstance(raw_wait, bool)
                and raw_wait >= 0
                and age is not None and -2 <= age <= FRESH_MINUTES
            )
            rows.append({
                "id": entry.get("id"),
                "name": entry.get("name"),
                "type": entry.get("entityType"),
                "status": status,
                "raw_standby_minutes": raw_wait,
                "usable_standby_minutes": raw_wait if usable else None,
                "last_updated_utc": iso(updated) if updated else None,
                "age_minutes": age,
                "wait_is_current": usable,
            })
        if not rows:
            raise ValueError("liveData array was empty")
        attractions = [r for r in rows if r["type"] == "ATTRACTION"]
        waits = [r for r in attractions if isinstance(r["raw_standby_minutes"], int) and not isinstance(r["raw_standby_minutes"], bool)]
        usable_waits = [r for r in waits if r["wait_is_current"]]
        closed_with_wait = [r for r in waits if r["status"] != "OPERATING"]
        ages = [r["age_minutes"] for r in attractions if r["age_minutes"] is not None]
        report.update({
            "item_count": len(rows),
            "attraction_count": len(attractions),
            "operating_attractions": sum(r["status"] == "OPERATING" for r in attractions),
            "status_counts": dict(Counter(str(r["status"]) for r in attractions)),
            "wait_value_count": len(waits),
            "usable_wait_count": len(usable_waits),
            "unusable_wait_count": len(waits) - len(usable_waits),
            "closed_with_wait": len(closed_with_wait),
            "items_updated_over_15_minutes_ago": sum(age > 15 for age in ages),
            "newest_item_age_minutes": min(ages) if ages else None,
            "oldest_item_age_minutes": max(ages) if ages else None,
            "usable_examples": [
                {"name": r["name"], "minutes": r["usable_standby_minutes"],
                 "age_minutes": r["age_minutes"]}
                for r in usable_waits[:12]
            ],
            "data_quality": "adequate" if len(usable_waits) >= 10 else "limited",
            "ok": True,
        })
        (OUTPUT / "raw_live.json").write_text(
            json.dumps(live, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (OUTPUT / "attractions.json").write_text(
            json.dumps(attractions, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # A machine-readable row for aggregation across GitHub Actions runs.
        (OUTPUT / "sample.jsonl").write_text(
            json.dumps(report, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["data_quality"] = "unavailable"
    finally:
        report["finished_at_utc"] = iso(utc_now())
        (OUTPUT / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        add_summary(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(run())
