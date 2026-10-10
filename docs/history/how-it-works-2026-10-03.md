---
title: Reef Lab system - how it works (historical deep reference)
written: 2026-10-03
last annotated: 2026-10-10
tags: [node-zero, reef-lab, history, hermes, palomino, reefchem, nz-home]
---

# Reef Lab system: how it works (historical, Hermes era)

> **Status 2026-10-10: historical.** This is the deep reference written when the stack was first built
> (2026-10-02/03), when Hermes + Claude Haiku wrote the digest and Ollama ran on pizer. Since then: Claude Reefer
> on mccrae writes the only daily log; Hermes and the local LLM are retired; pizer is shut down; CT 101 is
> renamed **reefcore** and the scripts moved from `/root/.hermes/scripts/` to `/opt/reefcore/`. Read
> `docs/REEF-LAB-SYSTEM.md` for the current system. This file is kept for the reasoning, the palomino and
> reefchem internals (sections 3.3, 3.4, 6.2, 6.3), and the lessons learned.

Secrets are never written in this file, only where they live.

Contents: 1 big picture · 2 where everything is · 3 components · 4 daily timeline ·
5 spending caps · 6 technical details · 7 command reference · 8 known issues ·
9 lessons learned

---

## 1. The big picture (as built 2026-10-03)

```
 Apex (Trident alk/Ca/Mg, pH, temp, sump level)
        |  every 5 min
        v
 LSSS Pi 10.0.0.228 -- InfluxDB history, FastAPI :8000 (no auth)
        |  reefchem.py pull: every 15 min (last 2 h) + before each digest (last 26 h)
        v
 hermes CT 101 ---- reefchem.db + reef-baselines.md   (reef_lab dataset on maximilian)
   |   |                     ^
   |   |                     | hand tests: reefchem.py log / wc
   |   | 06:30 reef-digest
   |   v
   |  Hermes cron --model--> Claude Haiku (capped reef-lab key)
   |   |          --search-> palomino CT 112 (Qdrant: reef + reef_lab)
   |   |--> Telegram digest + note saved to reef_lab/notes/<date>.md
   |
   |  06:00 reef-heartbeat --model--> Ollama on pizer CT 117 (qwen3 4B, local)
   |
   +-- nz-home :8079 (reef gauges, digest, systems, Claude chat)

 pizer watchdog (separate Telegram bot): Ollama, Hermes reachability, disk. Alerts on change.
```

Design rules (each one learned the hard way, see section 9):

- **The script does all the arithmetic.** The model only explains numbers it is given. It is told
  to quote them and never recompute.
- **The digest runs on Claude, not the local model.** The local 4B ran fast once tuned, but
  invented a source, skipped flagged items and claimed to save a file it never wrote.
- **The digest never gives dosing advice.** Dosing is Joe's decision from fresh tests. A stale
  reading (Trident stalled) gets "hand-test and check the tester".
- **Urgent alarms stay on the controllers** (Apex/GHL). Nothing here replaces them.
- **Model-written notes live in a separate collection** (`reef_lab`) so they are never
  mistaken for reference material.

---

## 2. Where everything is (as of 2026-10-03)

| Thing | Where | Notes |
|---|---|---|
| vincent | Proxmox host `10.0.0.7` | i7-11700T (8C/16T, 35 W), 31 GB RAM, no swap |
| pizer | CT 117, `10.0.0.117` | Ollama; 8 cores, 24 GB limit (shut down 2026-10-10) |
| hermes | CT 101, `10.0.0.100` | Hermes agent + gateway, reefchem, nz-home (now **reefcore**) |
| palomino | CT 112, `10.0.0.112` | Qdrant + Tika + ingest + MCP server :8765 |
| LSSS Pi | `10.0.0.228:8000` (`lsss.local`) | data source |
| maximilian | `10.0.0.3`, storage subnet `10.0.40.3` | holds `reef` and `reef_lab` datasets |

### Storage

| Dataset | On vincent | In containers | Use |
|---|---|---|---|
| `twentyfour_tb_storage/reef` | `/mnt/reef` (NFS ro) | palomino `mp0` → `/mnt/reef` (ro) | reference library |
| `twentyfour_tb_storage/reef_lab` | `/mnt/reef_lab` (NFS rw) | CT 101 `mp0` → `/root/reef-lab` (rw); palomino `mp1` → `/mnt/reef_lab` (ro); mccrae → `/mnt/reef-lab` | data, log, notes |

`reef_lab` NFS share: host `10.0.40.7` only, **Mapall user/group = joe** (uid 3000), dataset
owned by joe. Maproot does not work because the containers are unprivileged (container root is uid
100000 on vincent, which Maproot never matches). Inside the containers files show as
`nobody nogroup`; that is normal. Add `reef_lab` to the snapshot task and bob's replication list
by hand.

---

## 3. Components

### 3.1 Ollama on pizer (CT 117) — retired

Model `qwen3:4b-instruct-2507-q4_K_M` at 64K context. `qwen3:14b` was removed: the original Qwen3 family is
capped at 40,960 context, below Hermes's 64K minimum. `OLLAMA_KV_CACHE_TYPE=q8_0` made prompt reading collapse
as context grew on this CPU, so it was left off.

### 3.2 Hermes (CT 101) — retired

- Cron jobs got the full default tool set (~53 tools, ~15K-token prompt) unless `platform_toolsets.cron` was set
  in `config.yaml` (then ~5K). The `hermes tools` menu does not show cron.
- `HERMES_API_CALL_STALE_TIMEOUT=900` raised the per-call limit for non-streaming cron calls (default 180 s);
  found by grepping `/usr/local/lib/hermes-agent`.
- Jobs: `reef-heartbeat` 06:00 (local qwen) and `reef-digest` 06:30 (Claude Haiku, one palomino search, note
  saved to `reef_lab/notes/`).

### 3.3 palomino (CT 112): reef library search

- Collections: **`reef`** (from `/mnt/reef`, ~413 files) and **`reef_lab`** (from `/mnt/reef_lab`).
- MCP server `http://10.0.0.112:8765/mcp`, streamable HTTP, bearer token `/opt/palomino/mcp.token`,
  service `palomino-mcp`. Tools: `search_reef`, `read_document`, `search_lab_notes`, `read_lab_note`.
- Ingest cron (shared lock `/tmp/ingest.lock`):

```
15 * * * *  ingest.py                       (reef, state.db)
45 * * * *  ingest.py --root /mnt/reef_lab --collection reef_lab --state /opt/palomino/state-reef_lab.db
```

- Logs `/opt/palomino/ingest.log`, `ingest-lab.log`.
- `.noindex` hides a folder. `_duplicates`, `_archive`, dot-folders are skipped.
- RAM limit 4 GB; peak is the `:15` ingest.

### 3.4 reefchem.py: the math (now `/opt/reefcore/reefchem.py`)

stdlib Python. Database `reef_lab/data/reefchem.db`, targets `reef_lab/data/reef-baselines.md`.

| Command | What |
|---|---|
| `pull [--hours 26]` | copy `ext_probe` from the LSSS (duplicates ignored); also ingests the Telegram inbox |
| `log alk 8.1 ca 430 mg 1350 [--note "..."]` | hand test (`alk ca mg ph temp sal no3 po4`) |
| `wc [--minutes 120]` | mark a water change now |
| `report [--asof "YYYY-MM-DD HH:MM"]` | text summary used by the daily log |

Targets file (Joe edits; script and nz-home read it):

```
| param | probe | unit | low | high |
| alk   | Alkx5 | dKH  | 7.0 | 11.0 |
| salinity | hydros:1R Conductivity | ppt | 32.3 | 34.9 |
```

### 3.5 LSSS (data source)

- MQTT (live), InfluxDB 2.x `:8086` (buckets `lsss` real, `lsss-sim` simulator, no expiry),
  FastAPI `:8000` in front.
- Used: `GET /api/influx/export?measurements=ext_probe&hours=N&format=csv`;
  `GET /api/influx/tags?measurement=ext_probe` (the parameter is required); `GET /api/hydros/live`.
- The bench Pi is the only path for Apex data. Copied history is safe on maximilian.

### 3.6 nz-home (CT 101)

- `http://10.0.0.100:8079`, service `nz-home`, code `/opt/nz-home/` (GitHub `ballhog/nz-home`), config
  `/etc/nz-home.env`. LAN and Tailscale only, never through the Cloudflare tunnel.

---

## 5. Spending caps (Claude API, for the nz-home chat box)

1. **Prepaid credits, auto-reload off**: hard ceiling.
2. **Workspace monthly limit** + notification (the cutoff itself sends no warning).
3. **nz-home daily cap** `NZ_HOME_DAILY_TOKENS` (default 300k tokens/day).

The daily reef log runs on Claude Code on the Max plan (flat rate), not the API key.

---

## 6. Technical details

### 6.2 How reefchem computes

- **Storage**: `readings(ts, source, probe, param, value)` with a unique key on
  `(ts, source, probe, param)`, so repeated pulls never duplicate. `notes(ts, note)`,
  `events(ts, kind, end_ts)`.
- **Probe to parameter**: by probe name from `reef-baselines.md`, not by the LSSS `kind` tag (which mislabels
  `Kalk` as alk).
- **Trident**: the Apex repeats the last result every 5 min, so only value changes count as new
  tests. `STALLED?` after 12 h for alk, 30 h for calc/mag (alk 3x/day, Ca/Mg 1x/day).
- **Trends**: least-squares slope per day over the last 7 days (`statistics.linear_regression`), needing a
  2-day span. For pH/temp this uses every 5-min point; for Trident, the change points.
- **Water changes**: for each `LvLSmp` reading, compare with the median of the previous 2 h
  (24 readings). More than **0.4** below starts an event; events within 15 min merge. Window =
  5 min before the first low reading to **60 min after** the last (mixing tail). Temperature
  readings inside a window are left out of min/max/mean/trend. Manual `wc` events add to this.
- **Hand vs probe**: compares the hand test with the last probe value before it; a gap over 25 % of
  the target band prints `CHECK CALIBRATION`.
- **Feed**: no Apex data for 60 min → `ALERT` in the report.

### 6.3 How palomino search works

- Text is extracted (Tika), split into chunks, embedded on CPU with `BAAI/bge-small-en-v1.5`
  (fastembed) and stored in Qdrant with path, modified date and chunk number.
- A search embeds the query, takes the closest chunks, keeps at most `max_per_file` per document
  and returns them with paths so answers can cite them.
- Each collection has its own state database recording which files are indexed, so changed files
  are re-embedded and deleted files removed. A non-default collection must have its own `--state`
  file or the reef index would churn.

### 6.5 Performance (i7-11700T, CPU only, local 4B model)

| Situation | Prompt reading | Writing |
|---|---|---|
| qwen 4B, ~3-5K context, f16 cache | 35-60 tok/s | 4.5-8 tok/s |
| qwen 4B, 20-26K context | ~15-20 tok/s | **0.85-1.4 tok/s** |
| qwen 4B with q8_0 cache | fell 28 → 5 tok/s by 8K | 2.3 tok/s |

---

## 9. Lessons learned

- **A 4B model on CPU can do one focused step, not a multi-step job.** In the digest it skipped
  flagged items, cited a file that did not exist, and claimed to save a note it never wrote. Always compare
  the model's reply with the script output it was given.
- **Context size decides speed on this CPU.** Writing fell from ~8 to under 1 tok/s between 3K and
  25K tokens. A forgotten tool set (cron's default 53 tools) tripled the prompt.
- **Rules with exceptions get skipped.** "Don't dose on stale data" was ignored once; "never give
  dosing advice" was followed.
- **Check the tool's own code for settings** instead of guessing names.
- Shell: `<placeholders>` break bash; pasted prompts (`root@host:~#`) run; `pct exec` needs `bash -lc` for
  login-PATH tools; `systemctl show` opens a pager; containers default to UTC (set America/Detroit, restart
  cron); Telegram `getUpdates` is empty until you message the bot; a container memory limit is a ceiling, not a
  reservation; a CSS `display` rule overrides the HTML `hidden` attribute.
