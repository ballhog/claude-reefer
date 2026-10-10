#!/usr/bin/env python3
"""Reef log look-back (mccrae). stdlib only. All the matching math lives here, not in the model.

  lookback.py REPORT LOGDIR [--top 3]

1. Computes today's fingerprint from the reefchem REPORT (value + 7-day direction per parameter;
   alk uses the latest pre-dose value). Flat = |trend/day| under 2% of the target band width.
2. Reads every past *-daily.md fingerprint in LOGDIR and scores how similar each day was.
3. Prints the fingerprint block to copy into today's entry, the best matches, and what followed them
   (events, status, Joe's replies in the next 14 days).
"""
import re, sys
from datetime import date, timedelta
from pathlib import Path

BASELINES = Path("/mnt/reef-lab/data/reef-baselines.md")
HEAD = re.compile(r"^(\w+) \(([^)]*)\), target ([-\d.]+)-([-\d.]+):")
VAL = re.compile(r"^  \w+ (?:last new test result|latest): ([-\d.]+)")
PRE = re.compile(r"^  pre-dose alk .*: (.*)$")
TREND = re.compile(r"trend ([-+][\d.]+)/day")
FP = re.compile(r"^\s+(\w+): \{value: ([-\d.]+), trend_7d: (\w+)\}")


def bands():
    out = {}
    if BASELINES.exists():
        for l in BASELINES.read_text().splitlines():
            c = [x.strip() for x in l.strip().strip("|").split("|")]
            if len(c) == 5:
                try:
                    out[c[0]] = (float(c[3]), float(c[4]))
                except ValueError:
                    pass
    return out


def today_fp(report):
    fp, cur, first = {}, None, None
    for l in Path(report).read_text().splitlines():
        if first is None:
            m = re.search(r"\d{4}-\d{2}-\d{2}", l)
            first = m.group(0) if m else str(date.today())
        m = HEAD.match(l)
        if m:
            cur = m.group(1)
            fp[cur] = {"band": (float(m.group(3)), float(m.group(4)))}
            continue
        if not cur:
            continue
        if l and not l.startswith(" "):
            cur = None
            continue
        m = VAL.match(l)
        if m:
            fp[cur]["value"] = float(m.group(1))
            a = re.search(r"([\d.]+) (h|d) ago", l)
            if a and float(a.group(1)) * (24 if a.group(2) == "d" else 1) > (36 if "test result" in l else 12):
                fp[cur]["stalled"] = True   # old reading (feed down or Trident stalled): not today's state
        m = PRE.match(l)
        if m:
            vals = re.findall(r"\d\d-\d\d ([-\d.]+)", m.group(1))
            if vals:
                fp[cur]["value"] = float(vals[-1])
                fp[cur]["note"] = "pre-dose"
        if l.startswith("  STALLED?"):
            fp[cur]["stalled"] = True
        if l.startswith("  7d:"):
            m = TREND.search(l)
            if m:
                fp[cur]["trend"] = float(m.group(1))
    out = {}
    for p, d in fp.items():
        if "value" not in d or d.get("stalled"):   # a stale Trident value is not today's state
            continue
        lo, hi = d["band"]
        if not (lo * 0.5 <= d["value"] <= hi * 2) and not (lo == 0 and d["value"] <= hi * 2):
            continue                                 # impossible reading (e.g. Trident startup 0): skip
        t = d.get("trend")
        if t is None:
            dirn = "n/a"
        elif abs(t) < 0.02 * (hi - lo):
            dirn = "flat"
        else:
            dirn = "rising" if t > 0 else "falling"
        out[p] = (d["value"], dirn)
    return first, out


def parse_entry(f):
    t = f.read_text(errors="ignore")
    head, _, body = t.partition("\n---\n") if t.startswith("---") else ("", "", t)
    fp, meta = {}, {}
    for l in head.splitlines():
        m = FP.match(l)
        if m:
            fp[m.group(1)] = (float(m.group(2)), m.group(3))
        elif ":" in l and not l.startswith(" "):
            k, v = l.split(":", 1)
            meta[k.strip()] = v.strip()
    reply = body.split("## Joe's reply", 1)[1].strip() if "## Joe's reply" in body else ""
    return fp, meta, reply


def score(a, b, bnd):
    common = [p for p in a if p in b]
    if len(common) < 3:
        return None, 0
    total = 0.0
    for p in common:
        lo, hi = bnd.get(p, (0, 1))
        width = max(hi - lo, 1e-9)
        vsim = max(0.0, 1 - abs(a[p][0] - b[p][0]) / (0.5 * width))
        da, db = a[p][1], b[p][1]
        if "n/a" in (da, db):
            dsim = 0.5
        elif da == db:
            dsim = 1.0
        elif "flat" in (da, db):
            dsim = 0.5
        else:
            dsim = 0.0
        total += 0.5 * vsim + 0.5 * dsim
    return total / len(common), len(common)


def main():
    args = sys.argv[1:]
    top = 3
    if "--top" in args:
        i = args.index("--top"); top = int(args[i + 1]); del args[i:i + 2]
    report, logdir = args[0], Path(args[1])
    today, fp = today_fp(report)
    bnd = bands()

    print(f"FINGERPRINT for {today} (computed by script: copy exactly into today's entry)")
    print("fingerprint:")
    for p, (v, d) in fp.items():
        print(f"  {p}: {{value: {v:g}, trend_7d: {d}}}")

    entries = []
    for f in sorted(list(logdir.rglob("*-daily.md")) + list(logdir.rglob("*-history.md"))):
        d = f.name[:10]
        if d >= today:
            continue
        efp, meta, reply = parse_entry(f)
        entries.append((d, f, efp, meta, reply))

    scored = []
    for d, f, efp, meta, reply in entries:
        s, n = score(fp, efp, bnd)
        if s is not None:
            scored.append((s, n, d, f, meta, reply))
    scored.sort(key=lambda x: -x[0])

    print(f"\nLOOK-BACK: {len(entries)} past entries, {len(scored)} comparable")
    shown = [x for x in scored if x[0] >= 0.6][:top]
    if not shown:
        print("  no similar past day yet (score >= 0.60)")
    for s, n, d, f, meta, reply in shown:
        kind = " [backfilled numbers only]" if f.name.endswith("-history.md") else ""
        print(f"\n- {d} similarity {s:.2f} over {n} parameters{kind} ({f})")
        print(f"  status: {meta.get('status', '?')}; events: {meta.get('events', '[]')}"
              f"; observations: {meta.get('observations', '[]')}")
        if reply:
            print("  Joe then: " + " | ".join(l.strip() for l in reply.splitlines() if l.strip())[:400])
        after = [(d2, m2, r2) for d2, f2, e2, m2, r2 in entries
                 if d < d2 <= str(date.fromisoformat(d) + timedelta(days=14))]
        ev = [f"{d2}: {m2.get('events')}" for d2, m2, _ in after if m2.get("events") not in (None, "", "[]")]
        if ev:
            print("  in the 14 days after: " + "; ".join(ev)[:400])
        ob = [f"{d2}: {m2.get('observations')}" for d2, m2, _ in after if m2.get("observations") not in (None, "", "[]")]
        if ob:
            print("  observed in the 14 days after: " + "; ".join(ob)[:400])
    print("\nScores: 1.00 = same values and directions. Similar days are leads, not proof.")


if __name__ == "__main__":
    main()
