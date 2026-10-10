#!/usr/bin/env python3
"""Monthly review input (mccrae). Builds, by script, everything the monthly review needs:
  monthly-table.py LOGDIR YYYY-MM
1. a 90-day table of daily fingerprints (daily + backfilled history entries) ending with that month
2. per-parameter month stats: first/last/min/max of the daily values, and the change over the month
3. every event, observation and Joe reply in that month, by date
"""
import importlib.util, statistics, sys
from datetime import date, timedelta
from pathlib import Path

spec = importlib.util.spec_from_file_location("lookback", "/root/reef-log/lookback.py")
lb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lb)

logdir, month = Path(sys.argv[1]), sys.argv[2]
y, m = map(int, month.split("-"))
first = date(y, m, 1)
last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
start = last - timedelta(days=89)

days = {}
for f in sorted(list(logdir.rglob("*-daily.md")) + list(logdir.rglob("*-history.md"))):
    d = f.name[:10]
    try:
        dd = date.fromisoformat(d)
    except ValueError:
        continue
    if not (start <= dd <= last):
        continue
    fp, meta, reply = lb.parse_entry(f)
    if d in days and f.name.endswith("-history.md"):
        continue
    days[d] = (fp, meta, reply, f.name.endswith("-history.md"))

params = []
for fp, *_ in days.values():
    for p in fp:
        if p not in params:
            params.append(p)

print(f"MONTHLY REVIEW INPUT for {month} (computed by script; quote numbers, do not recompute)")
print(f"Window: {start} to {last}; {len(days)} days with data ({sum(1 for v in days.values() if v[3])} backfilled numbers-only)\n")
print("90-day table (value / 7d direction; '-' = no fresh reading that day)")
print("date       " + " ".join(f"{p[:11]:>12}" for p in params))
for d in sorted(days):
    fp = days[d][0]
    cells = []
    for p in params:
        if p in fp:
            v, dirn = fp[p]
            cells.append(f"{v:g}{'' if dirn == 'n/a' else ' ' + {'rising': '↑', 'falling': '↓', 'flat': '→'}.get(dirn, '?')}")
        else:
            cells.append("-")
    print(f"{d} " + " ".join(f"{c:>12}" for c in cells) + ("  (backfill)" if days[d][3] else ""))

print(f"\nMonth stats {month} (daily values)")
for p in params:
    vals = [(d, days[d][0][p][0]) for d in sorted(days) if d.startswith(month) and p in days[d][0]]
    if len(vals) < 2:
        continue
    vs = [v for _, v in vals]
    print(f"  {p}: first {vals[0][1]:g} ({vals[0][0]}), last {vals[-1][1]:g} ({vals[-1][0]}), "
          f"change {vals[-1][1] - vals[0][1]:+g}, min {min(vs):g}, max {max(vs):g}, mean {statistics.fmean(vs):.2f}, n={len(vs)}")

print(f"\nEvents, observations and Joe's replies in {month}")
any_ = False
for d in sorted(days):
    if not d.startswith(month):
        continue
    fp, meta, reply, hist = days[d]
    ev, ob = meta.get("events", "[]"), meta.get("observations", "[]")
    parts = []
    if ev not in ("", "[]"):
        parts.append(f"events {ev}")
    if ob not in ("", "[]"):
        parts.append(f"observations {ob}")
    if reply:
        parts.append("Joe: " + " | ".join(l.strip() for l in reply.splitlines() if l.strip()))
    if parts:
        any_ = True
        print(f"  {d} [{meta.get('status', '?')}]: " + "; ".join(parts))
if not any_:
    print("  none recorded")
