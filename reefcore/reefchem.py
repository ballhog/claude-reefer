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
            if r.get("kind") == "event":          # e.g. fed (evening check-in); shows on history charts
                ts = int(r["ts"])
                ev = str(r["event"])[:20]
                db.execute("INSERT INTO events VALUES (?,?,?)", (ts, ev, ts))
                db.execute("INSERT INTO notes VALUES (?,?)", (ts, str(r.get("note") or ev)[:200]))
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


def _last_done():
    """Last-done date per maintenance task id (from data/maintenance.md), as epoch seconds or None."""
    import re as _re
    out = {}
    try:
        for l in (DATA / "maintenance.md").read_text().splitlines():
            c = [x.strip() for x in l.strip().strip("|").split("|")]
            if len(c) >= 4 and _re.match(r"M\d+$", c[0]):
                out[c[0]] = (datetime.fromisoformat(c[3][:10]).timestamp() if c[3] not in ("", "-") else None)
    except (OSError, ValueError):
        pass
    return out


def data_due(db, now):
    """Maintenance signals from the sensors, alongside the calendar (Group 1, 2026-10-12).
    Returns {task_id: {"level": "overdue"|"due"|"info", "short": str, "reason": str}}. Script arithmetic only."""
    import statistics as _st
    last = _last_done()
    out = {}
    # M04 return pumps: each line's 24 h median vs its level in the 3 days after the last cleaning
    names = {"ghl_flow0": "320 return", "ghl_flow2": "200 return A", "ghl_flow3": "200 return B"}
    worst, parts = None, []
    for p, name in names.items():
        day = [v for _, v in series(db, p, "ghl", now - D)]
        if len(day) < 12:
            continue
        cur = _st.median(day)
        t0 = last.get("M04")
        if t0 and now - t0 > 3 * D:
            base_pts = [v for _, v in series(db, p, "ghl", int(t0), int(t0 + 3 * D))]
            base, how = (_st.median(base_pts), "after the last cleaning") if len(base_pts) >= 12 else (None, "")
        else:
            base, how = None, ""
        if base is None:                                  # no cleaning logged yet: best daily median of 30 days
            byday = {}
            for t, v in series(db, p, "ghl", now - 30 * D):
                byday.setdefault(t // D, []).append(v)
            meds = [_st.median(v) for v in byday.values() if len(v) >= 12]
            if not meds:
                continue
            base, how = max(meds), "best day in 30 days"
        if base <= 0:
            continue
        pct = cur / base * 100
        parts.append(f"{name} {cur:.0f} L/h = {pct:.0f}% of {base:.0f} ({how})")
        drop = 100 - pct
        lvl = "overdue" if drop >= 20 else "due" if drop >= 10 else "info"
        if worst is None or ["info", "due", "overdue"].index(lvl) > ["info", "due", "overdue"].index(worst[0]):
            worst = (lvl, f"{name} flow down {drop:.0f}%")
    if worst:
        out["M04"] = {"level": worst[0], "short": worst[1] if worst[0] != "info" else "flows normal",
                      "reason": "; ".join(parts)}

    def trips(param, since):
        pts = series(db, param, "hydros", since)
        n, prev = 0, None
        for _, v in pts:
            on = v >= 0.5
            if on and prev is False:
                n += 1
            prev = on
        return n, (pts[-1][1] >= 0.5 if pts else None)

    # M01 skimmer cup: the cup-full sensor tripped since the last cleaning (or in 7 days)
    since = max(now - 7 * D, int(last.get("M01") or 0))
    n, now_on = trips("1R SkimOverflow", since)
    if n or now_on:
        out["M01"] = {"level": "due", "short": "cup-full sensor tripped" if n else "cup-full sensor on",
                      "reason": f"Hydros '1R SkimOverflow' tripped {n} time(s) since {datetime.fromtimestamp(since):%m-%d}"
                                + (" and is on now" if now_on else "")}
    else:
        out["M01"] = {"level": "info", "short": "cup sensor quiet", "reason": "cup-full sensor has not tripped in 7 days"}
    # M02 filter roller: chamber overfill sensor (roll out or jammed)
    since = max(now - 7 * D, int(last.get("M02") or 0))
    n, now_on = trips("1RFliter Roller", since)
    if n or now_on:
        out["M02"] = {"level": "due", "short": "roller chamber overfill",
                      "reason": f"Hydros '1RFliter Roller' (chamber overfill) tripped {n} time(s) in 7 days"
                                + (" and is on now" if now_on else "") + ": roll may be out or jammed"}
    # M14 DI resin: product TDS (Hydros), the high end of the last 3 days of readings above 0
    tds = sorted(v for _, v in series(db, "tds", "hydros", now - 3 * D) if v > 0)
    if tds:
        hi = tds[int(len(tds) * .95) - 1 if len(tds) > 1 else 0]
        lvl = "overdue" if hi >= 5 else "due" if hi >= 1 else "info"
        x = {"level": lvl, "short": f"TDS {hi:.0f} ppm", "reason": f"product water TDS up to {hi:.1f} ppm in 3 days (resin is spent above 0-1; test between stages to find which)"}
    else:
        x = {"level": "info", "short": "TDS 0 ppm", "reason": "product water TDS reads 0 ppm (last 3 days)"}
    for k in ("M14", "M22", "M23"):        # cation, anion x2, mixed-bed DI x2 (one TDS meter after the last stage)
        out[k] = dict(x)
    return out


def data_due_report(db, now):
    try:
        dd = data_due(db, now)
    except Exception as e:
        print(f"\nDue by data: unavailable ({e})")
        return
    hot = [(k, v) for k, v in sorted(dd.items()) if v["level"] != "info"]
    print("\nDue by data (sensor signals, alongside the calendar):")
    if hot:
        for k, v in hot:
            print(f"  {v['level'].upper()} {k}: {v['short']} ({v['reason']})")
    else:
        print("  nothing flagged by sensors")
    if "M04" in dd and dd["M04"]["level"] == "info":
        print(f"  return pumps: {dd['M04']['reason']}")


def _num(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def supplies(now=None):
    """Supplies on hand -> days left and order-by date (Group 2, 2026-10-12). data/supplies.md; daily use from
    the recipe (per_batch over a full jug at that jug's ml/day) or a typed use_per_day. Script arithmetic only."""
    from datetime import date as _date, timedelta as _td
    today = datetime.fromtimestamp(now or time.time()).date()
    jugs = {}
    try:
        for l in (DATA / "recipes.md").read_text().splitlines():
            c = [x.strip() for x in l.strip().strip("|").split("|")]
            if len(c) >= 6 and c[0][:1] == "J" and c[0][1:].isdigit():
                jugs[c[0]] = (_num(c[3]), _num(c[4]))
    except OSError:
        pass
    out = []
    try:
        lines = (DATA / "supplies.md").read_text().splitlines()
    except OSError:
        return out
    for l in lines:
        c = [x.strip() for x in l.strip().strip("|").split("|")]
        if len(c) < 11 or not (c[0][:1] == "S" and c[0][1:].isdigit()):
            continue
        sid, item, unit, on, upd, per, jug, typed, pack, lead = c[:10]
        use = None
        jl, ml = jugs.get(jug, (None, None))
        if _num(per) and jl and ml:
            use = _num(per) * ml / (jl * 1000)
        elif _num(typed):
            use = _num(typed)
        r = {"id": sid, "item": item, "unit": unit, "use_per_day": round(use, 2) if use else None,
             "lead_days": int(_num(lead) or 7), "pack": _num(pack), "aliases": c[10], "on_hand": None,
             "days_left": None, "order_by": None, "state": "unknown"}
        onv = _num(on)
        if onv is not None:
            try:
                since = (today - _date.fromisoformat(upd[:10])).days
            except ValueError:
                since = 0
            r["on_hand"] = round(max(0.0, onv - (use or 0) * since), 1)
            if use:
                r["days_left"] = round(r["on_hand"] / use, 1)
                r["order_by"] = (today + _td(days=max(0, int(r["days_left"]) - r["lead_days"] - 14))).isoformat()
                r["state"] = ("order" if r["days_left"] <= r["lead_days"] + 14 else
                              "soon" if r["days_left"] <= r["lead_days"] + 30 else "ok")
            else:
                r["state"] = "no-use"
        out.append(r)
    return out


def supplies_report(now):
    try:
        sp = supplies(now)
    except Exception as e:
        print(f"\nSupplies: unavailable ({e})")
        return
    if not sp:
        return
    print("\nSupplies (data/supplies.md; days left at the current dose rates):")
    for r in sp:
        if r["days_left"] is not None:
            flag = {"order": "ORDER NOW", "soon": "order soon"}.get(r["state"], "")
            print(f"  {r['item']}: {r['on_hand']:g} {r['unit']} = {r['days_left']:.0f} days"
                  + (f" -> {flag} (order by {r['order_by']})" if flag else ""))
    unknown = [r["item"] for r in sp if r["on_hand"] is None]
    if unknown:
        print(f"  count needed: {', '.join(unknown)}")



# ---------- the tank's normal day (Group 3, 2026-10-12) ----------
# Half-hour profiles per sensor from the last 21 days (p10 / median / p90 for each time of day), "off-pattern"
# flags when the last 2 h sit outside that band, and one row of daily numbers per day kept forever.
PROFILE = [("temp", "apex", "Apex temp", "C"), ("ph", "apex", "pH (Apex)", ""), ("ph_hydros", "hydros", "pH (Hydros)", ""),
           ("salinity", "hydros", "salinity", "ppt"), ("temp_hydros", "hydros", "sump temp", "C"),
           ("temp_ghl", "ghl", "tank temp (GHL)", "C"), ("temp_200", "ghl", "200 temp", "C"),
           ("ghl_flow0", "ghl", "320 return", "L/h"), ("ghl_flow2", "ghl", "200 return A", "L/h"),
           ("ghl_flow3", "ghl", "200 return B", "L/h"), ("room_temp_ghl", "ghl", "room temp", "C"),
           ("humidity", "ghl", "room humidity", "%")]
SLOT = 1800
PROFILES_FILE = DATA / "profiles.json"


def _slot(t):
    lt = time.localtime(t)
    return (lt.tm_hour * 3600 + lt.tm_min * 60) // SLOT


def build_profiles(db, now, days=21):
    since, until = now - days * D, now - 6 * H          # the last 6 h never judge themselves
    wcs = wc_events(db, since)
    out = {}
    for p, src, name, unit in PROFILE:
        pts = series(db, p, src, since, until)
        if p in WC_PARAMS:
            pts = [x for x in pts if not any(a <= x[0] <= b for a, b, _ in wcs)]
        by, seen = {}, {}
        for t, v in pts:
            k = _slot(t)
            by.setdefault(k, []).append(v)
            seen.setdefault(k, set()).add(time.localtime(t).tm_yday)
        slots = {}
        for k, vs in by.items():
            if len(seen[k]) < 5:                          # at least 5 different days for this time of day
                continue
            vs.sort()
            n = len(vs)
            q = lambda f: vs[min(n - 1, int(f * (n - 1) + .5))]
            slots[str(k)] = [round(q(.1), 4), round(q(.5), 4), round(q(.9), 4)]
        if len(slots) >= 36:
            out[p] = {"src": src, "name": name, "unit": unit, "days": days, "slots": slots}
    return out


def profiles(db=None, now=None, max_age=3600):
    now = int(now or time.time())
    j = None
    try:
        j = json.loads(PROFILES_FILE.read_text())
        if now - j["built"] < max_age or db is None:
            return j["p"]
    except (OSError, ValueError, KeyError):
        if db is None:
            return {}
    p = build_profiles(db, now)
    tmp = PROFILES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"built": now, "p": p}))
    tmp.replace(PROFILES_FILE)
    return p


def off_pattern(db, now, prof=None):
    """Sensors whose last 2 h sit mostly outside their normal band for those times of day."""
    prof = prof if prof is not None else profiles()
    out = []
    for p, pr in prof.items():
        pts = series(db, p, pr["src"], now - 2 * H, now)
        if len(pts) < 8 or now - pts[-1][0] > 45 * 60:
            continue
        hi_n = lo_n = n = 0
        devs = []
        for t, v in pts:
            b = pr["slots"].get(str(_slot(t)))
            if not b:
                continue
            w = max(b[2] - b[0], abs(b[1]) * .005, 1e-6)
            n += 1
            if v > b[2] + .25 * w:
                hi_n += 1
            elif v < b[0] - .25 * w:
                lo_n += 1
            devs.append(v - b[1])
        if n < 8:
            continue
        for cnt, d in ((hi_n, "above"), (lo_n, "below")):
            if cnt / n >= .75:
                devs.sort()
                out.append({"p": p, "name": pr["name"], "unit": pr["unit"], "dir": d,
                            "now": round(pts[-1][1], 3), "dev": round(devs[len(devs) // 2], 3)})
    return out


def _q(vs, f):
    vs = sorted(vs)
    return vs[min(len(vs) - 1, int(f * (len(vs) - 1) + .5))] if vs else None


def daily_numbers(db, day):
    """One day's numbers (local date 'YYYY-MM-DD') -> {metric: value}."""
    t0 = int(datetime.fromisoformat(day).timestamp())
    t1 = t0 + D
    wcs = wc_events(db, t0)
    out = {}
    for p, src, key in (("ph", "apex", "ph_swing"), ("ph_hydros", "hydros", "ph_hydros_swing"),
                        ("temp", "apex", "temp_swing"), ("temp_hydros", "hydros", "temp_hydros_swing")):
        vs = [v for t, v in series(db, p, src, t0, t1) if not (p.startswith("temp") and any(a <= t <= b for a, b, _ in wcs))]
        if len(vs) >= 48:
            out[key] = round(_q(vs, .95) - _q(vs, .05), 3)
    sal = series(db, "salinity", "hydros", t0, t1)
    if len(sal) >= 48:
        out["sal_median"] = round(_q([v for _, v in sal], .5), 3)
        first = [v for t, v in sal if t < t0 + 3 * H]
        last = [v for t, v in sal if t >= t1 - 3 * H]
        if len(first) >= 6 and len(last) >= 6:
            out["sal_drift"] = round(_q(last, .5) - _q(first, .5), 3)
    for i, key in ((0, "flow320_med"), (2, "flowA_med"), (3, "flowB_med")):
        vs = [v for _, v in series(db, f"ghl_flow{i}", "ghl", t0, t1)]
        if len(vs) >= 24:
            out[key] = round(_q(vs, .5), 1)
    try:
        h = sqlite3.connect(f"file:{DATA / 'hydros.db'}?mode=ro", uri=True, timeout=10)
        n = h.execute("SELECT COUNT(*) FROM ato WHERE value=1 AND ts>=? AND ts<?", (t0, t1)).fetchone()[0]
        if h.execute("SELECT COUNT(*) FROM ato WHERE ts>=? AND ts<?", (t0 - D, t1)).fetchone()[0]:
            out["ato_runs"] = n
        w = [x for (x,) in h.execute("SELECT watts FROM outputs WHERE name='Skimmer' AND state=1 AND watts IS NOT NULL "
                                     "AND ts>=? AND ts<?", (t0, t1))]
        if w:
            out["skimmer_w"] = round(_q(w, .5), 1)
        h.close()
    except Exception:
        pass
    return out


DAILY_NAMES = {"ph_swing": ("pH swing per day (Apex)", ""), "ph_hydros_swing": ("pH swing per day (Hydros)", ""),
               "temp_swing": ("temp swing per day (Apex)", "C"), "temp_hydros_swing": ("sump temp swing per day", "C"),
               "sal_median": ("salinity, daily median", "ppt"), "sal_drift": ("salinity drift per day", "ppt"),
               "flow320_med": ("320 return, daily median", "L/h"), "flowA_med": ("200 return A, daily median", "L/h"),
               "flowB_med": ("200 return B, daily median", "L/h"), "ato_runs": ("ATO runs per day", ""),
               "skimmer_w": ("skimmer watts, daily median", "W")}


def update_daily(db, now=None, full=False):
    """Fill the daily table: every missing day since the data starts (first run), then yesterday and today."""
    db.execute("CREATE TABLE IF NOT EXISTS daily (day TEXT, metric TEXT, value REAL, PRIMARY KEY(day, metric))")
    now = int(now or time.time())
    today = datetime.fromtimestamp(now).date()
    have = {d for (d,) in db.execute("SELECT DISTINCT day FROM daily")}
    first = db.execute("SELECT MIN(ts) FROM readings WHERE source='apex'").fetchone()[0]
    days = []
    if first:
        d = datetime.fromtimestamp(first).date()
        while d <= today:
            if full or str(d) not in have or (today - d).days <= 1:
                days.append(str(d))
            d = d.fromordinal(d.toordinal() + 1)
    for d in days:
        for k, v in daily_numbers(db, d).items():
            db.execute("INSERT OR REPLACE INTO daily VALUES (?,?,?)", (d, k, v))
    db.commit()
    return len(days)


def normal_day_report(db, now):
    try:
        prof = profiles(db, now)
        off = off_pattern(db, now, prof)
    except Exception as e:
        print(f"\nNormal day: unavailable ({e})")
        return
    print(f"\nNormal day (half-hour profiles from the last 21 days; {len(prof)} sensors):")
    if off:
        for o in off:
            print(f"  OFF-PATTERN {o['name']}: {o['now']:g} {o['unit']}, {o['dir']} its normal range for this time of day "
                  f"(median {o['dev']:+g} {o['unit']} vs normal)")
    else:
        print("  every sensor is following its normal daily curve")
    try:
        today = str(datetime.fromtimestamp(now).date())
        rows = {}
        for d, k, v in db.execute("SELECT day, metric, value FROM daily WHERE day >= ?",
                                  (str(datetime.fromtimestamp(now - 15 * D).date()),)):
            rows.setdefault(k, {})[d] = v
        lines = []
        for k in ("ph_swing", "ph_hydros_swing", "temp_swing", "ato_runs", "sal_drift", "skimmer_w"):
            r = rows.get(k, {})
            past = [v for d, v in r.items() if d < today]
            yday = r.get(str(datetime.fromtimestamp(now - D).date()))
            if yday is None or len(past) < 5:
                continue
            lines.append(f"  {DAILY_NAMES[k][0]}: yesterday {yday:g}, 14-day median {_q(past, .5):g}")
        if lines:
            print("  daily numbers (kept forever in the daily table):")
            print("\n".join(lines))
    except Exception:
        pass



# ---------- before/after for every event (Group 3, 2026-10-12) ----------
# Each event (maintenance, jug mixed, water change, RO/DI, fed, dose-rate change, reef-log event) is compared:
# the 24 h before vs 1-25 h after and 1-73 h after. A move only counts if it is bigger than the normal
# day-to-day wobble of that sensor (2 x the spread of consecutive daily medians over 30 days) and a floor.
# Wording everywhere: timing, not proof.
EFFECT_PARAMS = [("ph", "apex", "pH", "", .03), ("ph_hydros", "hydros", "pH (Hydros)", "", .03),
                 ("temp", "apex", "temp", "C", .15), ("salinity", "hydros", "salinity", "ppt", .15),
                 ("ghl_flow0", "ghl", "320 return", "L/h", 15), ("ghl_flow2", "ghl", "200 return A", "L/h", 10),
                 ("ghl_flow3", "ghl", "200 return B", "L/h", 10), ("alk", "apex", "alk", "dKH", .25),
                 ("calc", "apex", "Ca", "ppm", 8), ("mag", "apex", "Mg", "ppm", 20)]
EFFECTS_FILE = DATA / "event-effects.json"
SNAP_FILE = DATA / "recipes-snapshot.json"


def collect_events(db, since):
    """[{key, ts, kind, label, task}] from every place Joe's actions are recorded."""
    import re as _re
    ev = []
    try:
        for l in (DATA / "maintenance-log.md").read_text().splitlines():
            m = _re.match(r"^- (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) (?:([MJ]\d+) )?(.*)$", l.strip())
            if not m:
                continue
            t = int(datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").timestamp())
            if t >= since:
                task = m.group(2) or ""
                kind = "mix" if task.startswith("J") else "maint"
                ev.append({"key": f"{kind}:{t}:{task}", "ts": t, "kind": kind, "task": task,
                           "label": m.group(3).split(":")[0][:70]})
    except OSError:
        pass
    for t, k in db.execute("SELECT ts, kind FROM events WHERE ts>=? AND kind IN ('wc','rodi','fed','dose')", (since,)):
        ev.append({"key": f"{k}:{t}", "ts": t, "kind": k, "task": "",
                   "label": {"wc": "water change", "rodi": "RO/DI added", "fed": "fed", "dose": "dose change"}.get(k, k)})
    try:                                                   # events Claude Reefer noted in the daily log
        for f in sorted((DATA.parent / "log").glob("*/*/*-daily.md")):
            day = f.name[:10]
            t = int(datetime.fromisoformat(day).timestamp())
            if t < since:
                continue
            m = _re.search(r"^events:\s*\[(.*)\]\s*$", f.read_text()[:3000], _re.M)
            parts, depth, cur = [], 0, ""
            for ch in (m.group(1) if m else ""):
                depth += ch == "(" and 1 or ch == ")" and -1 or 0
                if ch == ";" and depth == 0:
                    parts.append(cur); cur = ""
                else:
                    cur += ch
            parts.append(cur)
            for e in [x.strip().strip('"') for x in parts if x.strip()]:
                if e and "override" not in e and "maintenance-log" not in e:
                    ev.append({"key": f"log:{day}:{e[:40]}", "ts": t - 12 * 3600, "kind": "log", "task": "",
                               "label": e[:90] + " (from the reef log; time approximate)"})
    except OSError:
        pass
    try:                                                   # dose-rate changes (recipes.md ml/day, snapshot diff)
        for l in SNAP_FILE.read_text().splitlines()[1:]:
            pass
    except OSError:
        pass
    try:
        for j in json.loads((DATA / "dose-changes.json").read_text()):
            if j["ts"] >= since:
                ev.append({"key": f"dose:{j['ts']}:{j['id']}", "ts": j["ts"], "kind": "dose", "task": j["id"], "label": j["label"]})
    except (OSError, ValueError, KeyError):
        pass
    return sorted(ev, key=lambda e: e["ts"])


def track_dose_changes(now=None):
    """Snapshot ml/day per jug; record a dose-change event when it differs from the last snapshot."""
    now = int(now or time.time())
    cur = {}
    try:
        for l in (DATA / "recipes.md").read_text().splitlines():
            c = [x.strip() for x in l.strip().strip("|").split("|")]
            if len(c) >= 6 and c[0][:1] == "J" and c[0][1:].isdigit():
                cur[c[0]] = (c[1].split(" (")[0], c[4])
    except OSError:
        return
    try:
        old = json.loads(SNAP_FILE.read_text())
    except (OSError, ValueError):
        old = None
    if old is not None:
        f = DATA / "dose-changes.json"
        try:
            ch = json.loads(f.read_text())
        except (OSError, ValueError):
            ch = []
        for k, (name, ml) in cur.items():
            if k in old and old[k][1] != ml:
                ch.append({"ts": now, "id": k, "label": f"{name} dose {old[k][1]} -> {ml} ml/day"})
        f.write_text(json.dumps(ch[-500:], indent=1))
    SNAP_FILE.write_text(json.dumps(cur))


def _daily_wobble(db, p, src, now):
    """Typical day-to-day change of the daily median (median absolute consecutive difference, last 30 days)."""
    by = {}
    for t, v in series(db, p, src, now - 31 * D, now):
        by.setdefault(time.localtime(t).tm_yday, []).append(v)
    meds = [_q(v, .5) for k, v in sorted(by.items()) if len(v) >= 12]
    diffs = sorted(abs(a - b) for a, b in zip(meds, meds[1:]))
    return diffs[len(diffs) // 2] if len(diffs) >= 5 else None


def event_effects(db, ev, now, wob=None):
    t = ev["ts"]
    out = {"24": None, "72": None}
    wob = wob or {}
    for win in ("24", "72"):
        end = t + (25 if win == "24" else 73) * H
        if end > now:
            continue
        found = []
        for p, src, name, unit, floor in EFFECT_PARAMS:
            if p in ("alk", "calc", "mag"):
                # Trident tests follow the daily dose cycle (the 12:45 alk test is always ~1 dKH higher), so compare
                # every test in the 24 h before with every test after: whole cycles on both sides.
                ch = changes(series(db, p, src, t - 8 * D, end))
                before = [v for x, v in ch if t - 24 * H <= x < t]
                after = [v for x, v in ch if t + H < x <= end]
                if len(before) < 3 or len(after) < 3:
                    continue
            else:
                pts = series(db, p, src, t - 25 * H, end)
                before = [v for x, v in pts if t - 24 * H <= x < t]
                after = [v for x, v in pts if t + H < x <= end]
                if len(before) < 12 or len(after) < 12:
                    continue
            d = _q(after, .5) - _q(before, .5)
            w = wob.get(p)
            lim = max(floor, 2 * w) if w else floor * 1.5
            if abs(d) >= lim:
                found.append({"p": p, "name": name, "unit": unit, "delta": round(d, 3), "limit": round(lim, 3)})
        out[win] = found
    return out


def update_effects(db, now=None, days=60):
    """Compute before/after for events whose windows have completed; keep results in event-effects.json."""
    now = int(now or time.time())
    try:
        store = json.loads(EFFECTS_FILE.read_text())
    except (OSError, ValueError):
        store = {}
    wob = {}
    for p, src, *_ in EFFECT_PARAMS:
        if p not in ("alk", "calc", "mag"):
            w = _daily_wobble(db, p, src, now)
            if w is not None:
                wob[p] = w
    for ev in collect_events(db, now - days * D):
        old = store.get(ev["key"])
        if old and old.get("72") is not None:
            continue
        if ev["ts"] + 25 * H > now:
            continue
        r = event_effects(db, ev, now, wob)
        store[ev["key"]] = {**ev, **r}
    tmp = EFFECTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(store, indent=1))
    tmp.replace(EFFECTS_FILE)
    return store


def effect_text(e):
    """One line: what moved after this event (or that nothing measurable did)."""
    r = e.get("72") if e.get("72") is not None else e.get("24")
    if r is None:
        return "waiting for 24 h of data"
    win = "72 h" if e.get("72") is not None else "24 h"
    if not r:
        return f"no measurable effect ({win})"
    return f"{win}: " + ", ".join(f"{x['name']} {x['delta']:+g}{(' ' + x['unit']) if x['unit'] else ''}" for x in r)


def effects_report(db, now):
    try:
        store = update_effects(db, now)
    except Exception as e:
        print(f"\nAfter recent events: unavailable ({e})")
        return
    recent = [e for e in store.values() if now - 5 * D <= e["ts"] <= now - 25 * H]
    print("\nAfter recent events (median 24 h before vs after, beyond normal day-to-day wobble; timing, not proof):")
    if not recent:
        print("  no events with a finished window in the last 5 days")
    groups = []
    for e in sorted(recent, key=lambda x: x["ts"]):
        if groups and e["ts"] - groups[-1][0]["ts"] <= 2 * H:
            groups[-1].append(e)
        else:
            groups.append([e])
    for g in groups:
        print(f"  {datetime.fromtimestamp(g[0]['ts']):%m-%d %H:%M} " + " + ".join(e["label"] for e in g) + f": {effect_text(g[-1])}")


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
    data_due_report(db, now)
    normal_day_report(db, now)
    effects_report(db, now)
    jugs(now)
    supplies_report(now)
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
        try:                                         # normal-day model + daily numbers (cheap, every pull)
            update_daily(db)
            profiles(db)
            track_dose_changes()
            update_effects(db)
        except Exception as e:
            print(f"normal-day model: {e}")
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
