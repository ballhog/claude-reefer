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
- Group 4: scope settled 2026-10-13 (controller decision made). LSSS GHL driver DONE and deployed 10-13 (see Group 4 item 0).
- Groups 5-8: roadmap sketched 2026-10-13. Group 7 has a full design doc (LSSS repo docs/GROUP-7-HARDEN-LSSS.md);
  the others get their own planning pass.
- Group 9 (LSSS sign-in) was folded into Group 7 on 10-13; Group 9 reopened as a candidate-ideas list.

Arc: watch the tank (1-3) -> touch it carefully (4) -> understand it (5) -> integrate and guard it (6)
-> harden the LSSS (7) -> tie it to the physical world (8).

Division of labour (Joe 10-13): the LSSS is the gatherer and the deterministic controller; Claude Reefer is the compute.
Only the LSSS talks to the controllers; Claude Reefer reads through the LSSS.

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
- Control path (Joe 10-13): Claude Reefer asks -> the LSSS decides (its own rules, veto) -> the GHL switches.
  Claude Reefer never writes to the GHL directly. A max-on timer set in the GHL itself is the last backstop, so even an
  LSSS crash can't leave a pump running forever.
- Guardrails for any control: signed-in device only, press-and-hold to confirm, every switch logged,
  safety auto-off timeout.
- The old idea of feed pause / maintenance / water-change mode via GHL SPECIALFUNCTION is not in scope.

### Build items
0. DONE 10-13: LSSS GHL driver rewritten for the GHL local API v1.1 (text, TCP 10002, read-only). The old ws://host/ws
   protocol stopped answering after fw 7.52 + PLM-WiFiLAN, so the LSSS showed "device offline". LSSS commits 8217df9
   (driver, 24 tests) and 9b4a48d (docs), deployed via the System-page update. Reads probes + setpoints, 4 flows,
   24 switch channels with load current, level sensors; values match Claude Reefer's. Sensor names/kinds come only from
   `ghl.sensor_layout` in the Pi's runtime config (empty inputs still return numbers, e.g. 44 "mV").
   NEXT: once it has run clean for a day or two, point Claude Reefer at the LSSS for GHL data (only one thing should
   poll port 10002; the controller refuses new connections for ~3 s after one closes).
1. Replay slider on the schematic (24 h / 7 d): scrub the maintenance drawing back through time.
2. Ask the schematic: tap equipment, ask, Claude answers from that equipment's data.
3. Weekly coral photo review (colour/growth notes per coral).
4. First control: mixing-station mixing pump on/off. Low blast radius (a barrel, not the display).
   Joe 10-13: currently on the Hydros (read-only from here). Plan: move it to a GHL socket; switched only through
   the LSSS. Needs Group 7 pillar 6 (LSSS sign-in) and LSSS socket switching with rules first.
5. GHL outlet bar: per-socket switching (through the LSSS) + per-socket current into alerts.
   Joe 10-13: nothing on the bar yet. The mixing pump is the first device; add others one at a time.
6. Right-now current alerting: abnormal current, not the slow 2-week watts drift Group 3 does. Catches a straining
   skimmer, a powerhead bound on a snail, a stalling roller motor before other signals. Sources: Hydros watts, GHL sockets
   (now readable through the LSSS).

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

## Group 7: harden the LSSS (redefined 2026-10-13; absorbs old Group 9)
Full design: LSSS repo `docs/GROUP-7-HARDEN-LSSS.md` (latest 9b8547b). Design only, not built.
Extend, don't rebuild: the LSSS already has fault_service + HealthPublisher heartbeats; Group 7 extends them,
levels Apex/GHL up to the Hydros driver, and adds the network ladder and correlated plain-language notices.
Joe: connection failure handling must be "next level" - no blind failing, try every tool before giving up, and a
disconnection notice a non-technical person can follow. Lessons: the GHL sat "offline" for weeks with no reason given;
"Configured" said nothing about whether it worked; a GHL card went in and the software showed nothing at all.
1. Patients and charts: every connection (controllers, the LSSS's own sensors/outputs, MQTT, Influx, Telegram, the
   tunnel, its own network and the internet) has a chart: state, plain diagnosis, last success vs last attempt, what
   was tried, next retry, incident history, what it's supposed to have.
2. Never stop trying: back-off with jitter, forever; stale-but-connected counts as failed; respect fragile devices.
3. Try what it has, report what it sees: every way in (GHL text API -> old protocol -> port probes; name vs IP;
   LAN vs Tailscale), and never blank: "unknown reading on sensor 7", new/missing slots are events, trust labels.
4. Diagnostic ladder outward from the LSSS itself: own link -> gateway/LAN -> DNS -> internet -> device present ->
   port -> protocol -> sane data. Report the first broken rung; correlate (internet down = one notice, not three).
5. Plain-language notice: sentences for a reef sitter, one root-cause message per incident plus a recovery message,
   no crying wolf, queued + shown on the LSSS screen when Telegram itself is unreachable.
6. Lock the doors (was Group 9): Telegram-approved sign-in, one check on every POST/PUT/DELETE + secret GETs, reads
   stay open, front screen + SSH as no-lockout paths, scoped machine keys, general enough for labs.
   Gates Group 4 control. Open: tunnel read-only or control when signed in? Cloudflare Access as a second lock?
7. Carried over, LSSS-focused: watch the watcher (LSSS <-> Claude Reefer), sensor trust and calibration
   cross-checks, multi-person read-only access to notices.
Order: 6 (sign-in) -> 1-2 -> 4-5 with a failure simulator and tests -> 3 -> Connections page -> 7.

## Group 8: physical-world tracking (NFC)
1. Chemicals and supplies: NFC tag on each jug, salt box, reagent bottle. Tap on open / refill / new box ->
   supplies forecast becomes ground truth; lot and open date recorded; reagent age warnings (Trident reagents);
   new-lot taps land in the event log so before/after can spot "tests shifted when the new lot started".
2. Frag tracking: encapsulated glass-capsule NFC tags epoxied into frag plugs. Tap to open that colony's whole history
   (origin, placement moves, photos, growth, response to events). Lineage travels with frags sold or traded.
   Read range is touch-distance underwater: a deliberate tap, not a tank scan. Saltwater encapsulation to verify.

## Group 9: candidate ideas (reopened 2026-10-13; brainstorm, not committed scope)
The old Group 9 sign-in is now Group 7 pillar 6. Group 9 is a fresh group; ideas so far:
1. Watch the physical world the sensors can't see (arguably the strongest idea): a camera OUTSIDE the glass (an
   in-water camera fouls within days) plus Claude, looking at the tank and the plumbing.
   - Light on/off timing and photoperiod (catch the day the lights don't come on); movement and flow (a pump running
     but not moving water shows as stillness); slow change across successive images.
   - Algae by change over time: glass filming up faster ("scraping more often than you used to"), coralline spread,
     glass due for a wipe. Same approach as the coral photo review, pointed at surfaces.
   - Cyano: reddish-brown, stringy, blotchy mat on sand/rock, told apart from green film by colour + texture +
     location; more confident the more tank history it has seen.
   - The key point is the tie-together: join what the camera sees to nitrate/phosphate trends, flow, dosing and
     feeding, water changes. "Cyano on the sand" becomes "cyano + nutrients climbing 10 days + flow dropped on that
     side + feeding up": a likely cause, not just an observation. The camera sees the result; chemistry and flow
     explain it backwards.
   - Camera to start with (Joe 10-13): Amcrest IP5M-T1179EW-AI-V3, 5MP PoE turret (turret, not dome, to avoid glare
     off the glass; local RTSP/ONVIF, no cloud). Backup Reolink RLC-520A; Pi Camera Module 3 + PoE HAT for close-ups.
     Confirm IR can be switched off and RTSP is available before buying.
   - Camera plan (Joe, later 10-13): two kinds of PoE camera. Observer cameras first: display (lights-on, water
     movement, algae/cyano) + sump equipment monitor (ATO level, skimmer cup). Spawn instrument = far goal only (clear
     PVC overflow pipe in IR + optical trigger/turbidity sensor arming the camera; needs a dark-field optics bench test,
     spawn-capture storage/retention, a heartbeat on the watcher). Imaging runs on vincent (prototype), then a
     dedicated x86 mini PC with Intel iGPU/QuickSync (production), not a Pi. The LSSS stays out of imaging; it only
     arms the spawn watcher.
   - Setup rules: IR off; white balance + exposure locked; same times and light each day; square to the glass, room
     lights dim; never moved once set.
2. Know what's normal for the livestock, not just the water: infer animal wellbeing (polyp extension, colour, fish
   eating) from the coral photo log plus feeding events.
