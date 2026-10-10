#!/bin/sh
# 06:25 morning report (reefcore). Waits up to 15 min for the Hydros feed to be fresh (< 20 min old)
# so the report is not built on stale Hydros data; then pulls 26 h and writes the day's report.
# If the feed is still silent, the report goes ahead (it carries an ALERT line) and reef-alerts.py
# has already pinged Telegram.
R=/opt/reefcore/reefchem.py
OUT=/root/reef-lab/data/reports/$(date +%F).txt
i=0
while [ $i -lt 15 ]; do
  $R pull --hours 2 >/dev/null 2>&1
  age=$(python3 -c "import sqlite3,time; db=sqlite3.connect('file:/root/reef-lab/data/reefchem.db?mode=ro',uri=True); t=db.execute(\"select max(ts) from readings where source='hydros'\").fetchone()[0] or 0; print(int(time.time()-t))")
  [ "$age" -lt 1200 ] && break
  i=$((i+1)); sleep 60
done
$R pull --hours 26 >/dev/null 2>&1
$R report > "$OUT" 2>&1
