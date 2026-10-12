#!/usr/bin/env python3
"""Reef trend alerts + feed watchdog (reefcore CT 101). stdlib only.

Started every 5 min by hydros-pull.py; runs its checks at most every 15 min. Alerts are queued to
reef_lab/data/outbox/alerts.jsonl and sent by the Reef Log bot listener on mccrae (reefcore has no
Telegram token). Not a replacement for controller alarms: these are slow, trend-type problems.

Checks: Apex / Hydros / GHL feed silent > 30 min; a GHL return line under 80% of its 7-day median for
an hour; salinity (3 h median) within 0.3 ppt of the top of its range; a dosing jug at <= 2 days;
a Trident test that stopped producing new results.
Instrument watch (2026-10-12): impossible readings (probe fault), sensors frozen for 6 h, probe-pair
offset drift vs its 14-day normal, and a missed Trident alk run (learned run times).

Each alert is sent once when it starts, reminded every 12 h while it lasts, and gets a short
"cleared" line when it ends. Quiet hours 22:00-07:00: nothing is sent; anything still active at 07:00
goes out then.

  reef-alerts.py run       normal run (throttled to 15 min)
  reef-alerts.py check     evaluate now and print, send nothing, change no state
"""
import importlib.util, json, os, statistics, sys, time
from datetime import datetime, date

DATA = "/root/reef-lab/data"
STATE = f"{DATA}/alerts-state.json"
OUTBOX = f"{DATA}/outbox/alerts.jsonl"
H, D = 3600, 86400
QUIET = (22, 7)
REMIND_H = 12

spec = importlib.util.spec_from_file_location("reefchem", "/opt/reefcore/reefchem.py")
rc = importlib.util.module_from_spec(spec); spec.loader.exec_module(rc)


def hm(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def checks(db, now):
    """Return {key: (message, clear_message)} for every condition active now."""
    act = {}
    for src, name, fix in (("apex", "Apex", "Check the LSSS Pi and the Apex link."),
                           ("hydros", "Hydros", "Refresh the Hydros feed on the LSSS."),
                           ("ghl", "GHL", "Check the GHL ProfiLux (10.0.0.215) and its API setting.")):
        last = db.execute("SELECT MAX(ts) FROM readings WHERE source=?", (src,)).fetchone()[0]
        if last and now - last > 30 * 60:
            act[f"feed:{src}"] = (f"⚠️ {name} feed silent {rc.age(now - last)} (last reading {hm(last)}). {fix}",
                                  f"✅ {name} feed is back.")
    labels = {}
    try:
        for line in open(f"{DATA}/ghl-labels.txt"):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1); labels[k.strip()] = v.strip()
    except OSError:
        pass
    for i in range(4):
        k = f"ghl_flow{i}"
        week = [v for _, v in rc.series(db, k, "ghl", now - 7 * D, now)]
        hour = [v for _, v in rc.series(db, k, "ghl", now - H, now)]
        if len(week) < 12 or len(hour) < 6:
            continue
        med = statistics.median(week)
        if med > 50 and max(hour) < 0.8 * med:
            name = labels.get(k, k)
            act[f"flow:{i}"] = (f"🌊 {name} flow low for an hour: {hour[-1]:g} L/h vs normal ~{med:g} "
                                f"({hour[-1] / med * 100:.0f}%). Check the pump, line and valves.",
                                f"✅ {name} flow back to normal.")
    bl = rc.baselines()
    sal = bl.get("salinity")
    if sal:
        pts = [v for _, v in rc.series(db, "salinity", "hydros", now - 3 * H, now)]
        if len(pts) >= 6:
            m = statistics.median(pts)
            if m >= sal["high"] - 0.3:
                act["salinity:high"] = (f"🧂 Salinity {m:.2f} ppt (3 h median), near the top of your range ({sal['high']:g}). "
                                        "Time for some RO/DI; text 'added N gal rodi' when done.",
                                        f"✅ Salinity back down ({m:.2f} ppt).")
    try:
        today = date.today()
        for l in open(f"{DATA}/recipes.md"):
            c = [x.strip() for x in l.strip().strip("|").split("|")]
            if len(c) < 7 or not c[0].startswith("J") or not c[0][1:].isdigit():
                continue
            try:
                jug, per, last = float(c[3]) * 1000, float(c[4]), date.fromisoformat(c[5][:10])
            except ValueError:
                continue
            left = (jug - per * (today - last).days) / per
            if left <= 2:
                act[f"jug:{c[0]}"] = (f"🧪 {c[1]} jug: about {max(left, 0):.1f} days left (mixed {c[5]}, {c[4]} ml/day). "
                                      "Text 'mixed …' when you refill.", f"✅ {c[1]} jug refilled.")
    except OSError:
        pass
    for p, b in bl.items():
        if b["probe"] in getattr(rc, "TRIDENT", ()):
            pts = rc.changes(rc.series(db, p, b.get("source", "apex"), now - 7 * D, now))
            if pts and now - pts[-1][0] > rc.STALE_TEST_H[b["probe"]] * H:
                act[f"trident:{p}"] = (f"🔬 Trident: no new {p} result in {rc.age(now - pts[-1][0])}. "
                                       "Check reagents, waste and the Trident status.",
                                       f"✅ Trident {p} results coming in again.")
    try:
        instrument_checks(db, now, act)
    except Exception as e:                       # never let a new check break the old ones
        act["inst:error"] = (f"🛠️ instrument watch failed: {e}", "✅ instrument watch running again.")
    return act


# ---------- instrument watch (Group 1, 2026-10-12): the instruments themselves, not the tank ----------
MOVERS = [("temp", "apex", "Apex temp"), ("temp_hydros", "hydros", "Hydros sump temp"), ("ph", "apex", "Apex pH"),
          ("ph_hydros", "hydros", "Hydros pH"), ("salinity", "hydros", "Hydros salinity"),
          ("temp_ghl", "ghl", "GHL tank temp"), ("temp_200", "ghl", "GHL 200 temp"),
          ("ghl_flow0", "ghl", "320 return flow"), ("ghl_flow2", "ghl", "200 return A flow"), ("ghl_flow3", "ghl", "200 return B flow")]
PAIRS = [("ph", "apex", "ph_hydros", "hydros", "pH: Apex vs Hydros", 0.15, ""),
         ("temp", "apex", "temp_hydros", "hydros", "temp: Apex vs Hydros", 0.5, " °C"),
         ("temp", "apex", "temp_ghl", "ghl", "temp: Apex vs GHL", 0.5, " °C")]
SANE = {"ph": (6.0, 9.5), "ph_hydros": (6.0, 9.5), "salinity": (25, 40), "temp": (15, 35), "temp_hydros": (15, 35),
        "temp_ghl": (15, 35), "temp_200": (15, 35)}


def _hourly(db, p, src, since, now):
    b = {}
    for t, v in rc.series(db, p, src, since, now):
        b.setdefault(t // H, []).append(v)
    return {k: sum(v) / len(v) for k, v in b.items()}


def instrument_checks(db, now, act):
    feeds_down = {k.split(":")[1] for k in act if k.startswith("feed:")}
    # 1. impossible values -> probe fault, not a tank alarm
    for p, (lo, hi) in SANE.items():
        src = "ghl" if p in ("temp_ghl", "temp_200") else "hydros" if p.endswith("_hydros") or p == "salinity" else "apex"
        r = db.execute("SELECT value, ts FROM readings WHERE param=? AND source=? ORDER BY ts DESC LIMIT 1", (p, src)).fetchone()
        if r and now - r[1] < 2 * H and not (lo <= r[0] <= hi):
            act[f"inst:range:{p}"] = (f"🛠️ {p} reads {r[0]:g}, outside anything a reef can be ({lo:g}-{hi:g}). Probably the probe "
                                      "or its cable, not the tank: check the probe before acting on it.",
                                      f"✅ {p} reading is plausible again.")
    # 2. stuck sensor: no change at all for 6 h on something that normally moves
    for p, src, name in MOVERS:
        if src in feeds_down or f"inst:range:{p}" in act:
            continue
        pts = [v for _, v in rc.series(db, p, src, now - 6 * H, now)]
        if len(pts) < 10 or max(pts) != min(pts) or (p.startswith("ghl_flow") and pts[-1] == 0):
            continue
        wk = [v for _, v in rc.series(db, p, src, now - 7 * D, now - 6 * H)]
        if len(wk) > 50 and max(wk) - min(wk) > 0:
            act[f"inst:stuck:{p}"] = (f"🛠️ {name} has read exactly {pts[-1]:g} for 6 h; it normally moves. "
                                      "Sensor or its feed may be frozen.", f"✅ {name} is moving again.")
    # 3. probe drift: the OFFSET between two probes moved away from its 14-day normal
    for a, sa, b, sb, name, lim, unit in PAIRS:
        if sa in feeds_down or sb in feeds_down:
            continue
        ha, hb = _hourly(db, a, sa, now - 14 * D, now), _hourly(db, b, sb, now - 14 * D, now)
        both = sorted(set(ha) & set(hb))
        base = [ha[k] - hb[k] for k in both if k < (now - D) // H]
        cur = [ha[k] - hb[k] for k in both if k >= (now - 6 * H) // H]
        if len(base) < 24 or len(cur) < 3:
            continue
        b0, c0 = statistics.median(base), statistics.median(cur)
        if abs(c0 - b0) > lim:
            act[f"inst:drift:{a}-{b}"] = (f"🛠️ Probe drift, {name}: the gap is now {c0:+.2f}{unit}, normally {b0:+.2f}{unit}. "
                                          "One of the two probes is drifting: calibrate or check against a hand test.",
                                          f"✅ {name} gap back to normal ({c0:+.2f}{unit}).")
    # 4. Trident alk: learn its daily run times; flag a missed run within ~2 h instead of waiting 12 h
    pts = rc.changes(rc.series(db, "alk", "apex", now - 14 * D, now))
    if len(pts) >= 10:
        mins = [(datetime.fromtimestamp(t).hour * 60 + datetime.fromtimestamp(t).minute) for t, _ in pts]
        slots = []
        for m0 in sorted(mins):
            near = [m for m in mins if abs(m - m0) <= 60]
            if len(near) >= 5 and all(abs(m0 - s) > 120 for s in slots):
                slots.append(int(statistics.median(near)))
        last_t = pts[-1][0]
        mid = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0).timestamp()
        due = [mid + s * 60 for s in slots] + [mid - D + s * 60 for s in slots]
        missed = [t for t in due if t + 2 * H < now and last_t < t - H and now - t < D]
        if missed and "apex" not in feeds_down:
            t = max(missed)
            act["inst:trident:alk"] = (f"🔬 Trident skipped its {datetime.fromtimestamp(t):%H:%M} alk run (last result "
                                       f"{rc.age(now - last_t)} ago). Check power, reagents and waste.",
                                       "✅ Trident alk results coming in again.")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    now = int(time.time())
    try:
        state = json.load(open(STATE))
    except (OSError, ValueError):
        state = {"last_run": 0, "active": {}}
    if mode == "run" and now - state.get("last_run", 0) < 14 * 60:
        return
    import sqlite3
    db = sqlite3.connect(f"file:{DATA}/reefchem.db?mode=ro", uri=True, timeout=30)
    act = checks(db, now)
    if mode == "check":
        for k, (msg, _) in act.items():
            print(k, "|", msg)
        print(f"{len(act)} active")
        return
    hr = datetime.fromtimestamp(now).hour
    quiet = hr >= QUIET[0] or hr < QUIET[1]
    out, prev = [], state.get("active", {})
    newstate = {}
    for k, (msg, clr) in act.items():
        s = prev.get(k, {"since": now, "sent": 0})
        s["clear"] = clr
        s.pop("pending_clear", None)
        if not quiet and (not s["sent"] or now - s["sent"] > REMIND_H * H):
            out.append(msg if not s["sent"] else msg + f" (still, since {datetime.fromtimestamp(s['since']):%m-%d %H:%M})")
            s["sent"] = now
        newstate[k] = s
    for k, s in prev.items():
        if k not in act and s.get("sent") and not quiet:
            out.append(s.get("clear", f"✅ {k} cleared."))
        elif k not in act and s.get("sent") and quiet:
            newstate[k] = s          # hold the clear message until morning ... unless it re-fires
            newstate[k]["pending_clear"] = True
    for k in [k for k, s in newstate.items() if s.get("pending_clear") and k not in act]:
        if not quiet:
            out.append(newstate.pop(k).get("clear", ""))
    if out:
        os.makedirs(os.path.dirname(OUTBOX), exist_ok=True)
        with open(OUTBOX, "a") as f:
            for m in out:
                if m:
                    f.write(json.dumps({"ts": now, "text": "Reef alert: " + m}) + "\n")
    state = {"last_run": now, "active": newstate}
    tmp = STATE + ".tmp"
    json.dump(state, open(tmp, "w"), indent=1); os.replace(tmp, STATE)


if __name__ == "__main__":
    main()
