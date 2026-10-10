# Claude Reefer

The living side of Joe's Node Zero home lab: a ~820 gal LPS reef watched by scripts and written up daily by Claude.
The home page (nz-home) is its own repo: `ballhog/nz-home`.

## Layout
| Folder | Runs on | What |
|---|---|---|
| `reefcore/` | CT 101 reefcore, `/opt/reefcore/` | `reefchem.py` (all the math + the morning report), `hydros-pull.py` (Hydros outputs), `ato-watch.py` (ATO top-off runs, 15 s), `ghl-pull.py` (GHL ProfiLux flows + sensors), `reef-alerts.py` (trend alerts + feed watchdog), `morning-report.sh` (06:25 report, waits for Hydros), old `reef-digest.sh` / `llm-bench.py` (parked) |
| `mccrae/` | CT 103 mccrae, `/root/reef-log/` | `reef-log.sh` (06:30 daily log via headless Claude Code), `prompt.md`, `tg.py` (Telegram listener: tests, water changes, RO/DI, corals, livestock, maintenance, jugs, photos, questions), `voice.py` (iPhone voice endpoint), `lookback.py` (fingerprints + similar past days), `backfill.py`, monthly review, systemd units, `order_import.py` (coral from an order email) |
| `cron/` | CT 101 | the reefcore cron jobs |

Data lives on the `reef_lab` dataset (maximilian), not in this repo: `reefchem.db`, `hydros.db`, baselines,
reports, the reef log, coral/livestock registries, photos.

## Rules
- The script does the arithmetic; Claude explains and quotes it. No dosing advice from any model.
- Controllers are read-only; urgent alarms stay on Apex / Hydros / GHL.
- Secrets never enter the repo (`telegram.env`, `voice.token`, `palomino.token` stay on mccrae).

## Docs
- [`docs/REEF-LAB-SYSTEM.md`](docs/REEF-LAB-SYSTEM.md): the current system overview (hosts, data flow, timeline,
  Telegram/voice commands, controllers, command reference, open items, lessons learned).
- [`docs/history/how-it-works-2026-10-03.md`](docs/history/how-it-works-2026-10-03.md): the original deep
  reference from the Hermes era (palomino and reefchem internals, lessons learned).

## GitHub and publishing

| Repo | What | Lives at | Deploy key (on reefcore CT 101) |
|---|---|---|---|
| [`ballhog/claude-reefer`](https://github.com/ballhog/claude-reefer) (private) | this repo: `reefcore/`, `mccrae/`, `cron/`, `docs/` | `/opt/claude-reefer` | `/root/.ssh/claude-reefer_deploy`, ssh host alias `github-claude-reefer` |
| [`ballhog/nz-home`](https://github.com/ballhog/nz-home) | the home page (nz.home.arpa) | `/opt/nz-home` | `/root/.ssh/nz-home_deploy`, ssh host alias `github-nz-home` |

Both push over SSH with per-repo deploy keys (write access), configured in `/root/.ssh/config` on reefcore.
Commits are authored as `ballhog <ballhog@users.noreply.github.com>`.

### Push Claude Reefer (from vincent, as root)

    pct exec 103 -- sh /root/reef-log/stage-code.sh                 # mccrae: copy app code to reef_lab/.code-drop
    pct exec 101 -- /opt/claude-reefer/publish.sh "what changed"    # reefcore: refresh, secret-check, commit, push

`stage-code.sh` copies the mccrae code (no `telegram.env`, `voice.token`, `palomino.token`, `state/`, backups).
`publish.sh` copies `/opt/reefcore/*` and the cron files in, refuses to commit if anything looks like a token,
then commits and pushes. Docs in `docs/` are edited in place (Claude keeps them in step with the vault copy).

### Push nz-home (from vincent, as root)

    pct exec 101 -- bash -lc 'cd /opt/nz-home && git add -A && git commit -m "what changed" && git push'

### Check status

    pct exec 101 -- git -C /opt/claude-reefer status -sb
    pct exec 101 -- git -C /opt/nz-home status -sb

### Add a deploy key for a new repo

    pct exec 101 -- ssh-keygen -t ed25519 -N "" -C "<repo> deploy" -f /root/.ssh/<repo>_deploy
    pct exec 101 -- cat /root/.ssh/<repo>_deploy.pub     # paste into GitHub: repo Settings -> Deploy keys, allow write
    # add to /root/.ssh/config:  Host github-<repo> / HostName github.com / User git / IdentityFile ... / IdentitiesOnly yes
    # remote: git@github-<repo>:ballhog/<repo>.git

The same overview is in Joe's vault and (copied by Joe) at the root of the `reef` share as `Reef Lab System.md`.
