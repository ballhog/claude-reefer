#!/usr/bin/env python3
"""Hydros output logger (reefcore CT 101). stdlib only.

The LSSS stores Hydros *inputs* in InfluxDB but not *outputs* (pumps, lights, skimmer, ozone,
dosers). This snapshots every output from the LSSS live endpoint into
/root/reef-lab/data/hydros.db so on/off history and power draw are kept.

  hydros-pull.py fast        outputs only (cron every minute, for the live screens)
  hydros-pull.py pull        check every output; store only changes + hourly heartbeat (cron every 5 min)
  hydros-pull.py status      print the latest snapshot
  hydros-pull.py changes [H] on/off changes in the last H hours (default 24)
"""
import json, sqlite3, sys, time, urllib.request
try:  # LSSS machine key on every call to the LSSS (LSSS sign-in, 2026-10-14); harmless with no key
    __import__("sys").path.insert(0, "/opt/reefcore"); import lsss_auth  # noqa: E402,F401
except Exception:
    pass

LSSS = "http://10.0.0.228:8000/api/hydros/live"
DB = "/root/reef-lab/data/hydros.db"
HEARTBEAT = 3600   # store an unchanged output at least hourly


def db():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS outputs(
        ts INTEGER, device TEXT, name TEXT, state INTEGER, watts REAL, override INTEGER,
        alert TEXT, PRIMARY KEY(ts, device, name))""")
    return c


def pull(fast=False):
    import subprocess   # GHL ProfiLux has its own every-minute cron line (ghl-pull.py tick)
    if not fast:
        subprocess.Popen([sys.executable, "/opt/reefcore/reef-alerts.py", "run"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)   # trend alerts + feed watchdog
        subprocess.Popen([sys.executable, "/opt/reefcore/coral-review.py", "due"], start_new_session=True,
                         stdout=open("/var/log/coral-review.log", "a"), stderr=subprocess.STDOUT)   # Sunday 08:30 coral photo review
    with urllib.request.urlopen(LSSS, timeout=30) as r:
        live = json.load(r)
    age = live.get("last_update_age_s")
    if not live.get("connected") or age is None or age > 900:
        raise SystemExit(f"hydros feed stale or disconnected (age {age} s)")
    import subprocess   # ATO top-off watcher: 15 s polling for this 5-min window (see ato-watch.py)
    if not fast:
      subprocess.Popen([sys.executable, "/opt/reefcore/ato-watch.py", "watch"], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ts = int(time.time())
    rows = []
    for dev_id, dev in (live.get("devices") or {}).items():
        dname = dev.get("name") or dev_id
        for name, o in (dev.get("Output") or {}).items():
            if not isinstance(o, dict):
                continue
            p = o.get("powerI")
            rows.append((ts, dname, name, 1 if (o.get("valueState") or 0) > 0 else 0,
                         None if p is None else p / 10.0,   # powerI is in 0.1 W
                         1 if o.get("override") else 0, o.get("alert") or ""))
    c = db()
    keep = []
    for r in rows:
        last = c.execute("SELECT ts, state, watts, override, alert FROM outputs WHERE device=? AND name=? "
                         "ORDER BY ts DESC LIMIT 1", (r[1], r[2])).fetchone()
        if last is None or keep_row(last, r):
            keep.append(r)
    c.executemany("INSERT OR IGNORE INTO outputs VALUES (?,?,?,?,?,?,?)", keep)
    c.commit()
    print(f"{len(rows)} outputs checked, {len(keep)} recorded")


def keep_row(last, r):
    """Store only changes: on/off, override, alert, >20% power shift, or an hourly heartbeat."""
    lts, lst, lw, lovr, lalert = last
    ts, _, _, st, w, ovr, alert = r
    if st != lst or ovr != lovr or alert != lalert or ts - lts >= HEARTBEAT:
        return True
    if w is not None and lw is not None:
        return abs(w - lw) > max(2.0, 0.2 * lw)
    return False


def status():
    c = db()
    ts = c.execute("SELECT max(ts) FROM outputs").fetchone()[0]
    if not ts:
        print("no data yet"); return
    print(time.strftime("latest state as of %Y-%m-%d %H:%M", time.localtime(ts)))
    cur = c.execute("""SELECT device, name, state, watts, override, alert FROM outputs o
        WHERE ts = (SELECT max(ts) FROM outputs i WHERE i.device=o.device AND i.name=o.name)
        ORDER BY device, name""").fetchall()
    for dev, name, st, w, ovr, alert in cur:
        ws = "" if w is None else f"{w:6.1f} W"
        print(f"  {'ON ' if st else 'off'} {ws:>9}  {name}{'  [override]' if ovr else ''}{'  ALERT: ' + alert if alert else ''}")
    tot = sum(r[3] or 0 for r in cur)
    print(f"  total measured draw {tot:.1f} W")


def changes(hours=24):
    c = db()
    since = int(time.time()) - int(hours * 3600)
    last = {}
    for ts, dev, name, st in c.execute(
            "SELECT ts, device, name, state FROM outputs WHERE ts>=? ORDER BY ts", (since,)):
        k = (dev, name)
        if k in last and last[k] != st:
            print(time.strftime("%m-%d %H:%M", time.localtime(ts)), "ON " if st else "off", name)
        last[k] = st


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "pull":
        pull()
    elif cmd == "fast":      # every minute from cron: outputs only (live screens)
        pull(fast=True)
    elif cmd == "status":
        status()
    elif cmd == "changes":
        changes(float(sys.argv[2]) if len(sys.argv) > 2 else 24)
    else:
        raise SystemExit(__doc__)
