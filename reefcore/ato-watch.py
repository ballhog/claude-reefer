#!/usr/bin/env python3
"""ATO top-off watcher (reefcore CT 101). stdlib only.

Polls the LSSS Hydros live feed every 15 s for ~4m45s and records each change of the
'1R Sump ATO' input into /root/reef-lab/data/hydros.db (table ato). hydros-pull.py starts one
of these each 5-minute cron run, so coverage is continuous. senseValue 0 = water low / topping off,
1 = full. A run = the time the input stayed at 0 (resolution ~15 s, if the feed updates that fast).

  ato-watch.py watch           poll for one cron window (started by hydros-pull.py pull)
  ato-watch.py runs [H]        top-off runs in the last H hours (default 24)
"""
import fcntl, json, sqlite3, sys, time, urllib.request
try:  # LSSS machine key on every call to the LSSS (LSSS sign-in, 2026-10-14); harmless with no key
    __import__("sys").path.insert(0, "/opt/reefcore"); import lsss_auth  # noqa: E402,F401
except Exception:
    pass

LSSS = "http://10.0.0.228:8000/api/hydros/live"
DB = "/root/reef-lab/data/hydros.db"
INPUT = "1R Sump ATO"
LOCK = "/tmp/ato-watch.lock"
POLL, WINDOW = 15, 285


def db():
    c = sqlite3.connect(DB, timeout=30)
    c.execute("CREATE TABLE IF NOT EXISTS ato(ts INTEGER PRIMARY KEY, value INTEGER, feed_ts REAL)")
    return c


def read():
    with urllib.request.urlopen(LSSS, timeout=20) as r:
        live = json.load(r)
    if not live.get("connected") or (live.get("last_update_age_s") or 1e9) > 600:
        return None, None
    for dev in (live.get("devices") or {}).values():
        i = (dev.get("Input") or {}).get(INPUT)
        if isinstance(i, dict) and "senseValue" in i:
            return int(i["senseValue"]), live.get("last_update")
    return None, None


def watch():
    lk = open(LOCK, "w")
    try:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return   # another watcher is still running
    c = db()
    last = c.execute("SELECT value FROM ato ORDER BY ts DESC LIMIT 1").fetchone()
    last = last[0] if last else None
    end = time.time() + WINDOW
    while time.time() < end:
        try:
            v, fts = read()
        except Exception:
            v = None
        if v is not None and v != last:
            c.execute("INSERT OR REPLACE INTO ato VALUES (?,?,?)", (int(time.time()), v, fts))
            c.commit()
            last = v
        time.sleep(POLL)


def runs(since, until=None):
    """[(start_ts, end_ts or None, seconds)] for runs of value 0 overlapping the window."""
    c = db()
    rows = c.execute("SELECT ts, value FROM ato WHERE ts<=? ORDER BY ts", (until or 2**40,)).fetchall()
    out, start = [], None
    for ts, v in rows:
        if v == 0 and start is None:
            start = ts
        elif v == 1 and start is not None:
            if ts >= since:
                out.append((start, ts, ts - start))
            start = None
    if start is not None:
        out.append((start, None, int(time.time()) - start))
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "runs"
    if cmd == "watch":
        watch()
    else:
        h = float(sys.argv[2]) if len(sys.argv) > 2 else 24
        rs = runs(time.time() - h * 3600)
        for a, b, s in rs:
            print(time.strftime("%m-%d %H:%M:%S", time.localtime(a)), f"{s:5d} s", "" if b else "(running)")
        print(f"{len(rs)} runs, {sum(s for *_, s in rs) / 60:.1f} min total in {h:g} h")
