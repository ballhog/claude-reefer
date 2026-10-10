#!/usr/bin/env python3
"""Write history entries (fingerprint only) for past days from reefchem reports made --asof 06:25.
mccrae:  backfill.py REPORTDIR LOGDIR   (REPORTDIR holds YYYY-MM-DD.txt as-of reports)"""
import importlib.util, sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("lookback", "/root/reef-log/lookback.py")
lb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lb)

rdir, logdir = Path(sys.argv[1]), Path(sys.argv[2])
made = 0
for r in sorted(rdir.glob("????-??-??.txt")):
    day = r.stem
    target = logdir / day[:4] / day[5:7] / f"{day}-history.md"
    if (logdir / day[:4] / day[5:7] / f"{day}-daily.md").exists() or target.exists():
        continue
    _, fp = lb.today_fp(r)
    if len(fp) < 3:
        continue
    target.parent.mkdir(parents=True, exist_ok=True)
    body = ["---", f"date: {day}", "type: history", "status: backfill", "fingerprint:"]
    body += [f"  {p}: {{value: {v:g}, trend_7d: {d}}}" for p, (v, d) in fp.items()]
    body += ["events: []", "observations: []", "tags: [backfill]", "---",
             "Backfilled from stored sensor data (as of 06:25). Numbers only: no analysis, no notes, no replies.", ""]
    target.write_text("\n".join(body))
    made += 1
print(f"{made} history entries written")
