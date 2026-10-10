#!/usr/bin/env bash
# Reef log monthly review (mccrae). Cron: 07:00 on the 1st, reviews the month that just ended.
# Usage: monthly-review.sh [--dry-run] [YYYY-MM]   (--dry-run: writes to state/runs only, prints instead of Telegram)
set -uo pipefail
BASE=/root/reef-log
LAB=/mnt/reef-lab
LOGDIR=$LAB/log
RUNS=$BASE/state/runs
DRY=""; [ "${1:-}" = "--dry-run" ] && { DRY=1; shift; }
MONTH=${1:-$(date -d "$(date +%Y-%m-01) -1 day" +%Y-%m)}
export PATH=/root/.npm-global/bin:/usr/local/bin:/usr/bin:/bin
mkdir -p "$RUNS"
notify() { if [ -n "$DRY" ]; then cat "$1"; else "$BASE/tg.py" send "$1" ${2:+--buttons "$2"}; fi; }
fail() { echo "Reef log monthly review $MONTH: $1" > "$RUNS/monthly-$MONTH-error.txt"; notify "$RUNS/monthly-$MONTH-error.txt"; exit 1; }

INPUT=$RUNS/monthly-$MONTH-input.txt
python3 "$BASE/monthly-table.py" "$LOGDIR" "$MONTH" > "$INPUT" 2>&1 || fail "input script failed (see $INPUT)"
if [ -n "$DRY" ]; then OUT=$RUNS/monthly-$MONTH-review-DRY.md
else OUT=$LOGDIR/${MONTH:0:4}/${MONTH:5:2}/$MONTH-monthly-review.md; mkdir -p "$(dirname "$OUT")"; fi

PROMPT="$(cat "$BASE/monthly-prompt.md")

INPUT: $INPUT
LOGDIR: $LOGDIR
OUT: $OUT
today: $(date +%F)"

cd "$LAB" || fail "cannot cd to $LAB"
timeout 1200 claude -p "$PROMPT" --add-dir "$LAB" "$RUNS" \
  --allowedTools "Read" "Write" "Glob" "mcp__palomino__search_lab_notes" "mcp__palomino__read_lab_note" "mcp__palomino__search_reef" "mcp__palomino__read_document" \
  --output-format json > "$RUNS/monthly-$MONTH.json" 2> "$RUNS/monthly-$MONTH.err" || fail "claude run failed"
python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["result"])' "$RUNS/monthly-$MONTH.json" > "$RUNS/monthly-$MONTH-digest.txt" || fail "could not read Claude's reply"
[ -s "$OUT" ] || fail "Claude replied but $OUT was not written"
notify "$RUNS/monthly-$MONTH-digest.txt"
