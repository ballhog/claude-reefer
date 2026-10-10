#!/usr/bin/env python3
"""GHL ProfiLux logger (reefcore CT 101). stdlib only.

Reads the GHL local API (10.0.0.215:10002, read-only mode) and stores readings in reefchem.db
(table readings, source 'ghl'): the 4 flow sensors (param ghl_flow0..3, L/h) and the 10 sensor
slots (param ghl_s0..9, units unknown until Joe names them). Started every 5 min by hydros-pull.py.

Firmware quirk: asking for an attribute a resource doesn't have often returns the LAST value sent
instead of a NACK. Every read is therefore checked against a fresh marker read; a reply that equals
the marker is treated as a stale echo and dropped.

  ghl-pull.py pull      read once and store
  ghl-pull.py show      read once and print, store nothing
"""
import socket, sqlite3, sys, time

IP, PORT = "10.0.0.215", 10002
DB = "/root/reef-lab/data/reefchem.db"
FLOWS, SENSORS = 4, 10


def q(cmd):
    s = socket.create_connection((IP, PORT), timeout=3)
    s.settimeout(2)
    try:
        s.sendall(cmd.encode() + b"\r\n")
        out = b""
        while len(out) < 512:
            d = s.recv(512)
            if not d:
                break
            out += d
            if b">" in out or b"NACK" in out:
                break
    finally:
        s.close()
    t = out.decode("latin1").strip()
    if t.startswith("ACK <") and t.endswith(">"):
        return float(t[5:-1])
    return None


def read():
    vals = {}
    for i in range(SENSORS):
        v = q(f"GET SENSOR[{i}] ACTVALUE")      # SENSOR ACTVALUE is a documented read
        if v is not None:
            vals[f"ghl_s{i}"] = v
    for i in range(FLOWS):
        # marker: a NACK-producing query does not change the echo buffer, so use a real read
        mark = q(f"GET SENSOR[{(i + 7) % SENSORS}] ACTVALUE")
        v = q(f"GET FLOWSENSOR[{i}] ACTFLOW")
        if v is not None and v != mark:
            vals[f"ghl_flow{i}"] = v
        elif v is not None and v == mark == 0:
            vals[f"ghl_flow{i}"] = 0.0              # 0 == 0 is ambiguous but harmless
    return vals


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    try:
        vals = read()
    except OSError as e:
        raise SystemExit(f"GHL not reachable: {e}")
    if cmd == "show":
        for k, v in vals.items():
            print(f"{k:10} {v:g}")
        return
    ts = int(time.time())
    db = sqlite3.connect(DB, timeout=30)
    db.executemany("INSERT OR IGNORE INTO readings VALUES (?,?,?,?,?)",
                   [(ts, "ghl", k, k, v) for k, v in vals.items()])
    db.commit()
    print(f"{len(vals)} GHL readings stored")


if __name__ == "__main__":
    main()
