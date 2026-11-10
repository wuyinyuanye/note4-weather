#!/usr/bin/env python3
"""Compare two unofficial Shanghai Disney queue feeds within one cloud run.
Agreement is NOT proof either feed matches the official Disney app.
"""
import difflib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import request

PARK="ddc4357c-c148-4b36-9888-07894fe75e83"
URLS={
  "themeparks":f"https://api.themeparks.wiki/v1/entity/{PARK}/live",
  "queue_times":"https://queue-times.com/parks/30/queue_times.json",
}
OUT=Path("disney-compare-output")
OUT.mkdir(parents=True,exist_ok=True)

def norm(x):
    x=(x or "").lower()
    x=re.sub(r"[^a-z0-9 ]"," ",x)
    return " ".join(x.split())

def download(url):
    started=time.monotonic()
    with request.urlopen(request.Request(url,headers={"User-Agent":"ShanghaiDisneyResearch/1.0","Accept":"application/json"}),timeout=20) as resp:
        data=resp.read(3_000_000)
        status=resp.status
    return json.loads(data), {"http_status":status,"elapsed_s":round(time.monotonic()-started,3),"bytes":len(data),"retrieved_at":datetime.now(timezone.utc).isoformat()}

def main():
    report={"checked_at":datetime.now(timezone.utc).isoformat(),"sources":{},"error":None}
    try:
        data={}
        for src,url in URLS.items():
            body,meta=download(url)
            data[src]=body
            report["sources"][src]=meta
            (OUT/f"{src}.json").write_text(json.dumps(body,ensure_ascii=False,indent=2),encoding="utf-8")
        tp=[{"name":x.get("name"),"open":x.get("status")=="OPERATING",
             "status":x.get("status"),
             "wait":((x.get("queue") or {}).get("STANDBY") or {}).get("waitTime"),
             "updated":x.get("lastUpdated")}
            for x in data["themeparks"].get("liveData",[]) if x.get("entityType")=="ATTRACTION"]
        qt=[]
        obj=data["queue_times"]
        for ride in obj.get("rides",[]):
            qt.append(ride)
        for land in obj.get("lands",[]):
            for ride in land.get("rides",[]):
                qt.append(ride)
        qt=[{"name":r.get("name"),"open":r.get("is_open"),"wait":r.get("wait_time"),"updated":r.get("last_updated")} for r in qt]
        names={norm(x["name"]):x for x in qt if x["name"]}
        used=set()
        pairs=[]
        for ride in tp:
            name=norm(ride["name"])
            match=names.get(name)
            score=1.0 if match else 0
            if not match:
                candidates=[(difflib.SequenceMatcher(None,name,k).ratio(),k,v) for k,v in names.items() if k not in used]
                if candidates:
                    score,key,closest=max(candidates,key=lambda x:x[0])
                    if score>=0.76:match=closest
            if match:
                key=norm(match["name"])
                if key in used:continue
                used.add(key)
                both_open=ride["open"] and match["open"]
                valid_numbers=both_open and type(ride["wait"]) is int and type(match["wait"]) is int
                pairs.append({
                    "themeparks_name":ride["name"],"queue_times_name":match["name"],"match_score":round(score,3),
                    "tp_open":ride["open"],"qt_open":match["open"],"status_agrees":ride["open"]==match["open"],
                    "tp_wait":ride["wait"],"qt_wait":match["wait"],
                    "difference_minutes":abs(ride["wait"]-match["wait"]) if valid_numbers else None,
                    "tp_last_updated":ride["updated"],"qt_last_updated":match["updated"],
                })
        measured=[p for p in pairs if p["difference_minutes"] is not None]
        report.update({
            "tp_attractions":len(tp),"queue_times_rides":len(qt),"matched":len(pairs),
            "both_open_numeric":len(measured),"exact_matches":sum(p["difference_minutes"]==0 for p in measured),
            "within_5_min":sum(p["difference_minutes"]<=5 for p in measured),
            "over_15_min":sum(p["difference_minutes"]>15 for p in measured),
            "status_mismatches":sum(not p["status_agrees"] for p in pairs),
            "pairs":pairs,
            "warning":"Two downstream aggregators may share a single Disney upstream. Agreement is not independent confirmation against the official Disney app.",
        })
        report["ok"]=True
    except Exception as e:
        report["ok"]=False
        report["error"]=f"{type(e).__name__}: {e}"
    (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report.get("ok") else 1

if __name__=="__main__":
    raise SystemExit(main())
