# Claude Reefer

The living side of Joe's Node Zero home lab: a ~820 gal LPS reef watched by scripts and written up daily by Claude.
The home page (nz-home) is its own repo: `ballhog/nz-home`.

## Layout
| Folder | Runs on | What |
|---|---|---|
| `reefcore/` | CT 101 reefcore, `/opt/reefcore/` | `reefchem.py` (all the math + the morning report), `hydros-pull.py` (Hydros outputs), `ato-watch.py` (ATO top-off runs, 15 s), `ghl-pull.py` (GHL ProfiLux flows + sensors), old `reef-digest.sh` / `llm-bench.py` (parked) |
| `mccrae/` | CT 103 mccrae, `/root/reef-log/` | `reef-log.sh` (06:30 daily log via headless Claude Code), `prompt.md`, `tg.py` (Telegram listener: tests, water changes, RO/DI, corals, livestock, maintenance, jugs, photos, questions), `voice.py` (iPhone voice endpoint), `lookback.py` (fingerprints + similar past days), `backfill.py`, monthly review, systemd units, `order_import.py` (coral from an order email) |
| `cron/` | CT 101 | the reefcore cron jobs |

Data lives on the `reef_lab` dataset (maximilian), not in this repo: `reefchem.db`, `hydros.db`, baselines,
reports, the reef log, coral/livestock registries, photos.

## Rules
- The script does the arithmetic; Claude explains and quotes it. No dosing advice from any model.
- Controllers are read-only; urgent alarms stay on Apex / Hydros / GHL.
- Secrets never enter the repo (`telegram.env`, `voice.token`, `palomino.token` stay on mccrae).

## Updating this repo
From vincent:

    pct exec 103 -- sh /root/reef-log/stage-code.sh
    pct exec 101 -- /opt/claude-reefer/publish.sh "what changed"

`publish.sh` copies the live code in, refuses to commit if anything looks like a token, then commits and pushes.

See `Reef Lab System.md` (reef share) for the full system overview.
