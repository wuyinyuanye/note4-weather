#!/usr/bin/env python3
"""One-shot cloud probe of Shanghai Disneyland ThemeParks.wiki wait times.
Only standard-library modules are used; no credentials, no client IP dependencies.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import socket
import sys
import time
from urllib import request, error

PARK_ID = "ddc4357c-c148-4b36-9888-07894fe75e83"
BASE = "https://api.themeparks.wiki/v1"
OUTPUT = Path(os.getenv("PROBE_OUTPUT", "disney-probe-output"))
OUTPUT.mkdir(parents=True, exist_ok=True)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch(path: str):
    url = BASE + path
    req = request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "ShanghaiDisneyDataProbe/1.0 (+GitHub Actions research)"
    })
    started = time.monotonic()
    try:
        with request.urlopen(req, timeout=20) as response:
            status = response.status
            data = response.read(3_000_000)
            headers = dict(response.headers.items())
        result = json.loads(data)
        return result, {"url": url, "http_status": status,
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                        "bytes": len(data), "rate_limit_remaining": headers.get("RateLimit-Remaining")}
    except error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {url}; retry-after={exc.headers.get('Retry-After')}") from exc
    except (error.URLError, socket.timeout, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"{url}: {type(exc).__name__}: {exc}") from exc


def run():
    report = {"checked_at_utc": utc_now(), "park_id": PARK_ID,
              "source": "ThemeParks.wiki", "ok": False, "calls": []}
    try:
        entity, meta = fetch(f"/entity/{PARK_ID}")
        report["calls"].append(meta)
        if not isinstance(entity, dict):
            raise ValueError("entity response is not an object")
        report["park"] = {"name": entity.get("name"), "entity_type": entity.get("entityType")}
        name = str(entity.get("name") or "").lower()
        if not ("shanghai" in name and "disney" in name):
            raise ValueError(f"Park ID mismatch: {entity.get('name')!r}")
        live, meta = fetch(f"/entity/{PARK_ID}/live")
        report["calls"].append(meta)
        if not isinstance(live, dict) or not isinstance(live.get("liveData"), list):
            raise ValueError("Unexpected live response: missing liveData list")
        rows = []
        for item in live["liveData"]:
            if not isinstance(item, dict):
                continue
            queue = item.get("queue") or {}
            standby = queue.get("STANDBY") or {} if isinstance(queue, dict) else {}
            if not isinstance(standby, dict):
                standby = {}
            rows.append({"id": item.get("id"), "name": item.get("name"),
                         "type": item.get("entityType"), "status": item.get("status"),
                         "wait_minutes": standby.get("waitTime"),
                         "last_updated": item.get("lastUpdated")})
        report["item_count"] = len(rows)
        report["items_with_standby_wait"] = sum(isinstance(x["wait_minutes"], int) for x in rows)
        report["examples"] = [x for x in rows if x["wait_minutes"] is not None][:10]
        (OUTPUT / "rides.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUTPUT / "raw_live.json").write_text(json.dumps(live, ensure_ascii=False, indent=2), encoding="utf-8")
        if not rows:
            raise ValueError("liveData list is empty; cannot validate rides")
        report["ok"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        report["finished_at_utc"] = utc_now()
        (OUTPUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(run())
