---
title: Reef Lab System
rev: 2026-10-12
updated: 2026-10-12
tags: [node-zero, reef-lab, claude-reefer, reef-log, mccrae, reefcore, palomino, nz-home, ghl, hydros]
---

# Reef Lab System (rev 2026-10-12)

> Current system overview. Copies of this file also live in Joe's LifeOS vault
> (`03-Areas/Reef/Reef Lab System/Reef Lab System rev 2026-10-12.md`) and, once copied by Joe, at the root of
> the `reef` share as `Reef Lab System.md`. The older deep reference (Hermes era) is in
> `docs/history/how-it-works-2026-10-03.md`.

How the reef data, the reef log ("Claude Reefer"), Telegram and voice logging, and the home page fit
together. Recipes: `reef_lab/data/recipes.md` (and Joe's vault note `Mixing Notes - DIY Balling.md`).

Secrets are never written here, only where they live.

**Also 10-12, upgrade Group 3 (the tank's normal day):** normal-for-this-time ribbon on 24 h charts and an "off pattern" tag on gauges; a `daily` table of one number per day (pH/temp swing, salinity drift, return flows, ATO runs, skimmer watts); before/after per event (WC, mixes, maintenance, RO/DI, feeding, dose-rate changes) judged against normal day-to-day wobble; power and cost from the Hydros meters at $0.217/kWh with watts drift feeding maintenance by data.

**Also 10-12, upgrade Group 2:** sign-in approved from Telegram (no password) protects every change; logging from the screen (+ Log, mixed today, photos); 8 pm Telegram check-in; supplies forecast with a Sunday shopping list.

**What changed in rev 10-12 (upgrade Group 1, plan in the project doc `nz-claude-reefer-upgrade-plan-2026-10-12.md`):** live screens (pages update when data lands; GHL flows and Hydros outputs every minute), tap any number for its history, maintenance by data (return-pump flow drop, skimmer cup sensor, roller overfill, RO/DI TDS; new report section "Due by data"), instrument watch alerts (impossible readings, frozen sensors, probe-pair drift, missed Trident alk run). New index on `readings(param, source, ts)`.

**What changed in rev 10-11:** GHL ProfiLux now wired (PLM-WiFiLAN card, 10.0.0.215) with the GHL API at
full access; `ghl-pull.py` uses one TCP session; flow plugs re-mapped after the card swap (logical names kept);
humidity/temp card moved to the Expansion Box on the 200 (slots 10/11). Telegram answers "status" instantly
and treats questions without "?" as questions. Hydros feed watchdog fixed (Joe, via the LSSS). nz-home: home
page fits any screen with no scrolling (wall monitor to phone, bottom tabs on phones), sub-pages scroll,
Recipes became a dosing-station graphic with a daily-dosing gauge panel, Maintenance became an Imperial
schematic of the whole system with tasks completed right in the pop-up. Lighting recorded in the tank
profile. Reef PC by the tank runs the home page full screen. GHL doser retrofit parked on the roadmap.

**What changed in rev 10-10 (vs 10-09):** Claude Reefer is the only AI voice (Haiku digest and Hermes retired,
local LLM retired); always-on Telegram listener + iPhone voice; coral registry with care sheets;
maintenance, recipes and dosing-jug pages; Hydros outputs and ATO logged; GHL ProfiLux connected
(flow sensors); new report sections (flow, salinity drift, pH bump, jugs, maintenance); Imperial gauges
incl. flow gauges; coral growth panel and Livestock tab; self test; code on GitHub. **CT 101 renamed hermes →
reefcore**: reef scripts now in `/opt/reefcore/` (`/root/.hermes/scripts` is a symlink to it); pizer (CT 117)
shut down, not needed.

---

## 0. How to use it (Joe's quick guide, rev 2026-10-12 late, Groups 1-3)

The everyday "what does what" in plain words. Technical detail is in the sections after this one.

### The home page (`nz.home.arpa`)
- **Gauges** fit the screen (wall monitor, the 24" reef PC, laptop, iPad, phone with tabs at the bottom). A red top edge = outside your range or a stale test.
- **Tap any gauge** for its history: line, your normal range shaded, and markers for water changes, maintenance, mixed jugs, feeding and RO/DI. 24 H / 7 D / 30 D buttons; drag across the chart to read exact values. Esc or ✕ closes.
- **Live:** the page updates itself when new data lands (flows every minute, probes every 5 min). No need to reload.
- **Alert strip** at the top: reef alerts in one line; tap to open them all.
- **°C / °F** buttons top right (remembered per device).
- **⚡ $/day chip** (top right, every page): what the Hydros-metered gear costs per day. Tap for the power panel (see below). Turns amber when a pump's watts drift.
- **Ask Claude** box: questions about what's on the page. Self test (left) runs 10 pipeline checks.

### The tank's normal day (Group 3)
- **Normal-for-this-time ribbon:** on a 24 h history chart, a shaded band behind today's line shows what this sensor usually does at each half hour (middle 80% of the last 21 days). Today's line outside the ribbon = unusual for the time of day, even if it's inside your target range.
- **"off pattern" tag** on a home gauge: the last 2 hours spent mostly (75%+) outside that ribbon. A heads-up, not an alarm; no Telegram for it. Sensors with too little history (Hydros, GHL) start showing the ribbon after about 5 days.
- **Daily numbers:** one value per day, kept forever: pH swing (Apex and Hydros), temp swing, salinity median and drift, return-flow medians, ATO runs, skimmer watts. Open them from the buttons under a chart ("pH swing per day").
- **Before / after each event:** for every water change, mix, maintenance task, RO/DI fill, feeding and dose-rate change, the script compares the 24 h before with the 24 h and 72 h after. It only calls a change when it's bigger than the tank's normal day-to-day wobble; otherwise "no measurable effect". Trident alk is compared over whole daily cycles (alk swings about 1 dKH a day, so the 12:45 test after the 09:45 dose always reads higher).
  - On a chart, an event marker's label adds "· after: …".
  - In a maintenance pop-up, the last 3 times the task was done show "After <date>: …".
  - The morning report has an "after events" section. All of it is **timing, not proof**.

### Power and cost (Group 3)
- Rate: **$0.217/kWh**. The script adds up each Hydros output's watts over time (kWh per day), then $/day and $/month.
- **Power panel** (tap the ⚡ chip): $/day and $/month, kWh/day, watts right now, today so far, a bar per day for the last 14 days, and every output with W now, kWh/day and $/month. **Tap an output** for its watts history.
- **Only what the Hydros meters.** Display lights and heaters on other strips aren't counted, so the real bill is higher. First numbers (1 full day, 10-11): about 8.2 kWh/day = $1.77/day, $54/month; top users are the roller pump, the sump Tunze, sump LED, skimmer and the 320 Tunze.
- **Watts drift = health signal:** for steady pumps (skimmer, sump Tunze, gyres/Tunzes, roller pump), the last 24 h median watts vs the 14 days before. A 10%+ change shows in the panel; 20%+ makes the matching maintenance task due by data (skimmer → M01, sump powerheads → M19, 320 powerheads → M05, roller → M02). Starts once there are 3+ days of history.
- Link: any page + `?power` opens the panel.

### Signing in, and logging from the screen
- **Looking is open; changing needs a signed-in device** (chat, COMPLETE, + Log, mixed today, photos).
- **Sign in:** tap **🔒 Sign in** (top right). Name the device, tick *Keep this device signed in* on the reef PC / wall screen (6 months; otherwise 30 days), tap *Send to Telegram*. The Reef Log bot asks "Approve sign-in … code 123456?": check the code matches the screen, tap **✅ Approve**. The screen signs itself in. No password anywhere.
- Top right then shows **● device name**; tap it to sign that device out. Telegram **`devices`** lists every signed-in device with a *Sign out* button for each.
- **+ Log** (top right, every page): hand test (alk, Ca, Mg, salinity, pH, NO3, PO4; odd numbers like alk 99 are refused), water change (5/10/20/30 gal or type it), RO/DI added. Lands in the database right away, shows on the history charts (amber diamonds for tests) and in the next reef log.
- **Dosing station:** tap a jug, then **hold "mixed today"** to restart its countdown (same as texting "mixed alk").
- **Coral / livestock page:** open one, **+ Add photo** (the iPad opens the camera), optional caption. Files to that coral's photo history and timeline.

### Maintenance page (`nz.home.arpa/maintenance`)
- **The drawing** is the whole plant: 200 upstairs, 320 display, 300 sump with returns, roller, skimmer, heaters, probes, ATO, X10 dosing heads, Trident, lights, and the RO/DI train (sediment, carbon block, membrane, cation, 2× anion, 2× DI, booster pump). Saltwater is dark blue, RO/DI light blue; flow dashes move faster when the GHL sees more flow.
- **Glows:** blue = running (return pumps from GHL flow, everything else from Hydros power). **Red** = needs you now (overdue task, or a return line under 80% of normal). **Amber** = soon (task due within 7 days, or a dosing jug at 3 days or less). The glow traces the equipment's own outline. Calm screen = nothing needs you.
- **Tap equipment** to light up its panel; tap again (or tap the panel) for the pop-up.
- **Doing a task:** in the pop-up, **press and hold COMPLETE** (about 1 s). Did it another day? Tap *done earlier*, pick the date, then hold COMPLETE. An **Undo** toast shows for 10 s. Telegram/voice ("cleaned the skimmer cup") writes the same log.
- **BY DATA:** some tasks also watch sensors and can come due before the calendar says so: return pumps (flow down 10% from their clean level = due, 20% = overdue), skimmer cup (cup-full sensor tripped), filter roller (chamber overfill sensor), RO/DI resin (product TDS 1 ppm or more), and pump watts drift (above). The pop-up shows the sensor reason under the task, plus "After <date>" notes from the before/after check.
- **RO/DI:** sediment and carbon block every 60 days (Joe: they go black); resins by TDS; membrane ~2 years. Changed 10-12: both sediment filters, the carbon block and one anion stage.
- **Dotted-underlined values** in panels and pop-ups open their history chart (Hydros outputs show watts / on-off).
- **Ticker** along the bottom: overdue/due tasks, return flows vs normal, salinity, alk, Ca, Mg, temps, pH, humidity, Hydros outputs on, last ATO run, jug days left. Hover to pause.
- **Data feed** (right, wide screens): real report and log lines in Aurebesh.
- `?pulsetest` on the address shows what alert glows look like.

### Recipes / dosing station (`nz.home.arpa/recipes`)
- Jugs (Alk, Part C, Calcium, Mg mix), salt and RO/DI barrels with fill levels from the last mix date. Tap a vessel for its recipe card (and the hold-to-log *mixed today* button). The **daily dosing** gauges show what the doses add per day and the Ca:alk balance.
- **Supplies** button: on hand, use per day (from the recipe and dose rate), days left, order-by date. Red = order now (within shipping time + 2 weeks). Counts come from Telegram (below).
- Mixing-barrel sensors in the salt card open their history.

### Telegram (Reef Log bot) and voice
- **status** (no "?" needed): instant snapshot of feeds and alerts.
- Questions: just ask ("how's alk this week"); Claude answers from the report, profile, recipes and logs.
- Logging: `alk 7.4`, `hand test alk 7.7`, `ca 430 mg 1350`, `changed 20 gallons`, `added 10 gal rodi`, `mixed alk`, `cleaned skimmer`, `replaced filter roll`, `what's due`, `jugs`, coral and livestock lines (`new coral …`, `C-012 par 180`, `new fish …`), photos with a caption. Anything else is noted in today's log and acknowledged.
- **Evening check-in, 8 pm:** 🐟 Fed · 🌊 Water change (then gallons) · 🧪 Mixed a jug (then which) · 🔧 Maintenance (then which task) · 👍 Nothing else, then ✔ Done. Tap as many as fit; it shows what was already logged today so nothing gets double-entered.
- **Supplies:** plain words work: `supplies: 6 x 55 lb boxes reef salt, 40 lb calcium chloride`, `received epsom 5 lb` (adds to what's there), `have 1000 ml left in the mg jug`; units g/kg/lb/oz, ml/L/gal, bags/bottles/rolls (needs the pack size in supplies.md). `supplies` = full list, `shopping list` = only what to order. **Sunday ~9 am** the shopping list arrives on its own.
- **devices** = signed-in devices, each with a Sign out button.
- **Morning:** report at 06:25 (now with normal-day, after-events and power sections), Claude Reefer daily log to Telegram at 06:30 (👍/👎 buttons). Things logged on the home page go into it too.
- **Alerts** ("Reef alert: …"): feed silent, return flow low, salinity near the top, jug low, Trident stalled, plus **instrument watch**: probe fault (impossible reading), frozen sensor (same value 6 h), probe drift (the gap between two probes changed), Trident skipped an alk run (it learned the run times: ~00:20, 06:15, 12:40, 18:20). Sent once, reminded every 12 h, "cleared" when fixed. Quiet 22:00-07:00 (held until morning).
- **Voice:** iPhone Shortcut "Reefer" (works on Tailscale away from home).

### The reef PC by the tank
- Dedicated Windows PC: Edge in kiosk mode at login (shortcut in the Startup folder). **Alt+F4** exits. Sign it in once with *Keep this device signed in*.

### Handy links
- Any page + `?chart=salinity` (or any parameter, e.g. `ghl_flow0`) opens that history directly. Add `&days=30` for a month. Hydros output: `?chart=Skimmer&src=hydros_out`. `?power` opens the power panel.
- `?nolive` turns live updates off (used for screenshots). `nz.home.arpa/recipes#supplies` opens the supplies table.

### GHL ProfiLux notes
- Wired at 10.0.0.215 (PLM-WiFiLAN card). GHL API at full access, but every script only reads; nothing writes to a controller without your OK.
- Expansion cards: **configure them in the ProfiLux first, then move them to the Expansion Box** (the humidity card on the 200 is sensor 10 = room temp, 11 = humidity).
- Flow ports since the card swap: port 2 = 320 return, 0/1 = 200 returns A/B, 3 empty. History keeps the line names.
- The GHL clock runs 1 h slow until DST is enabled on it.

### When something looks wrong
- "Hydros feed silent": refresh the Hydros feed on the LSSS.
- A page not updating: it reconnects on its own within ~10 s; reload if not.
- Everything stale at once / Self test fails on files: check Maximilian (the reef_lab share lives there; 10-12 it went down for ~20 min and everything resumed on its own).
- Sign-in request didn't arrive: wait ~10 s (the bot checks every 8 s); requests expire after 5 minutes; max 5 per 10 minutes.
- Trident alerts after an unplug: check power, reagents and waste; results resume on their own.
- Anything odd: Telegram `status`, or Self test on the home page.

### What's next
- Upgrade plan: `claude/nz-claude-reefer-upgrade-plan-2026-10-12.md`. Groups 1, 2 and 3 done. Group 4 = replay slider, ask the schematic, weekly photo review, controller-action decision.
- Power: tell Claude where the heaters and display lights are plugged in (if they can be metered, they join the panel).
- Supplies forecast needs your remaining counts (`supplies …` in Telegram).
- Roadmap: smart RO/DI for city water at the new place; ESP32 retrofit of the GHL dosers (after the outlet PCB and the move).

---

## 1. Big picture

```
 Apex (Trident alk/Ca/Mg, pH, temp, sump level) ─┐
 Hydros (salinity, pH, sump temp, TDS, room temp, ATO, levels, switches) ─┤ every 5 min
                                                  v
 LSSS Pi 10.0.0.228 (InfluxDB ext_probe, FastAPI :8000; /api/hydros/live = Hydros outputs)
        │ reefchem.py pull: every 15 min, and 26 h before the morning report
        v
 reefcore CT 101 ── reefchem.db + reef-baselines.md                 (reef_lab dataset)
   │  hydros-pull.py (5 min) → hydros.db   outputs on/off/watts, change-only + hourly
   │  ato-watch.py   (15 s)  → hydros.db   ATO top-off runs
   │  ghl-pull.py    (5 min) → reefchem.db GHL ProfiLux 10.0.0.215:10002 (flows, sensor slots)
   │  06:25 reefchem.py report → reef_lab/data/reports/YYYY-MM-DD.txt
   │
   ├─▶ 06:30 Claude Reefer (mccrae CT 103, Claude Code headless, Max plan, flat rate)
   │        → reef_lab/log/YYYY/MM/YYYY-MM-DD-daily.md  → Telegram (Reef Log bot, 👍/👎 buttons)
   │        1st of month 07:00: monthly review → YYYY-MM-monthly-review.md
   │
   └─▶ nz-home :8079 (nz.home.arpa): gauges, flow gauges, latest log, corals, livestock,
            maintenance, recipes, self test, Claude chat

 Joe → Telegram (Reef Log bot, always-on listener) or iPhone voice (mccrae :8790)
     → hand tests, water changes, RO/DI adds, notes, photos, coral/livestock/maintenance/mix logging, questions
 palomino CT 112 indexes reef (library) and reef_lab (log + notes) hourly; Claude searches it via MCP.
```

### Design rules

- **The script does all the arithmetic.** Claude only explains numbers it is given, and quotes them.
- **No dosing advice from any model.** Dosing decisions are Joe's, from fresh tests.
- **Urgent alarms stay on the controllers** (Apex / Hydros / GHL). This system is for trends.
- **One voice in the reef log:** the mccrae Claude. Joe's replies are the feedback.
- **Hypotheses stay hypotheses** until Joe confirms them. Timing lining up is not proof.
- **Read-only on controllers.** Nothing here switches outputs. The GHL API has full access enabled (10-10), but every script only sends GET; any SET needs Joe first.
- **Model-written text is kept apart** from the reference library (`reef_lab`, not `reef`).

---

## 2. Where everything is

| Thing | Address | Role |
|---|---|---|
| maximilian | `10.0.0.3` (storage `10.0.40.3`) | holds `reef` and `reef_lab` datasets |
| vincent | `10.0.0.7` | Proxmox host; `reef_lab` at `/mnt/reef_lab`; smoke test `~claude/bin/reef-smoke.sh` |
| reefcore CT 101 (was hermes) | `10.0.0.100` | `/opt/reefcore/`: reefchem, hydros-pull, ato-watch, ghl-pull; nz-home; orionid-planner; this repo at `/opt/claude-reefer` |
| mccrae CT 103 | `10.0.0.16` | Claude Reefer: reef log, Telegram listener, voice endpoint |
| palomino CT 112 | `10.0.0.112` | Qdrant + Tika search, MCP `:8765` |
| pizer CT 117 | `10.0.0.117` | shut down, not needed (Ollama retired); disk kept |
| LSSS Pi | `10.0.0.228:8000` | Apex + Hydros inputs (InfluxDB), Hydros live outputs |
| Apex | `10.0.0.227` | AquaController |
| GHL ProfiLux | `10.0.0.215` | web UI (digest auth, realm "ghl"); local API TCP 10002 (full access enabled, scripts read only) |

### reef_lab layout

```
reef_lab/
  data/          reefchem.db, hydros.db, reef-baselines.md, reports/, inbox/ (Telegram queue),
                 tank-profile.md, recipes.md, maintenance.md, maintenance-log.md, todo-at-home.md,
                 roadmap.md, expected-overrides.txt, ghl-labels.txt                 (.noindex)
  log/YYYY/MM/   reef log: YYYY-MM-DD-daily.md, *-history.md (backfill), YYYY-MM-monthly-review.md
  corals/        registry.md + C-###.md (profile, care sheet, timeline incl. PAR/weight)
  livestock/     registry.md + L-###.md (fish and inverts; created on the first 'new fish …')
  photos/YYYY/MM Telegram photos, YYYY-MM-DD_HHMM_<subject>.jpg                     (.noindex)
  notes/         old Haiku digests (history)                                        (.noindex)
  bench/         local LLM bench (retired: .parked)                                 (.noindex)
  .code-drop/    mccrae code staged for this repo (stage-code.sh)                    (.noindex)
```

Backups: `reef` and `reef_lab` must be in maximilian's snapshot task and bob's replication list.

---

## 3. Timeline

| When | What | Where |
|---|---|---|
| always | Telegram listener (`reef-log-bot.service`), voice endpoint (`reef-voice.service`) | mccrae |
| every 15 s (in 5-min windows) | ATO top-off watcher | reefcore |
| every minute | `ghl-pull.py tick` (flows every minute, sensor slots every 5 min); `hydros-pull.py fast` (outputs) | reefcore (`/etc/cron.d/reefcore-fast`) |
| every 5 min | Apex/Hydros into InfluxDB; `hydros-pull.py pull` (+ alerts, ATO watcher) | LSSS, reefcore |
| every 15 min | `reefchem.py pull --hours 2` (also ingests the Telegram inbox) | reefcore |
| :15 / :45 hourly | palomino ingest: `reef` / `reef_lab` | palomino |
| 06:25 | pull 26 h + write the day's report | reefcore |
| 06:30 | Claude Reefer daily log → Telegram | mccrae |
| 1st, 07:00 | monthly review (cron line: Joe to add) | mccrae |

All containers run America/Detroit time.

---

## 4. Claude Reefer: the reef log (mccrae)

The long-term memory of the tank: what the data showed, what Claude thought, what Joe said and did.

### Each morning (`/root/reef-log/reef-log.sh`)

1. Wait for the 06:25 report.
2. `lookback.py` computes today's **fingerprint** (value + 7-day direction per parameter; stale or
   impossible readings skipped) and finds similar past days, with what happened in the 14 days after.
3. Claude closes **yesterday's entry** (Joe's replies, 👍/👎, events), writes **today's**, and
   updates coral / livestock / maintenance files when replies call for it. The script checks the file exists.
4. Digest to the Reef Log bot with 👍/👎 buttons. Any failure sends a one-line error.

### Entry format

```
---
date: 2026-10-09
type: daily                # daily / history / monthly-review
status: hypothesis         # hypothesis / confirmed / corrected / no-reply / backfill
fingerprint: {alk: {value: 6.88, trend_7d: flat}, ...}
events: [calc dose cut 800 -> 700 ml/day]
tags: [alk, calc]
---
## Observations · ## Hypotheses · ## Coral corner · ## Joe's reply
```

### What the morning report contains (reefchem.py)

Per parameter: latest, 7-day/30-day stats, trend, 24 h range, hand test vs probe (CHECK CALIBRATION).
Plus: pre-dose alk (last Trident result before the 09:45 bolus) · Hydros levels, switches and
equipment (outputs in override, on/off counts, watts) · maintenance due · dosing-jug run-out ·
**pH bump after the alk bolus** (with batch-change marker) · **Flow** (GHL; LOW < 80% of 7-day median)
· **Salinity drift** (daily medians, RO/DI adds, ATO runs, gal/week to hold level, days to the top of
range) · water changes · Joe's notes.

---

## 5. Logging from the phone

**Telegram (Reef Log bot)**, any time:

| Send | Does |
|---|---|
| `alk 7.4`, `ca 430 mg 1350`, `sal 34.1` (`!` forces an odd value) | hand test → reefchem |
| `changed 20 gallons` | water change (temp left out of stats 2 h) |
| `added 10 gal rodi` / `rodi 20 L` | RO/DI add → salinity drift |
| `mixed alk`, `new batch calcium` | dosing-jug countdown restarts |
| `cleaned skimmer`, `replaced filter roll`, `what's due`, `jugs` | maintenance log / status |
| `new coral X @ loc`, `C-012 set location …`, `C-012 weight 42`, `C-012 care sheet`, `corals`, `frag C-003 x2 @ loc` | coral registry |
| `C-012 par 180` | PAR reading → the coral's PAR history (Growth panel) |
| `new fish yellow tang @ 320`, `new snail trochus x10 @ sump`, `L-001 eating well`, `L-001 set species …`, `L-003 died`, `livestock` | livestock registry (L-###) |
| photo (caption `C-012`, `L-001` or text) | saved to `photos/`, added to that coral's or animal's timeline |
| anything with `?` | Claude answers (sees report, tank profile, recipes, maintenance, registries) |
| anything else | note → tomorrow's log |
| 👍 / 👎 on the morning digest | feedback filed into the entry |

**Voice:** iPhone Shortcut "Reefer" (Dictate → POST `http://10.0.0.16:8790/voice` with the bearer
token in `voice.token` → Speak). Works on Tailscale away from home. Questions get a spoken answer;
everything else is logged exactly like Telegram.

---

## 6. nz-home (reefcore)

`http://nz.home.arpa` (`10.0.0.100:8079`). Code `/opt/nz-home/` (GitHub `ballhog/nz-home`, tag
v0.2.0, 0.3.0 in progress; see README/CHANGELOG there). Config `/etc/nz-home.env`.

- **Reef:** Imperial targeting-scale gauges (Apex, Trident, Hydros: salinity, pH, sump temp, TDS, room
  temp) and **flow gauges** for the GHL return lines; alerts; full report; latest reef log; °C/°F.
- **Corals** (with a Growth panel: first vs latest photo, PAR and weight history) / **Livestock** (fish and
  inverts, L-###) / **Maint** / **Recipes** tabs.
- **Systems** lamps + **Self test** (10 read-only pipeline checks, animated diagnostic panel).
- **Claude chat** (Haiku, capped key, open on the LAN).
- LAN and Tailscale only, never through the Cloudflare tunnel.

**Added 2026-10-12 (Group 3, the tank's normal day):**
- **Normal day** (`reefchem.py`): `build_profiles` / `profiles()` -> `data/profiles.json` (p10/p50/p90 per 30-min slot, last 21 days, last 6 h left out, WC windows left out for temps; rebuilt hourly from the 15-min `pull`). `off_pattern()`: last 2 h >= 75% outside the band widened 25%. `daily(day, metric, value)` table via `update_daily` (backfilled from 09-03). Report section "Normal day". nz-home: `/api/series` returns `profile` for charts of 1.5 days or less (ribbon), `src=daily` series, `related` buttons; `reef_data` items carry `offpattern`.
- **Before/after per event:** `collect_events` (maintenance-log, events table wc/rodi/fed/dose, daily-log frontmatter `events:`, `dose-changes.json` from `track_dose_changes` snapshots of recipes) -> `event_effects` (24 h before vs 1-25 h and 1-73 h after; a move counts only past 2x the median day-to-day wobble and a floor per parameter; Trident compares whole daily cycles, 3+ tests each side) -> `data/event-effects.json` (`update_effects`, 60 days). `effect_text`, report section "After events" (events within 2 h grouped). nz-home: chart event labels get " · after: ..."; `plant_data` tasks carry `effects` (last 3), shown in the maintenance pop-up.
- **Power and cost:** `power_summary()` integrates `hydros.db` watts per output (each row held to the next, capped 2 h), splits at local midnight, averages the last 7 full days (90%+ covered); `RATE = 0.217` $/kWh -> `data/power.json`. Watts drift: 24 h median while drawing > 2 W vs the 14 days before; 10%+ shown, 20%+ sets the mapped task due (`POWER_TASK`: Skimmer M01, 1RTunzeSmp / 300 Gyre M19, 320 Tunze / Gyres / MP40 M05, FilterRolrPump M02) via `data_due`. Report section "Power". nz-home `GET /api/power` (recomputes if the file is over 10 min old); `nz.js` header chip `#nzPow` + pop-over, `?power` deep link, rows open `src=hydros_out` history. Hydros-metered outputs only (display lights and heaters not counted).

**Added 2026-10-12 (Group 2):**
- **Sign-in:** `POST /api/auth/start` {name, keep} -> 6-digit code + one-time nonce; queues a message with Approve/Deny buttons to `data/outbox/ui.jsonl`; tg.py writes `data/auth/answers/<id>.json`; `GET /api/auth/poll?id&nonce` sets `nz_s` (HttpOnly, SameSite=Strict, 30 d / 183 d). Sessions: `/var/lib/nz-home/sessions.json` (token hashes, 0600); public list without secrets: `data/auth/devices.json`; Telegram sign-outs: `data/auth/revoke/<sid>` (applied by the watcher). Max 5 requests per 10 min, codes live 5 min. `GET /api/auth/me`, `POST /api/auth/logout`. Every other POST: signed-in device or `Authorization: Bearer $NZ_HOME_TOKEN` (scripts). `nz.js` wraps fetch so any 401 opens the sign-in and retries.
- **Logging:** `POST /api/log/test` (sanity ranges, `force` overrides), `/api/log/wc`, `/api/log/rodi` {gal} -> `data/inbox/hand-tests.jsonl` + immediate `reefchem.ingest_inbox`; `POST /api/recipes/mixed` {id: J#}; `POST /api/coral|animal/<ID>/photo?caption=` (JPEG body, 15 MB max) -> `photos/YYYY/MM/` + timeline line. All of it also goes to `data/inbox/screen-log.txt`, which `tg.py take` folds into the reef log with Joe's replies.
- **Supplies:** `data/supplies.md` (on hand as of a date, per-batch amount + jug -> use/day, pack size, lead days); `reefchem.supplies()` -> `/api/recipes` `supplies`, the dosing-station Supplies table and a report section.

**Added 2026-10-12 (Group 1):**
- **Live:** `GET /api/events` (Server-Sent Events). A watcher thread fingerprints reefchem.db, hydros.db, alerts-state.json, maintenance and recipes files every 5 s and pushes what changed; pages refetch only then (60-120 s timer kept as fallback). Works through Caddy (nz.home.arpa). `?nolive` turns it off (headless screenshots stall on an open stream).
- **History for any number:** `GET /api/series?p=&src=&days=` (points downsampled to ~400, normal band, events: water changes, maintenance log, mixed jugs, hand tests; `src=hydros_out` for Hydros outputs). Shared `/static/nz.js` (`NZ.live`, `NZ.chart`, `NZ.bind`): home gauges, maintenance panel values and pop-up readings, recipes barrel sensors. Deep link: any page `?chart=<param>[&src=&days=&label=]`.
- **Maintenance by data:** `reefchem.data_due()`; the worse of calendar and sensors sets the task state ("BY DATA · …"), with the sensor reason in the pop-up and the alert glow.

**Added 2026-10-10/11:**
- **Fit to screen:** the home page never scrolls; gauges shrink through full / sparkline / dial / chip / micro
  modes to fit (wall monitor, the 24" touchscreen by the tank, laptop, iPad Pro, phone with bottom tabs);
  small header, alert strip on top. Sub-pages (Corals, Livestock, Recipes, Maint) scroll normally; shared CSS
  is scoped to `body.home`.
- **Recipes:** opens on a dosing-station drawing (Alk, Part C, Calcium, Mg mix jugs, salt and RO/DI barrels,
  fill level from `recipes.md`); tap a vessel for its recipe card. A daily-dosing gauge panel shows what the
  daily doses add (alk dKH, Ca, Mg ppm/day) and the Ca:alk balance.
- **Maintenance:** Imperial schematic of the whole plant (200 upstairs, 320 display, 300 sump with returns,
  roller, skimmer, heaters, probes, ATO, X10 dosing heads, Trident, lights) with leader lines to task panels.
  Saltwater dark blue, RO/DI light blue; flow animation speed from the GHL flow sensors; running equipment
  glows (return pumps from GHL flow, the rest from Hydros outputs). Tap equipment to light its panel, tap
  again for details. Aurebesh feed from real report/log lines.
- **Complete a task in the pop-up:** hold COMPLETE (or "done earlier" with a date); toast with Undo.
  `POST /api/maintenance/done` `{id, date?, note?, undo_to?}` updates `maintenance.md` and appends to
  `maintenance-log.md`. `GET /api/plant` feeds the drawing. POST routes need a signed-in device since Group 2.
- **Reef PC by the tank:** dedicated Windows PC, Edge in kiosk mode at login
  (`msedge.exe --kiosk http://10.0.0.100:8079 --edge-kiosk-type=fullscreen --no-first-run`, Startup folder).

---

## 7. Controllers and data sources

| Source | How it arrives | Notes |
|---|---|---|
| Apex + Trident | LSSS InfluxDB `ext_probe` | Trident alk 3x/day, Ca/Mg 1x/day; alk reads ~0.5 dKH low |
| Hydros inputs | LSSS InfluxDB `ext_probe` (`hydros:<input>` in baselines) | refresh the LSSS Hydros feed if the report says "no Hydros data" |
| Hydros outputs | LSSS `/api/hydros/live` → `hydros-pull.py` → `hydros.db` | expected overrides in `expected-overrides.txt` |
| ATO | Hydros "1R Sump ATO" input, 15 s watcher | probe sits 5-6" from the ATO inlet |
| GHL ProfiLux 4 | GHL API v1.1 over TCP 10002 at 10.0.0.215 (PLM-WiFiLAN, wired, fw 7.52, full access), `ghl-pull.py` | `FLOWSENSOR[n] ACTFLOW` (L/h), `SENSOR[n] ACTVALUE` for slots 0-15. One TCP connection per read: the port refuses a new connection for ~3 s after the last one closed. NACK -4 unknown resource, -5 unknown attribute, -101 missing/out of range, -102 not supported, -104 end of history, -105 no access |

GHL flow (`ghl-labels.txt`): stored names are the LOGICAL line, `ghl-pull.py` `PORT_MAP` maps them to the
physical port so history stays continuous when plugs move. Since the 10-10 card swap: `ghl_flow0` 320 return =
port 2, `ghl_flow2`/`ghl_flow3` 200 return A/B = ports 0/1, `ghl_flow1` unused = port 3 (Joe confirmed). 7-day
medians ~880 / ~450 / ~400 L/h. GHL sensor slots: 0 tank temp, 8 200 temp, 10 room temp, 11 room humidity
(humidity card in the Expansion Box since 10-11); 1 old pH input (ignored); 2 ORP-like input (varies, unused);
3-5 empty. Also present on this firmware (read-only so far): `DOSER[0-15]` (FILLLEVEL, CAPACITY; no GHL dosers
connected), `LEVELSENSOR`, `ILLUMINATION`, `TIMER`, `KHDIRECTOR`, `SPECIALFUNCTION`, `SYSTEM`; `DESCRIPTION` is
blank everywhere. The GHL clock runs 1 h slow (DST not enabled).

---

## 7b. Alerts and the feed watchdog (added 2026-10-10)

`/opt/reefcore/reef-alerts.py`, started every 5 min by `hydros-pull.py`, checks at most every 15 min and queues
messages to `reef_lab/data/outbox/alerts.jsonl`; the Reef Log bot listener on mccrae sends them ("Reef alert: …").
Not a replacement for controller alarms.

| Alert | Fires when | Clears when |
|---|---|---|
| Feed silent (Apex / Hydros / GHL) | no reading for 30 min | readings resume |
| Flow low | a GHL return line under 80% of its 7-day median for a full hour | back above |
| Salinity high | 3 h median within 0.3 ppt of the top of the range | median drops |
| Jug low | a dosing jug at 2 days or less (from `recipes.md`) | 'mixed …' logged |
| Trident stalled | no new result for 12 h (alk) / 30 h (Ca, Mg) | new results |

Sent once when it starts, reminded every 12 h, short "cleared" line when it ends. Quiet hours 22:00-07:00
(held, then sent at 07:00 if still active). State: `reef_lab/data/alerts-state.json`.
`reef-alerts.py check` prints what is active without sending anything.

**Instrument watch (added 2026-10-12)**, same plumbing:

| Alert | Fires when |
|---|---|
| Probe fault | a reading outside anything a reef can be (pH < 6 or > 9.5, salinity < 25 or > 40, temp < 15 or > 35 °C) |
| Frozen sensor | exactly the same value for 6 h on temps, pH, salinity or return flows (which normally move) |
| Probe drift | the Apex-vs-Hydros pH gap, or Apex-vs-Hydros / Apex-vs-GHL temp gap, moves > 0.15 pH / 0.5 °C from its 14-day median (the usual ~0.25 pH gap itself is not an alert) |
| Trident missed alk run | its run times are learned (currently ~00:20, 06:15, 12:40, 18:20); a run 2 h overdue fires (the 10-10 unplug would have alerted ~8 h after the last result instead of 12+) |

**Morning report** also has "Due by data" (sensor maintenance signals) since 10-12. The 06:25 cron now runs `/opt/reefcore/morning-report.sh`, which waits up to 15 min for the
Hydros feed to be fresh before building the report.

**GHL sensor slots (Joe 2026-10-10, updated 10-11):** slot 0 = tank temp (`temp_ghl`), 8 = 200 peninsula temp
(`temp_200`), 10 = room temp (`room_temp_ghl`), 11 = room humidity (`humidity`, %). Slots 6/7 went away when the
humidity card left the ProfiLux; GHL expansion cards must be configured in the ProfiLux first, then moved to the
Expansion Box. No salinity probe on the GHL. Mapped in `reef-baselines.md` (`ghl:ghl_sN`);
they show as gauges and in the report.

---

## 8. Telegram bots

| Bot | Sends | Reads replies |
|---|---|---|
| Reef Log bot (`@reeflog_bot`) | daily log, answers, confirmations, errors | `reef-log-bot.service` (single long-poll listener) |
| Reef Lab bot | (Hermes, retired) | — |
| Node Zero Watchdog | (ran on pizer; retired with it) | no |

Telegram allows only one `getUpdates` reader per bot, so the listener is the only reader.

Listener additions (10-12): long-poll 8 s (queued sign-in requests go out within seconds); sends both outboxes (`alerts.jsonl`, `ui.jsonl`, the latter with inline buttons); callbacks `auth:<id>:ok|no`, `dev:<sid>:out`, `ci:*` (check-in); 8 pm check-in and Sunday 09:00 shopping list are sent by the listener itself (state in `state/checkin-last`, `state/shopping-last`; no cron); commands `devices`, `supplies`, `shopping list`, `stock|received|have <item> <qty> [unit]`. Inbox kind `event` (e.g. fed) -> events + notes.

Listener behaviour (`tg.py`, 10-10): "status" / "connection status" (no "?" needed) gets an instant reply from
`reefchem.db` and `alerts-state.json`; questions are recognised by wording, not only by "?"; any other text is
noted in today's log and acknowledged ("📝 Noted in today's log…"), so nothing goes unanswered.

---

## 9. Command reference

### mccrae (`pct enter 103`)

```
/root/reef-log/reef-log.sh [--dry-run]        # run the daily log now
/root/reef-log/monthly-review.sh [--dry-run]  # monthly review
systemctl status reef-log-bot reef-voice
ls /root/reef-log/state/runs/                 # each run: JSON, digest, errors, lookback
```

Files: `reef-log.sh`, `prompt.md`, `tg.py`, `lookback.py`, `backfill.py`, `voice.py`,
`monthly-*`, `stage-code.sh`, `telegram.env` (600), `voice.token`, `palomino.token`, `state/`.
Cron `/etc/cron.d/reef-log`.

### reefcore (`pct enter 101`)

```
/opt/reefcore/reefchem.py report
/opt/reefcore/reefchem.py log alk 7.4 --note "Salifert"
/opt/reefcore/hydros-pull.py status | changes 24
/opt/reefcore/ato-watch.py runs 24
/opt/reefcore/ghl-pull.py show
systemctl restart nz-home          # needed after reefchem.py or server.py changes
```

### vincent

```
~claude/bin/reef-smoke.sh          # 17 checks of the whole pipeline
cat /mnt/reef_lab/log/2026/10/$(date +%F)-daily.md
```

### GitHub

See the repo README ("GitHub and publishing") for both repos, deploy keys and the push commands.

---

## 10. Open items (2026-10-12)

| Item | Status |
|---|---|
| Monthly-review cron line on mccrae | Joe to add: `0 7 1 * * root /root/reef-log/monthly-review.sh >/dev/null 2>&1` |
| GHL flow lines confirmed; 'look low for Royal Exclusives' question still open | watching |
| GHL clock 1 h slow: +1 h and enable DST | at-home list |
| nz-home login | **done 10-12** (Telegram-approved sign-in) |
| Maintenance page: Imperial background **done 10-12** (hull plating, rings, ticker, outline glows); pass 2 per-equipment blueprints (needs MP40 / gyre / Turbelle mapping) | Joe to choose |
| Reef PC: console mode (bigger touch targets, idle page rotation) | after the kiosk settles |
| Upgrade Group 2 | **built 10-12**; supplies need Joe's remaining counts (`supplies …` in Telegram) |
| Upgrade Group 3: normal-day model, before/after per event, power cost | **built 10-12**; Hydros/GHL ribbons need ~5 days of data; heaters + display lights not metered yet (where are they plugged in?) |
| Smart RO/DI for city water at the new place | roadmap |
| Upgrade Group 4: replay slider, ask the schematic, weekly photo review, controller-action decision | planned |
| GHL doser ESP32 retrofit (PoE, LSSS family, scales, 4 isolated triggers) | **parked** on the roadmap until the outlet PCB is done and the move |
| ATO pump flow (1 min into a cup) → gallons evaporated per day | at-home list |
| Hydros overrides, ORP probe, Apex vs Hydros pH gap ~0.3, D4 Mg regimen, salt batch test | at-home list |
| Water volume, WC volume, canary corals | tank profile TBD |
| Alk switching to CoreChem soda ash (500 g/5 L): compare pH bump vs the 10-05 baked batch | watching |
| Coral photos with IDs, Euphyllia types, locations | via Telegram |
| Phase 2: photo growth tracking, PAR history, Livestock tab | **built 10-10**; coral intake (dip/QT) still roadmap |
| Phase 3: business/sales, wishlist, QT workflow, cost page, emergency alerts | roadmap |
| Hermes program uninstall on reefcore (`/usr/local/lib/hermes-agent`); keep `/root/.hermes` (node, scripts symlink) | Joe, optional |
| Confirm `reef_lab` in snapshot task + bob replication | to check |
| LSSS API has no auth (incl. outlet/heater routes) | keep off the internet |

---

## 11. Lessons learned

- A small local model on CPU can do one simple step, not a multi-step job; it invents details.
- Rules with exceptions get skipped; flat rules ("never give dosing advice") hold.
- A model saying it saved a file is not proof; the script checks.
- Know the instrument schedule before flagging stalls (Trident Ca/Mg run once a day).
- Change one shared script, check everything that imports it (nz-home imports reefchem).
- Telegram: one reader per bot; a crashing reader swallows messages, so keep the listener soft-failing.
- Controllers lie politely: the GHL (older firmware) echoed the last value for a bad query; fw 7.52 NACKs properly.
- GHL: configure an expansion card in the ProfiLux first, then move it to the Expansion Box; the TCP API wants one
  long-lived connection (~3 s cooldown between connections).
- Store sensor history under logical names and map physical ports in code; plugs move.
- Shell: `<placeholders>` break bash; curly quotes from phone apps break commands;
  `pct exec` needs `bash -lc` for tools on a login PATH; `cp -p` onto the NFS dataset fails (ownership).
- Alk swings about 1 dKH through the day: a single Trident test is not "high" or "low" on its own; compare whole
  daily cycles (the 12:45 test after the 09:45 bolus always reads highest).
- Hydros stores watts only on a 20% change or hourly, so integrate it as a step line with a gap cap, never average rows.
- The reef_lab share lives on Maximilian: when everything goes stale at once, check Maximilian first.
