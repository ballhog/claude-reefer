#!/usr/bin/env python3
"""GHL ProfiLux logger (reefcore CT 101). stdlib only.

Since 2026-10-14 (Group 4 item 0) the GHL is read THROUGH THE LSSS: GET http://10.0.0.228:8000/api/ghl/live.
Only the LSSS talks to the controller (TCP 10002 serves one client at a time and refuses new connections
for ~3 s after one closes). Stored exactly as before, in reefchem.db (table readings, source 'ghl'):
the 4 flow sensors (param ghl_flow0..3, L/h, LOGICAL lines) and the sensor slots (param ghl_s<N>,
N = GHL SENSOR index, 0-based). reefchem's pull renames ghl_s0/8/10/11 to temp_ghl/temp_200/
room_temp_ghl/humidity via the baselines file, as before.

LSSS channels are 1-based: probe channel c = GHL SENSOR[c-1]; flow channel c = physical FLOWSENSOR[c-1].
Readings carry the LSSS's last_update time, so a stale LSSS stores nothing new (INSERT OR IGNORE) and the
"GHL feed silent" alert fires as it always did. Refused if the LSSS says not connected or the data is
older than MAX_AGE_S.

Cron every minute: `ghl-pull.py tick` stores the flows each minute (live screens) and the sensor slots
every 5 min. `pull` stores everything once.

  ghl-pull.py pull      read once (via the LSSS) and store
  ghl-pull.py show      read once (via the LSSS) and print, store nothing
  ghl-pull.py direct    read the GHL itself on TCP 10002 and print, store nothing (diagnostic only:
                        it competes with the LSSS for the controller's single connection)
"""
import json, socket, sqlite3, sys, time, urllib.request

LSSS_URL = "http://10.0.0.228:8000/api/ghl/live"
MAX_AGE_S = 180                               # LSSS polls ~1/min; older than this = treat as no data
IP, PORT = "10.0.0.215", 10002                # only for `direct`
DB = "/root/reef-lab/data/reefchem.db"
FLOWS, SENSORS = 4, 16
# Stored name ghl_flowN is the LOGICAL line, not the physical port, so history and 7-day medians stay
# continuous when plugs move. 2026-10-10 PLM-WiFiLAN card swap shuffled the plugs; Joe confirmed
# port 2 = 320 return, ports 0/1 = the two 200 returns (A/B assigned by pre-swap levels ~450/~405).
#   logical: ghl_flow0 320 return | ghl_flow1 unused | ghl_flow2 200 return A | ghl_flow3 200 return B
PORT_MAP = {0: 2, 1: 3, 2: 0, 3: 1}           # logical index -> physical FLOWSENSOR port
LOGICAL = {phys: log for log, phys in PORT_MAP.items()}


def read_lsss():
    """Return (ts, {param: value}) from the LSSS, or raise OSError with a plain reason."""
    try:
        with urllib.request.urlopen(LSSS_URL, timeout=15) as r:
            d = json.load(r)
    except (OSError, ValueError) as e:
        raise OSError(f"LSSS not reachable at {LSSS_URL}: {e}")
    if not d.get("connected"):
        raise OSError(f"LSSS reports the GHL not connected: {d.get('error') or 'no reason given'}")
    age = d.get("last_update_age_s")
    if age is None or age > MAX_AGE_S:
        raise OSError(f"LSSS GHL data is stale ({age if age is None else round(age)} s old)")
    vals = {}
    for p in d.get("probes", []):
        ch, v = p.get("channel"), p.get("_value_raw", p.get("value"))
        if ch is None or v is None:
            continue
        if p.get("kind") == "flow":
            phys = int(ch) - 1
            if phys in LOGICAL:
                vals[f"ghl_flow{LOGICAL[phys]}"] = float(v)
        elif 1 <= int(ch) <= SENSORS:
            vals[f"ghl_s{int(ch) - 1}"] = float(v)
    if not vals:
        raise OSError("LSSS returned no GHL probe values")
    return int(d["last_update"]), vals


def read_direct():
    """Diagnostic: the old direct read over TCP 10002 (one connection, many GETs)."""
    s = socket.create_connection((IP, PORT), timeout=3)
    s.settimeout(2)
    vals = {}

    def get(cmd):
        s.sendall(cmd.encode() + b"\r\n")
        out = b""
        while len(out) < 512:
            dd = s.recv(512)
            if not dd:
                break
            out += dd
            if b">" in out or b")" in out:
                break
        t = out.decode("latin1").strip()
        if t.startswith("ACK <") and t.endswith(">"):
            try:
                return float(t[5:-1].strip('"'))
            except ValueError:
                return None
        return None

    try:
        for i in range(SENSORS):
            v = get(f"GET SENSOR[{i}] ACTVALUE")
            if v is not None:
                vals[f"ghl_s{i}"] = v
        for i in range(FLOWS):
            v = get(f"GET FLOWSENSOR[{PORT_MAP[i]}] ACTFLOW")
            if v is not None:
                vals[f"ghl_flow{i}"] = v
    finally:
        s.close()
    return vals


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "direct":
        try:
            vals = read_direct()
        except OSError as e:
            raise SystemExit(f"GHL not reachable directly: {e}")
        for k, v in vals.items():
            print(f"{k:10} {v:g}")
        return
    try:
        ts, vals = read_lsss()
    except OSError as e:
        raise SystemExit(f"GHL via LSSS: {e}")
    if cmd == "show":
        print(f"via LSSS, data from {time.strftime('%H:%M:%S', time.localtime(ts))}")
        for k, v in vals.items():
            print(f"{k:10} {v:g}")
        return
    if cmd == "tick" and time.localtime().tm_min % 5:
        vals = {k: v for k, v in vals.items() if k.startswith("ghl_flow")}   # sensor slots only every 5 min
    db = sqlite3.connect(DB, timeout=30)
    cur = db.executemany("INSERT OR IGNORE INTO readings VALUES (?,?,?,?,?)",
                         [(ts, "ghl", k, k, v) for k, v in vals.items()])
    db.commit()
    print(f"{cur.rowcount} GHL readings stored (via LSSS)")


if __name__ == "__main__":
    main()
