#!/usr/bin/env bash
# Reef Log daily run (mccrae, 06:30). Spec: LifeOS 03-Areas/Reef/Reef Lab System/Reef Lab v2 - reef log build spec.md
# Usage: reef-log.sh [--dry-run] [REPORTFILE]   (--dry-run: no Telegram read/send, replies empty)
set -uo pipefail

BASE=/root/reef-log
LAB=/mnt/reef-lab
LOGDIR=$LAB/log
DATE=$(date +%F)
DRY=${1:-}
REPORT=${2:-$LAB/data/reports/$DATE.txt}
RUNS=$BASE/state/runs
mkdir -p "$RUNS" "$LOGDIR"
REPLIES=$BASE/state/replies-$DATE.txt
export PATH=/root/.npm-global/bin:/usr/local/bin:/usr/bin:/bin

notify() { if [ "$DRY" = "--dry-run" ]; then cat "$1"; else "$BASE/tg.py" send "$1"; fi; }
fail() { echo "Reef log $DATE: $1" > "$RUNS/$DATE-error.txt"; notify "$RUNS/$DATE-error.txt"; exit 1; }

# reefcore writes the report at 06:25; wait up to 15 min
for _ in $(seq 1 30); do [ -s "$REPORT" ] && break; sleep 30; done
[ -s "$REPORT" ] || fail "no reefchem report at $REPORT (reefcore 06:25 job?)"

if [ "$DRY" = "--dry-run" ]; then : > "$REPLIES"
else "$BASE/tg.py" take > "$REPLIES" || fail "could not read Telegram replies"; fi

PREV=$(find "$LOGDIR" -name '*-daily.md' ! -name "$DATE-daily.md" 2>/dev/null | sort | tail -1)
PREV=${PREV:-none}
ENTRY=$LOGDIR/$(date +%Y/%m)/$DATE-daily.md
LOOKBACK=$RUNS/$DATE-lookback.txt
python3 "$BASE/lookback.py" "$REPORT" "$LOGDIR" > "$LOOKBACK" 2>&1 || fail "look-back script failed (see $LOOKBACK)"

PROMPT="$(cat "$BASE/prompt.md")

REPORT: $REPORT
REPLIES: $REPLIES
PREV: $PREV
LOGDIR: $LOGDIR
LOOKBACK: $LOOKBACK"

cd "$LAB" || fail "cannot cd to $LAB"
timeout 900 claude -p "$PROMPT" \
  --add-dir "$LAB" "$BASE/state" "$RUNS" \
  --allowedTools "Read" "Write" "Edit" "Glob" "mcp__palomino__search_lab_notes" "mcp__palomino__read_lab_note" "mcp__palomino__search_reef" "mcp__palomino__read_document" \
  --output-format json > "$RUNS/$DATE.json" 2> "$RUNS/$DATE.err" \
  || fail "claude run failed (see $RUNS/$DATE.err)"

python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["result"])' "$RUNS/$DATE.json" > "$RUNS/$DATE-digest.txt" \
  || fail "could not read Claude's reply"

# the model saying it saved the entry is not proof (lesson from v1)
[ -s "$ENTRY" ] || fail "Claude replied but $ENTRY was not written"

if [ "$DRY" = "--dry-run" ]; then cat "$RUNS/$DATE-digest.txt"; else "$BASE/tg.py" send "$RUNS/$DATE-digest.txt" --buttons "$DATE"; fi
