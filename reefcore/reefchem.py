#!/usr/bin/env python3
"""reefchem: LSSS (Apex) readings + hand tests -> SQLite -> report vs baselines.
  reefchem.py pull [--hours 26]          fetch ext_probe from the LSSS
  reefchem.py log alk 8.1 ca 430 mg 1350 [--note "text"]
  reefchem.py report                     plain-text summary (all math done here)
  reefchem.py wc [--minutes 120]         log a water change (temp excluded meanwhile)
"""
import argparse, csv, io, json, sqlite3, statistics, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

DATA = Path("/root/reef-lab/data")
DB = DATA / "reefchem.db"
BASELINES = DATA / "reef-baselines.md"
LSSS = "http://10.0.0.228:8000"
TRIDENT = {"Alkx5", "Cax5", "Mgx5"}   # Apex repeats the last test; count changes only
STALE_TEST_H = {"Alkx5": 12, "Cax5": 30, "Mgx5": 30}  # Trident runs alk 3x/day, Ca+Mg 1x/day; flag after ~1.5 missed runs
STALE_FEED_MIN = 60                    # no LSSS data for this long -> alert
WC_PROBE = "LvLSmp"                    # sump level; a drop marks a water change
WC_DROP = 0.4                          # this far below the 2 h median = water change
WC_TAIL = 3600                         # keep excluding this long after level recovers
WC_PARAMS = {"temp", "temp_hydros"}    # stats that skip water-change windows
HYDROS_DB = DATA / "hydros.db"           # output snapshots from hydros-pull.py
ALK_DOSE = (9, 45)                       # alk bolus start (h, m); pre-dose alk = last Trident result before it
LEVELS = {"1RSump Level LLS": "sump level", "200 Overflw LLS": "peninsula (200) overflow level",
          "Mixn Barrel LLS": "mixing barrel level"}
SWITCHES = {"1R SkimOverflow": "skimmer overflow", "1R Sump ATO": "sump ATO", "1R Sump Leak": "sump leak",
            "1R Sump Low WC": "sump low (WC)", "1RFliter Roller": "filter roller", "Mixn Water Low": "mixing water low"}
CHECK_IF_SET = {"1R SkimOverflow", "1R Sump Leak"}   # any 1 in 24 h -> CHECK line
OVERRIDE_H = 12                        # output in override longer than this -> listed
EXPECTED_OVERRIDES = DATA / "expected-overrides.txt"   # one output name per line: overrides that are normal
HAND = {"alk": "alk", "ca": "calc", "calc": "calc", "mg": "mag", "mag": "mag",
        "ph": "ph", "temp": "temp", "sal": "salinity", "no3": "no3", "po4": "po4"}
H, D = 3600, 86400


def baselines():
    out = {}
    if not BASELINES.exists():
        return out
    for line in BASELINES.read_text().splitlines():
        if not line.strip().startswith("|"):
            continue
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) != 5 or c[0] == "param" or set(c[0]) <= set("-: "):
            continue
        try:
            lo, hi = float(c[3]), float(c[4])
        except ValueError:
            continue
        probe, source = (None if c[1] in ("", "-") else c[1]), "apex"
        if probe and ":" in probe and probe.split(":", 1)[0] in ("apex", "hydros", "ghl"):
            source, probe = probe.split(":", 1)
        out[c[0]] = {"probe": probe, "source": source, "unit": c[2], "low": lo, "high": hi}
    return out


def age(s):
    return f"{s / H:.1f} h" if s < 2 * D else f"{s / D:.1f} d"


def series(db, param, source, since, until=None):
    return db.execute("SELECT ts, value FROM readings WHERE param=? AND source=? AND ts>=? AND ts<=? "
                      "ORDER BY ts", (param, source, since, until or 2**40)).fetchall()


def changes(pts):
    out = []
    for ts, v in pts:
        if not out or v != out[-1][1]:
            out.append((ts, v))
    return out


def num(x):
    return f"{x:.2f}".rstrip("0").rstrip(".")


def wc_events(db, since):
    pts = db.execute("SELECT ts, value FROM readings WHERE probe=? AND ts>=? ORDER BY ts",
                     (WC_PROBE, since - 2 * H)).fetchall()
    events = []
    for i, (ts, v) in enumerate(pts):
        prev = [x[1] for x in pts[max(0, i - 24):i]]
        if len(prev) >= 6 and v < statistics.median(prev) - WC_DROP:
            if events and ts - events[-1][1] <= 15 * 60:
                events[-1][1] = ts
            else:
                events.append([ts, ts])
    out = [(a - 300, b + WC_TAIL, "auto") for a, b in events]
    out += [(a, b, "logged") for a, b in db.execute(
        "SELECT ts, end_ts FROM events WHERE kind='wc' AND end_ts>=?", (since,))]
    return sorted(o for o in out if o[1] >= since)


def slope_per_day(pts, min_span=2 * D):
    if len(pts) < 3 or len({t for t, _ in pts}) < 2 or pts[-1][0] - pts[0][0] < min_span:
        return None
    return statistics.linear_regression([t / D for t, _ in pts], [v for _, v in pts]).slope


def predose(pts, now, days=7):
    """Last Trident alk change point before the bolus, per day (oldest first)."""
    out = []
    for back in range(days - 1, -1, -1):
        day = datetime.fromtimestamp(now - back * D)
        cut = int(day.replace(hour=ALK_DOSE[0], minute=ALK_DOSE[1], second=0).timestamp())
        if cut > now:
            continue
        before = [x for x in pts if cut - 16 * H <= x[0] < cut]
        if before:
            out.append((day.strftime("%m-%d"), before[-1][1]))
    return out


def levels(db, now):
    lines = []
    for probe, name in LEVELS.items():
        pts = db.execute("SELECT ts, value FROM readings WHERE probe=? AND source='hydros' AND ts>=? ORDER BY ts",
                         (probe, now - 7 * D)).fetchall()
        if not pts:
            continue
        day = [v for t, v in pts if t >= now - D]
        s = slope_per_day(pts)
        lines.append(f"  {name}: now {num(pts[-1][1])}"
                     + (f", 24h {num(min(day))} to {num(max(day))}" if day else "")
                     + (f", 7d trend {s:+.3f}/day" if s is not None else "") + " (raw sensor units)")
    if lines:
        print("\nLevels (Hydros):")
        print("\n".join(lines))


def switches(db, now):
    lines = []
    for probe, name in SWITCHES.items():
        pts = db.execute("SELECT ts, value FROM readings WHERE probe=? AND source='hydros' AND ts>=? ORDER BY ts",
                         (probe, now - D)).fetchall()
        if not pts:
            continue
        flips = sum(1 for a, b in zip(pts, pts[1:]) if a[1] != b[1])
        line = f"  {name}: now {num(pts[-1][1])}, {flips} changes in 24h"
        if probe in CHECK_IF_SET and any(v >= 1 for _, v in pts):
            line += "  CHECK: read 1 in the last 24h"
        lines.append(line)
    if lines:
        print("\nSwitches (Hydros; 1/0 as reported):")
        print("\n".join(lines))


def equipment(now):
    if not HYDROS_DB.exists():
        return
    h = sqlite3.connect(f"file:{HYDROS_DB}?mode=ro", uri=True)
    rows = h.execute("SELECT ts, device, name, state, watts, override, alert FROM outputs WHERE ts>=? "
                     "ORDER BY ts", (now - 7 * D,)).fetchall()
    if not rows:
        return
    by = {}
    for r in rows:
        by.setdefault(r[2], []).append(r)
    notes, flipped, expected = [], [], []
    try:
        ok_ovr = {l.strip() for l in EXPECTED_OVERRIDES.read_text().splitlines() if l.strip() and not l.startswith("#")}
    except OSError:
        ok_ovr = set()
    for name, rs in sorted(by.items()):
        ts, _, _, st, w, ovr, alert = rs[-1]
        span = now - rs[0][0]
        on_frac = sum(r[3] for r in rs) / len(rs)
        if alert:
            notes.append(f"  ALERT {name}: {alert}")
        if ovr:
            since = ts
            for r in reversed(rs):
                if not r[5]:
                    break
                since = r[0]
            if name in ok_ovr:
                expected.append(name)
            elif now - since >= OVERRIDE_H * H:
                notes.append(f"  {name}: in override ({'on' if st else 'off'}) for at least {age(now - since)}")
        if not st and span >= 12 * H and on_frac >= 0.95 and len(rs) >= 6:
            notes.append(f"  CHECK {name}: OFF now, normally on")
        day = [r for r in rs if r[0] >= now - D]
        flips = sum(1 for a, b in zip(day, day[1:]) if a[3] != b[3])
        if flips:
            flipped.append(f"{name} {flips}")
        ws = [r[4] for r in rs[:-1] if r[3] and r[4] is not None]
        steady = len(ws) >= 6 and statistics.fmean(ws) > 0 and statistics.pstdev(ws) / statistics.fmean(ws) < 0.15
        if st and w is not None and steady:
            med = statistics.median(ws)
            if med >= 5 and abs(w - med) > 0.3 * med:
                notes.append(f"  CHECK {name}: drawing {w:.1f} W vs usual {med:.1f} W")
    total = sum(r[-1][4] or 0 for r in by.values())
    print(f"\nEquipment (Hydros outputs; history since {datetime.fromtimestamp(rows[0][0]).strftime('%m-%d %H:%M')}):")
    print("\n".join(notes) if notes else "  all outputs as usual: nothing off, nothing stuck in override, no alerts")
    if expected:
        print(f"  expected overrides (per Joe): {', '.join(expected)}")
    if flipped:
        print(f"  on/off switches in 24h: {', '.join(flipped)}")
    print(f"  measured draw now {total:.0f} W")


def ingest_inbox(db):
    """Hand tests texted to the Reef Log bot (queued by mccrae tg.py). Rename first, then read: no lost lines."""
    inbox = DATA / "inbox" / "hand-tests.jsonl"
    if not inbox.exists():
        return 0
    work = inbox.with_name(f"processing-{int(time.time())}.jsonl")
    inbox.rename(work)
    n = 0
    for line in work.read_text().splitlines():
        try:
            r = json.loads(line)
            if r.get("kind") == "rodi":
                ts = int(r["ts"])
                db.execute("INSERT INTO events VALUES (?,?,?)", (ts, "rodi", ts))
                db.execute("INSERT INTO notes VALUES (?,?)", (ts, f"RO/DI added {float(r['gal']):g} gal"))
                n += 1
                continue
            if r.get("kind") == "wc":
                ts = int(r["ts"])
                db.execute("INSERT INTO events VALUES (?,?,?)", (ts, "wc", ts + 120 * 60))
                db.execute("INSERT INTO notes VALUES (?,?)", (ts, f"manual water change {float(r['gal']):g} gal"))
                n += 1
                continue
            db.execute("INSERT OR IGNORE INTO readings VALUES (?,?,?,?,?)",
                       (int(r["ts"]), "hand", "hand", r["param"], float(r["value"])))
            n += 1
        except (ValueError, KeyError):
            print(f"inbox: skipped bad line {line!r}")
    db.commit()
    done = DATA / "inbox" / "done"
    done.mkdir(exist_ok=True)
    work.rename(done / work.name)
    if n:
        print(f"inbox: {n} entries logged (hand tests / water changes)")
    return n


def maintenance(now):
    """Maintenance schedule + recent actions, so the log can tie physical work to sensor changes."""
    import re as _re
    from datetime import date as _date, timedelta as _td
    mfile, lfile = DATA / "maintenance.md", DATA / "maintenance-log.md"
    if not mfile.exists():
        return
    today = datetime.fromtimestamp(now).date()
    due, never = [], 0
    for l in mfile.read_text().splitlines():
        c = [x.strip() for x in l.strip().strip("|").split("|")]
        if len(c) < 6 or not _re.match(r"M\d+$", c[0]):
            continue
        every = int(_re.sub(r"\D", "", c[2]) or 0)
        if not every:
            continue
        if c[3] in ("", "-"):
            never += 1
            continue
        left = (_date.fromisoformat(c[3][:10]) + _td(days=every) - today).days
        if left < 0:
            due.append(f"  OVERDUE {c[1]}: {-left} days (last {c[3]})")
        elif left <= 7:
            due.append(f"  due soon {c[1]}: in {left} days")
    recent = []
    if lfile.exists():
        for l in lfile.read_text().splitlines():
            m = _re.match(r"^- (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) (M\d+) (.*)$", l)
            if m and _date.fromisoformat(m.group(1)) >= today - _td(days=14):
                recent.append(f"  {m.group(1)} {m.group(2)} {m.group(4)}")
    print("\nMaintenance (schedule in data/maintenance.md):")
    print("\n".join(due) if due else "  nothing overdue or due in 7 days")
    if never:
        print(f"  ({never} scheduled tasks never logged yet)")
    if recent:
        print("  done in the last 14 days (physical work can explain sensor changes):")
        print("\n".join(recent))


def jugs(now):
    """Dosing jug run-out forecast from data/recipes.md."""
    import re as _re
    from datetime import date as _date
    f = DATA / "recipes.md"
    if not f.exists():
        return
    today = datetime.fromtimestamp(now).date()
    out = []
    for l in f.read_text().splitlines():
        c = [x.strip() for x in l.strip().strip("|").split("|")]
        if len(c) < 7 or not _re.match(r"J\d+$", c[0]):
            continue
        try:
            jug, per, last = float(c[3]) * 1000, float(c[4]), _date.fromisoformat(c[5][:10])
        except ValueError:
            continue
        left = (jug - per * (today - last).days) / per
        tag = "EMPTY?" if left <= 0 else "MIX SOON" if left <= 3 else "ok"
        out.append(f"  {c[1]}: ~{left:.1f} days left ({tag}; mixed {c[5]}, {c[4]} ml/day)")
    print("\nDosing jugs (forecast):")
    print("\n".join(out) if out else "  no forecast yet (jug sizes / mix dates TBD in data/recipes.md)")


SYSTEM_L = 2800   # approx system water volume in litres (TBD, Joe to confirm)


def ph_bump(db, now, days=7):
    """pH rise after the 09:45 alk bolus: median 09:15-09:45 vs peak 09:45-12:30, per day and probe.
    Lights reach 100% ~30 min after the bolus, so part of the rise is photosynthesis; compare days, not absolutes."""
    import re as _re
    mixed = None
    f = DATA / "recipes.md"
    if f.exists():
        m = _re.search(r"^\|\s*J1\s*\|(?:[^|]*\|){4}\s*(\d{4}-\d{2}-\d{2})", f.read_text(), _re.M)
        mixed = m.group(1) if m else None
    rows = []
    for back in range(days - 1, -1, -1):
        day = datetime.fromtimestamp(now - back * D)
        t0 = int(day.replace(hour=ALK_DOSE[0], minute=ALK_DOSE[1], second=0, microsecond=0).timestamp())
        if t0 + 165 * 60 > now:
            continue
        cells = []
        for label, param, src in (("apex", "ph", "apex"), ("hydros", "ph_hydros", "hydros")):
            pre = [v for _, v in series(db, param, src, t0 - 30 * 60, t0 - 1)]
            post = series(db, param, src, t0, t0 + 165 * 60)
            if len(pre) >= 2 and len(post) >= 4:
                base = statistics.median(pre)
                pts, pv = max(post, key=lambda x: x[1])
                cells.append(f"{label} {base:.2f}->{pv:.2f} ({pv - base:+.2f}, peak {datetime.fromtimestamp(pts):%H:%M})")
        if cells:
            tag = "  [alk batch mixed this day]" if mixed and day.strftime("%Y-%m-%d") == mixed else ""
            rows.append(f"  {day:%m-%d}: " + "; ".join(cells) + tag)
    print("\npH bump after the 09:45 alk bolus (pre = 09:15-09:45 median, peak by 12:30; lights add some of this):")
    print("\n".join(rows) if rows else "  not enough pH data yet")
    if mixed:
        print(f"  current alk batch mixed {mixed} (compare days before/after)")


def ghl_flow(db, now):
    """GHL ProfiLux flow sensors (ghl-pull.py, L/h): now, 24h range, 7d median, drop flag. Labels in data/ghl-labels.txt."""
    labels = {}
    f = DATA / "ghl-labels.txt"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                labels[k.strip()] = v.strip()
    rows = []
    for i in range(4):
        k = f"ghl_flow{i}"
        pts = series(db, k, "ghl", now - 7 * D, now)
        if not pts:
            continue
        ts, v = pts[-1]
        day = [x for t2, x in pts if t2 >= now - D]
        med = statistics.median(x for _, x in pts)
        flag = ""
        if now - ts > 30 * 60:
            flag = f"  STALE ({age(now - ts)} old)"
        elif med > 50 and v < 0.8 * med:
            flag = f"  LOW: {v / med * 100:.0f}% of its 7d median"
        rows.append(f"  {labels.get(k, k)}: {v:g} L/h (~{v / 3.785:.0f} gal/h)"
                    + (f", 24h {min(day):g} to {max(day):g}" if day else "") + f", 7d median {med:g}" + flag)
    if rows:
        print("\nFlow (GHL ProfiLux flow sensors):")
        print("\n".join(rows))


def salinity_drift(db, now):
    """Salinity creep from 2-part/Balling residue vs RO/DI added (Joe logs 'added 10 gal rodi')."""
    import re as _re
    pts = series(db, "salinity", "hydros", now - 30 * D, now)
    rodi = [(ts, float(m.group(1))) for ts, note in db.execute(
        "SELECT ts, note FROM notes WHERE ts>=? AND note LIKE 'RO/DI added %' ORDER BY ts", (now - 30 * D,))
        for m in [_re.search(r"([\d.]+) gal", note)] if m]
    print("\nSalinity drift (Hydros daily medians; dosing residue pushes salinity up, RO/DI brings it down):")
    if not pts:
        print("  no Hydros salinity data in 30 days")
        return
    days = {}
    for ts, v in pts:
        days.setdefault(datetime.fromtimestamp(ts).date(), []).append(v)
    med = [(d, statistics.median(v)) for d, v in sorted(days.items()) if len(v) >= 3]
    if med:
        print("  daily: " + ", ".join(f"{d:%m-%d} {v:.2f}" for d, v in med[-7:]))
    cur = med[-1][1] if med else pts[-1][1]
    fine = []
    try:   # 15-second ATO runs from ato-watch.py (hydros.db), when available
        import importlib.util
        spec = importlib.util.spec_from_file_location("atow", "/opt/reefcore/ato-watch.py")
        atow = importlib.util.module_from_spec(spec); spec.loader.exec_module(atow)
        fine = atow.runs(now - 7 * D, now)
    except Exception:
        fine = []
    if fine:
        r24 = [r for r in fine if r[0] >= now - D]
        first = min(r[0] for r in fine)
        span = max(1.0, (now - first) / D)
        dips = []
        for a, b, s in fine:
            before = [v for ts, v in pts if a - 30 * 60 <= ts < a]
            after = [v for ts, v in pts if a <= ts <= (b or a) + 20 * 60]
            if before and after:
                dips.append(min(after) - statistics.median(before))
        print(f"  ATO top-off (15 s watcher): {len(r24)} runs, {sum(s for *_, s in r24) / 60:.1f} min total in 24h"
              + (f", typical run {statistics.median(s for *_, s in r24):.0f} s" if r24 else "")
              + (f"; {len(fine) / span:.1f} runs/day since {datetime.fromtimestamp(first):%m-%d}" if span > 1.5 else "")
              + (f"; salinity change right after a run: median {statistics.median(dips):+.2f} ppt (n={len(dips)})"
                 if len(dips) >= 3 else ""))
    ato = series(db, "1R Sump ATO", "hydros", now - 7 * D, now)
    calls = [ts for i, (ts, v) in enumerate(ato) if v == 0 and (i == 0 or ato[i - 1][1] != 0)]
    if ato and not fine:
        dips = []
        for c in calls:
            before = [v for ts, v in pts if c - 30 * 60 <= ts < c]
            after = [v for ts, v in pts if c <= ts <= c + 30 * 60]
            if before and after:
                dips.append(min(after) - statistics.median(before))
        print(f"  ATO top-off calls seen (1R Sump ATO low, 5-min snapshots, short runs missed): "
              f"{sum(1 for c in calls if c >= now - D)} in 24h, {len(calls) / 7:.1f}/day over 7d"
              + (f"; salinity change in the 30 min after a call: median {statistics.median(dips):+.2f} ppt "
                 f"(n={len(dips)})" if len(dips) >= 3 else ""))
    if rodi:
        tot = sum(g for _, g in rodi)
        print(f"  RO/DI logged in 30 days: {tot:g} gal in {len(rodi)} adds; last "
              f"{datetime.fromtimestamp(rodi[-1][0]):%m-%d} ({rodi[-1][1]:g} gal)")
        after = [(d, v) for d, v in med if datetime.combine(d, datetime.min.time()).timestamp() > rodi[-1][0]]
        if len(after) >= 2:
            print(f"  since that add: {after[0][1]:.2f} -> {after[-1][1]:.2f} "
                  f"({after[-1][1] - after[0][1]:+.2f} ppt over {(after[-1][0] - after[0][0]).days} days)")
    else:
        print("  no RO/DI adds logged in 30 days (text 'added 10 gal rodi' to log one)")
    since = rodi[-1][0] if rodi else 0
    seg = [(int(datetime.combine(d, datetime.min.time()).timestamp()), v) for d, v in med
           if datetime.combine(d, datetime.min.time()).timestamp() > since][-14:]
    s = slope_per_day(seg, min_span=4 * D) if len(seg) >= 5 else None
    if s is None:
        print("  trend: needs 5+ days of readings since the last RO/DI add")
        return
    hi = baselines().get("salinity", {}).get("high")
    line = f"  trend: {s * 7:+.2f} ppt/week"
    if s > 0:
        gal_wk = s * 7 / cur * SYSTEM_L / 3.785
        line += f"; about {gal_wk:.0f} gal RO/DI per week (as a saltwater swap) would hold it level"
        if hi and cur < hi:
            line += f"; reaches {hi:g} in ~{(hi - cur) / s:.0f} days at this rate"
    print(line)
    if hi and cur >= hi - 0.5:
        print(f"  NEAR HIGH: {cur:.2f} vs target top {hi:g}")


def pull(db, hours):
    url = f"{LSSS}/api/influx/export?measurements=ext_probe&hours={hours}&format=csv"
    with urllib.request.urlopen(url, timeout=300) as r:
        rows = list(csv.DictReader(io.StringIO(r.read().decode())))
    pmap = {b["probe"]: p for p, b in baselines().items() if b["probe"]}
    new = 0
    for row in rows:
        if row.get("field") != "value" or not row.get("source"):
            continue
        ts = int(datetime.fromisoformat(row["time"]).timestamp())
        probe = row["probe"]
        cur = db.execute("INSERT OR IGNORE INTO readings VALUES (?,?,?,?,?)",
                         (ts, row["source"], probe, pmap.get(probe, probe), float(row["value"])))
        new += cur.rowcount
    for probe, p in pmap.items():
        if probe != p:
            db.execute("UPDATE OR IGNORE readings SET param=? WHERE probe=? AND param=? AND source!='hand'", (p, probe, probe))
            db.execute("DELETE FROM readings WHERE probe=? AND param=? AND source!='hand'", (probe, probe))
    db.commit()
    print(f"pulled {len(rows)} rows, {new} new")


def log(db, pairs, note):
    if len(pairs) % 2:
        sys.exit("usage: log alk 8.1 ca 430 ...")
    ts, bl = int(time.time()), baselines()
    for k, v in zip(pairs[::2], pairs[1::2]):
        p = HAND.get(k.lower())
        if not p:
            sys.exit(f"unknown parameter '{k}' (known: {', '.join(sorted(HAND))})")
        try:
            val = float(v)
        except ValueError:
            sys.exit(f"'{v}' is not a number")
        b = bl.get(p)
        if b and not (b["low"] * 0.5 <= val <= b["high"] * 2):
            print(f"warning: {p} {val:g} is far outside {b['low']:g}-{b['high']:g}; logged anyway")
        db.execute("INSERT INTO readings VALUES (?,?,?,?,?)", (ts, "hand", "hand", p, val))
    if note:
        db.execute("INSERT INTO notes VALUES (?,?)", (ts, note))
    db.commit()
    print("logged")


def report(db, asof=None):
    now, bl = int(asof or time.time()), baselines()
    print(f"Reef data summary {datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M')} "
          "(numbers computed by script; quote them, do not recompute)")
    if not bl:
        print(f"ALERT: no baselines file at {BASELINES}")
    last = db.execute("SELECT MAX(ts) FROM readings WHERE source='apex'").fetchone()[0]
    if not last or now - last > STALE_FEED_MIN * 60:
        print(f"ALERT: no LSSS/Apex data for {age(now - last) if last else 'ever'}")
    lasth = db.execute("SELECT MAX(ts) FROM readings WHERE source='hydros'").fetchone()[0]
    if lasth and now - lasth > STALE_FEED_MIN * 60:
        print(f"ALERT: no Hydros data for {age(now - lasth)} (refresh the Hydros feed on the LSSS)")
    wcs = wc_events(db, now - 30 * D)
    in_wc = lambda t: any(a <= t <= b2 for a, b2, _ in wcs)
    for p, b in bl.items():
        print(f"\n{p} ({b['unit']}), target {b['low']:g}-{b['high']:g}:")
        if b["probe"]:
            src = b.get("source", "apex")
            pts = series(db, p, src, now - 30 * D, now)
            trident = b["probe"] in TRIDENT
            if trident:
                pts = changes(pts)
            dropped = 0
            if p in WC_PARAMS:
                kept = [x for x in pts if not in_wc(x[0])]
                dropped, pts = len(pts) - len(kept), kept
            if not pts:
                print(f"  {src}: no data in 30 days")
            else:
                ts, v = pts[-1]
                flag = "LOW" if v < b["low"] else "HIGH" if v > b["high"] else "in range"
                what = "last new test result" if trident else "latest"
                print(f"  {src} {what}: {num(v)} ({flag}), {age(now - ts)} ago")
                if trident and now - ts > STALE_TEST_H[b["probe"]] * H:
                    print(f"  STALLED?: no changed Trident result in {age(now - ts)}")
                if b["probe"] == "Alkx5":
                    pre = predose(pts, now)
                    if pre:
                        print("  pre-dose alk (last result before the 09:45 bolus): "
                              + ", ".join(f"{d} {num(v)}" for d, v in pre))
                p7 = [x for x in pts if x[0] >= now - 7 * D]
                if p7:
                    vals = [x[1] for x in p7]
                    s = slope_per_day(p7)
                    print(f"  7d: mean {statistics.fmean(vals):.2f}, min {num(min(vals))}, max {num(max(vals))}"
                          + (f", trend {s:+.3f}/day" if s is not None else "") + f", n={len(vals)}")
                print(f"  30d: mean {statistics.fmean(x[1] for x in pts):.2f}, n={len(pts)}")
                if dropped:
                    print(f"  ({dropped} readings during water changes left out of these stats)")
                if not trident:
                    day = [x[1] for x in pts if x[0] >= now - D]
                    if day:
                        print(f"  24h range: {num(min(day))} to {num(max(day))}")
        hand = series(db, p, "hand", now - 90 * D)
        if hand:
            ts, v = hand[-1]
            line = f"  hand test: {v:g}, {age(now - ts)} ago"
            if b["probe"]:
                ref = db.execute("SELECT value FROM readings WHERE param=? AND source=? AND ts<=? "
                                 "ORDER BY ts DESC LIMIT 1", (p, b.get("source", "apex"), ts)).fetchone()
                if ref:
                    diff = v - ref[0]
                    line += f"; {b.get('source', 'apex')} then {ref[0]:g}, diff {diff:+.2f}"
                    if abs(diff) > 0.25 * (b["high"] - b["low"]):
                        line += "  CHECK CALIBRATION"
            print(line)
    levels(db, now)
    switches(db, now)
    equipment(now)
    maintenance(now)
    jugs(now)
    ph_bump(db, now)
    ghl_flow(db, now)
    salinity_drift(db, now)
    recent = [w for w in wcs if w[1] >= now - 7 * D]
    if recent:
        print("\nWater changes (7d; temp in these windows left out):")
        for a, b2, how in recent:
            print(f"  {datetime.fromtimestamp(a).strftime('%m-%d %H:%M')} to "
                  f"{datetime.fromtimestamp(b2).strftime('%H:%M')} ({how})")
    notes = db.execute("SELECT ts, note FROM notes WHERE ts>=? ORDER BY ts", (now - 7 * D,)).fetchall()
    if notes:
        print("\nJoe's notes (7d):")
        for ts, n in notes:
            print(f"  {datetime.fromtimestamp(ts).strftime('%m-%d')}: {n}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pull").add_argument("--hours", type=int, default=26)
    lg = sub.add_parser("log")
    lg.add_argument("pairs", nargs="+")
    lg.add_argument("--note")
    sub.add_parser("report").add_argument("--asof", help="'YYYY-MM-DD HH:MM': report as of then (backfill)")
    sub.add_parser("wc").add_argument("--minutes", type=int, default=120)
    a = ap.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB)
    db.execute("CREATE TABLE IF NOT EXISTS readings (ts INT, source TEXT, probe TEXT, param TEXT, "
               "value REAL, UNIQUE(ts, source, probe, param))")
    db.execute("CREATE TABLE IF NOT EXISTS notes (ts INT, note TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS events (ts INT, kind TEXT, end_ts INT)")
    if a.cmd == "pull":
        ingest_inbox(db)
        pull(db, a.hours)
    elif a.cmd == "log":
        log(db, a.pairs, a.note)
    elif a.cmd == "wc":
        t = int(time.time())
        db.execute("INSERT INTO events VALUES (?,?,?)", (t, "wc", t + a.minutes * 60))
        db.commit()
        print(f"water change logged; temp left out of stats for {a.minutes} min")
    else:
        report(db, datetime.strptime(a.asof, "%Y-%m-%d %H:%M").timestamp() if a.asof else None)


if __name__ == "__main__":
    main()
