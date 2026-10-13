# Claude Reefer upgrade plan (2026-10-12, roadmap extended 2026-10-13)

Joe: "make Claude Reefer better than ever", built in groups, each planned before building.
Ground rules kept: scripts do the arithmetic; no dosing advice from a model; urgent alarms stay on the controllers;
nothing life-critical (heaters, return pumps) is ever under app control. Controller writes: decided 2026-10-13 (Group 4).

## Status (2026-10-13)
- Group 1: DONE and pushed (live screens, tap-for-history, maintenance by data, instrument watch).
- Group 2: DONE and pushed (Telegram-approved sign-in, + Log, mixed today, photo upload, 8 pm check-in,
  supplies forecast + Sunday list, plain-words supplies parsing, hand-test lead-ins).
- Group 3: DONE and pushed (nz-home 2e30df3 normal day, 8849d90 before/after UI, b59c4b7 power;
  claude-reefer 08c3149, 361cc0d, 4752a90, docs b3686b4).
  - Normal day: ribbon on 24 h charts, off-pattern tag, `daily` table. Hydros/GHL ribbons activate after ~5 days of data.
  - Before/after: `event-effects.json`, chart labels, maintenance pop-up notes, report section. Trident compared over whole
    daily cycles (alk swings ~1 dKH/day; the 12:45 post-bolus test is always highest, not an outlier).
  - Power: $0.217/kWh (Joe 10-12). First full day 10-11: 8.2 kWh/day, $1.77/day, ~$54/month for Hydros-metered outputs only.
    Watts drift (10% shown, 20% = task due) feeds M01/M02/M05/M19 once 3+ days of history exist.
  - Still open: where heaters and display lights are plugged in (not metered); optional 7-day window for dose-change events.
- Group 4: scope settled 2026-10-13 (controller decision made), next to build.
- Groups 5-8: roadmap sketched 2026-10-13 (Joe, commute). Not planned in detail yet; each gets its own planning pass.

Arc: watch the tank (1-3) -> touch it carefully (4) -> understand it (5) -> integrate and guard it (6)
-> harden it (7) -> tie it to the physical world (8).

## Group 1: live screens, history everywhere, maintenance by data, instrument watch (DONE)
- `/api/events` (SSE) + watcher; GHL flows and Hydros outputs every minute (`/etc/cron.d/reefcore-fast`).
- `/api/series` + shared `/static/nz.js` chart (band, events, 24 h / 7 d / 30 d, `?chart=` deep link).
- `reefchem.data_due()`: return-flow drop, skimmer cup sensor, roller overfill, RO/DI TDS (applies to every resin stage).
- reef-alerts instrument watch: probe fault, frozen sensor, probe-pair drift, missed Trident alk run (learned times).

## Group 2: two-way logging (DONE)
- Sign-in: 6-digit code on screen, Approve/Deny from the Reef Log bot; cookie 30 d / 183 d; `devices` in Telegram.
- `+ Log` (tests, WC, RO/DI), hold "mixed today", coral/animal photo upload, all into the same inbox as Telegram.
- 8 pm check-in and Sunday 09:00 shopping list sent by the bot listener itself (cron edits are blocked from Claude's side).
- `data/supplies.md` + `reefchem.supplies()`; Telegram `supplies ...` in plain words (several items, "6 55 lb boxes").

## Group 3: the tank's normal day (DONE 2026-10-12)
Data available: Apex + Hydros since 2026-09-03, GHL since 10-10, Hydros outputs/watts since 10-09.
1. Normal day
   - Half-hour profile (p10 / median / p90 per time of day, last 21 days, last 6 h excluded, WC windows excluded for temps)
     for temp, both pH, salinity, sump temp, GHL temps, return flows, room temp, humidity -> `data/profiles.json`
     rebuilt hourly from the 15-min `reefchem.py pull`.
   - 24 h history charts draw the normal-for-this-time ribbon behind today's line.
   - Off-pattern flag: last 2 h >= 75% outside the band (band widened 25%) -> small tag on the home gauge + report section.
     No Telegram alerts at first.
   - `daily` table (kept forever, backfilled from 09-03): pH swing (p95-p5), temp swing, salinity median + drift,
     return-flow medians, ATO runs, skimmer watts. Chart links from the related sensor ("pH swing per day").
2. Before/after per event: maintenance, mixes, WC, RO/DI, fed, Hydros switches/overrides, dose-rate changes, new corals.
   24 h / 72 h vs the day before, judged against normal day-to-day wobble from step 1; "no measurable effect" otherwise.
   Morning report + reef log (worded as hypotheses), chart marker cards, maintenance pop-up history, per-type patterns.
3. Power: kWh/day per Hydros output, $/month at $0.217/kWh, top consumers, watts drift as a health
   signal (skimmer / return pumps) feeding "by data". Needs from Joe: $/kWh; where the heaters are plugged in.

## Group 4: look, then touch carefully (NEXT)
### Controller-action decision (made 2026-10-13)
Joe's rule: controllers are mostly monitors. Centralising control makes a single point of failure, and livestock makes
it mission-critical. Heaters run on Rancos straight to the wall; return pumps are independent too. Their running must
never depend on a soft layer. Only "don't care if it's off" gear is a candidate (mixing pump, filter roller, skimmer).
- Apex and Hydros: effectively read-only (cloud-mediated). Real write paths: the LSSS (Joe's own) and the GHL ProfiLux
  (API at full access, 10.0.0.215; every script still only reads).
- Guardrails for any control: signed-in device only, press-and-hold to confirm, every switch logged,
  safety auto-off timeout.
- The old idea of feed pause / maintenance / water-change mode via GHL SPECIALFUNCTION is not in scope.

### Build items
1. Replay slider on the schematic (24 h / 7 d): scrub the maintenance drawing back through time.
2. Ask the schematic: tap equipment, ask, Claude answers from that equipment's data.
3. Weekly coral photo review (colour/growth notes per coral).
4. First control: mixing-station mixing pump on/off. Low blast radius (a barrel, not the display).
   OPEN: is it on an LSSS outlet or on the Hydros? Decides feasibility.
5. GHL outlet bar: per-socket switching from the app + per-socket current into alerts. ~5-6 devices.
   OPEN: which devices sit on the bar.
6. Right-now current alerting: abnormal current, not the slow 2-week watts drift Group 3 does. Catches a straining
   skimmer, a powerhead bound on a snail, a stalling roller motor before other signals. Sources: Hydros watts, GHL sockets.

### Future shelf (not scheduled)
- Joe's own custom outlet box: built to be less failure-prone than off-the-shelf; the only thing that could earn
  heater control.
- Shelly (or similar) current monitoring on circuits the Hydros doesn't see: true load/power picture, monitoring only,
  feeds item 6.

## Group 5: understand the tank (the headliners)
1. Prediction window: run the daily digest's drift forward. "Alk down a little each day for 5 days; at this rate
   half a point low by Friday." Same engine as the digest, a new panel. (Dose numbers still come from scripts.)
2. Ask anything: plain-language questions across all joined data ("why did pH drop Tuesday night?"), cross-referencing
   feeding, skimmer watts, room conditions, events. Extends "ask the schematic" to the whole system.
3. Coral growth story: per-colony timeline from the photo log; growth over months linked to stability periods
   ("doubled in 90 days, after alk steadied"). Builds on the weekly photo review.

## Group 6: LSSS <-> Claude Reefer integration and two-layer safety
Division of labour: the LSSS is the deterministic layer (rules, scripts, life support that runs whether or not
anything smart is watching); Claude Reefer is the intelligence layer on top. Neither pretends to be the other.
1. Review and clean the LSSS interface: every sensor, output and rule state legible to Claude Reefer in one
   well-defined shape (authoritative, real-time, no scraping).
2. Clear definition of what can be controlled and how (Group 4 frames it; Group 6 makes it final).
3. Rules in both layers: time limits, overcurrent, sanity checks in Claude Reefer AND in the LSSS.
   The LSSS holds the final veto ("you told me to keep this on; it's been a week; is that right?"),
   so a wrong, stale or crashed smart layer can't make it do something stupid.

## Group 7: review and harden
Purpose (Joe): as the groups land, go back and check we built what we meant and put the thought in, then close out.
1. Watch the watcher: if Claude Reefer itself goes quiet (digest stops, feeds stall), Joe is told.
2. Multi-person access: someone else (travel, a reef buddy) can get the digest and alerts and see what normal looks like.
3. Sensor trust and calibration: cross-check probes against each other and against hand tests; catch a probe that
   reads wrong confidently.

## Group 8: physical-world tracking (NFC)
1. Chemicals and supplies: NFC tag on each jug, salt box, reagent bottle. Tap on open / refill / new box ->
   supplies forecast becomes ground truth; lot and open date recorded; reagent age warnings (Trident reagents);
   new-lot taps land in the event log so before/after can spot "tests shifted when the new lot started".
2. Frag tracking: encapsulated glass-capsule NFC tags epoxied into frag plugs. Tap to open that colony's whole history
   (origin, placement moves, photos, growth, response to events). Lineage travels with frags sold or traded.
   Read range is touch-distance underwater: a deliberate tap, not a tank scan. Saltwater encapsulation to verify.
