#!/usr/bin/env python3
"""GHL ProfiLux logger (reefcore CT 101). stdlib only.

Reads the GHL local API v1.1 (10.0.0.215:10002, fw 7.52, API set to full access; this script only GETs) and stores readings in reefchem.db
(table readings, source 'ghl'): the 4 flow sensors (param ghl_flow0..3, L/h) and the 10 sensor
slots (param ghl_s0..9, units unknown until Joe names them). Started every 5 min by hydros-pull.py.

fw 7.52 answers NACK properly for missing slots, so the old echo/marker check is gone.
All reads share one TCP connection (see Session).

  ghl-pull.py pull      read once and store
  ghl-pull.py show      read once and print, store nothing
"""
import socket, sqlite3, sys, time

IP, PORT = "10.0.0.215", 10002
DB = "/root/reef-lab/data/reefchem.db"
FLOWS, SENSORS = 4, 10


class Session:
    """One TCP connection for the whole read.

    fw 7.52 + PLM-WiFiLAN: the port refuses (RST) a new connection for ~3 s after the last one
    closed, but it happily answers many commands on one open connection. So: connect once, send
    every GET over it, and on a reset wait out the cooldown and reconnect.
    """

    def __init__(self):
        self.s = None

    def _open(self):
        for attempt in range(4):
            try:
                self.s = socket.create_connection((IP, PORT), timeout=3)
                self.s.settimeout(2)
                return
            except OSError:
                time.sleep(3.5)
        raise OSError("GHL refused 4 connection attempts")

    def get(self, cmd):
        for attempt in range(3):
            if self.s is None:
                self._open()
            try:
                self.s.sendall(cmd.encode() + b"\r\n")
                out = b""
                while len(out) < 512:
                    d = self.s.recv(512)
                    if not d:
                        raise ConnectionResetError("closed")
                    out += d
                    if b">" in out or b")" in out or out.rstrip() == b"ACK":
                        break
                break
            except OSError:
                self.close()
                time.sleep(3.5)
        else:
            return None
        t = out.decode("latin1").strip()
        if t.startswith("ACK <") and t.endswith(">"):
            try:
                return float(t[5:-1].strip('"'))
            except ValueError:
                return None
        return None                                  # NACK: slot empty / card removed

    def close(self):
        if self.s is not None:
            try:
                self.s.close()
            except OSError:
                pass
        self.s = None


def read():
    vals = {}
    g = Session()
    try:
        for i in range(SENSORS):
            v = g.get(f"GET SENSOR[{i}] ACTVALUE")
            if v is not None:
                vals[f"ghl_s{i}"] = v
        for i in range(FLOWS):
            v = g.get(f"GET FLOWSENSOR[{i}] ACTFLOW")
            if v is not None:
                vals[f"ghl_flow{i}"] = v
    finally:
        g.close()
    if not vals:
        raise OSError("GHL answered nothing")
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
