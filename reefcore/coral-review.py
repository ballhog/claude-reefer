#!/usr/bin/env python3
"""Weekly coral photo review (Group 4 item 3, 2026-10-14). reefcore CT 101, stdlib + ffmpeg.

For every living coral with a new photo in the last 7 days, Claude looks at the newest photo next to the
previous one (if any) and writes a short, hedged note on colour, polyp extension, tissue/edges and growth.
Observations only: no dosing advice, and it says so when light or angle make a comparison unreliable.

  coral-review.py dry            review and print, write nothing, send nothing (default)
  coral-review.py run            write the notes into each coral's timeline, save data/coral-reviews/<date>.md,
                                 queue the Telegram summary (sent by the Reef Log bot)
  coral-review.py one C-001      review one coral's latest photo now and print (writes nothing)
  coral-review.py due            `run`, but only on Sunday from 08:30 if this week's review isn't written yet
                                 (max 3 attempts a day; one at a time)

Schedule: hydros-pull.py (cron every 5 min) starts `coral-review.py due`, the same way it starts reef-alerts
and ato-watch; no cron line of its own. So it runs Sunday ~08:30-08:35, before the 09:00 shopping list.
Timeline line written:  - <date time> review: <note> (Claude photo review of <photo date>[ vs <prev date>])
"""
import base64, json, os, re, subprocess, sys, tempfile, time, urllib.error, urllib.request
from pathlib import Path

LAB = Path("/root/reef-lab")
CORALS, PHOTOS, DATA = LAB / "corals", LAB / "photos", LAB / "data"
OUTBOX = DATA / "outbox" / "ui.jsonl"          # tg.py on mccrae sends these
REVIEWS = DATA / "coral-reviews"
TL = re.compile(r"^- (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) (.*)$")
PH = re.compile(r"photo: /mnt/reef-lab/photos/(\S+\.jpg)(?:\s+[—-]\s*(.*)|\s*\((.*)\))?")
WEEK, STALE_DAYS = 7 * 86400, 14


def env():
    e = {}
    try:
        for l in open("/etc/nz-home.env"):
            if "=" in l and not l.lstrip().startswith("#"):
                k, v = l.strip().split("=", 1)
                e[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return e


E = env()
KEY = os.environ.get("ANTHROPIC_API_KEY") or E.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("NZ_REVIEW_MODEL") or E.get("NZ_REVIEW_MODEL") or E.get("NZ_HOME_MODEL") or "claude-haiku-4-5-20251001"


def ts(s):
    return time.mktime(time.strptime(s, "%Y-%m-%d %H:%M"))


def corals():
    out = []
    for l in (CORALS / "registry.md").read_text().splitlines():
        c = [x.strip() for x in l.strip().strip("|").split("|")]
        if len(c) >= 8 and re.match(r"C-\d{3}$", c[0]):
            out.append({"id": c[0], "name": c[1], "status": c[7].lower()})
    return out


def coral_file(cid):
    f = CORALS / f"{cid}.md"
    t = f.read_text(errors="ignore") if f.exists() else ""
    prof, body = {}, t
    if t.startswith("---\n"):
        head, _, body = t[4:].partition("\n---\n")
        for l in head.splitlines():
            if ":" in l:
                k, v = l.split(":", 1)
                prof[k.strip()] = v.strip()
    tl = [{"time": m[1], "text": m[2]} for m in (TL.match(l) for l in body.splitlines()) if m]
    photos = []
    for e in tl:
        m = PH.match(e["text"])
        if m:
            p = PHOTOS / m[1]
            if p.exists():
                photos.append({"time": e["time"], "path": p, "caption": (m[2] or m[3] or "").strip()})
    care = ""
    m = re.search(r"^## Care sheet.*?(?=^Timeline|\Z)", body, re.M | re.S)
    if m:
        care = m.group(0)
    return f, prof, tl, photos, care


def small_jpeg(p):
    """Downscale to <= 1280 px on the long edge (keeps tokens and upload size sane)."""
    out = Path(tempfile.mkstemp(suffix=".jpg")[1])
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(p), "-vf",
                        "scale='if(gt(iw,ih),min(1280,iw),-2)':'if(gt(iw,ih),-2,min(1280,ih))'", "-q:v", "4", str(out)],
                       capture_output=True)
    data = out.read_bytes() if r.returncode == 0 and out.stat().st_size > 1000 else Path(p).read_bytes()
    out.unlink(missing_ok=True)
    return base64.b64encode(data).decode()


PROMPT = """You are reviewing reef coral photos for Joe, who has kept reef tanks for over 20 years. Coral: {cid} {name} ({species}; {ctype}).
Care-sheet light/colour/problem hints (general guidance, may be wrong for this colony):
{care}
Recent notes on this coral (newest last):
{notes}

{what}

Write what you can actually SEE, as careful observations, not diagnoses. Cover, briefly: colour (vs the previous photo if there is one),
polyp / tentacle extension, tissue and edges (recession, bleaching, bare skeleton, anything on or near it), and visible growth or size
change. If light colour, white balance, angle or distance differ between photos, say the comparison is unreliable for that aspect
rather than guessing. Never recommend dose or parameter changes. Do not invent details you cannot see.

Reply with JSON only:
{{"note": "<one or two plain sentences for the coral's timeline, max 45 words>",
  "flag": "none" | "watch" | "look",   // look = something Joe should check in person soon
  "flag_reason": "<short, or empty>",
  "comparable": true | false,          // false if the two photos can't be fairly compared (or there is no previous photo)
  "confidence": "low" | "medium" | "high"}}"""


def review(c):
    f, prof, tl, photos, care = coral_file(c["id"])
    if not photos:
        return None
    new = photos[-1]
    prev = next((p for p in reversed(photos[:-1]) if ts(new["time"]) - ts(p["time"]) >= 3 * 86400), None)
    notes = [e["text"] for e in tl if not e["text"].startswith(("photo:", "set "))][-6:]
    hints = "\n".join(l for l in care.splitlines() if re.match(r"- \*\*(Light|Pests|Notes for Joe)", l))[:1500] or "(none)"
    if prev:
        what = (f"Image 1 is the PREVIOUS photo ({prev['time']}; caption: {prev['caption'] or 'none'}). "
                f"Image 2 is the NEW photo ({new['time']}; caption: {new['caption'] or 'none'}). Compare them.")
    else:
        what = (f"There is only one photo ({new['time']}; caption: {new['caption'] or 'none'}). Describe the baseline condition; "
                "there is nothing to compare against yet.")
    text = PROMPT.format(cid=c["id"], name=prof.get("common_name") or c["name"], species=prof.get("scientific_name") or "?",
                         ctype=prof.get("type") or "?", care=hints, notes="\n".join(notes) or "(none)", what=what)
    content = []
    for p in ([prev] if prev else []) + [new]:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": small_jpeg(p["path"])}})
    content.append({"type": "text", "text": text})
    req = urllib.request.Request("https://api.anthropic.com/v1/messages",
                                 data=json.dumps({"model": MODEL, "max_tokens": 400,
                                                  "messages": [{"role": "user", "content": content}]}).encode(),
                                 headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Claude API HTTP {e.code}: {e.read()[:200]!r}")
    raw = "".join(b.get("text", "") for b in resp.get("content", []))
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        j = json.loads(m.group(0)) if m else {}
    except ValueError:
        j = {}
    if not j.get("note"):
        j = {"note": raw.strip()[:300], "flag": "none", "flag_reason": "", "comparable": False, "confidence": "low"}
    j.update({"id": c["id"], "name": prof.get("common_name") or c["name"], "file": f, "photo": new["time"],
              "prev": prev["time"] if prev else None,
              "tokens": resp.get("usage", {}).get("input_tokens", 0) + resp.get("usage", {}).get("output_tokens", 0)})
    return j


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "dry"
    if mode == "due":
        lt = time.localtime()
        if lt.tm_wday != 6 or (lt.tm_hour, lt.tm_min) < (8, 30):
            return
        day = time.strftime("%Y-%m-%d", lt)
        if (REVIEWS / f"{day}.md").exists():
            return
        import fcntl
        REVIEWS.mkdir(parents=True, exist_ok=True)
        lock = open(REVIEWS / ".lock", "w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return                                        # another run is going
        att = REVIEWS / f".attempts-{day}"
        n = int(att.read_text() or 0) if att.exists() else 0
        if n >= 3:
            return
        att.write_text(str(n + 1))
        mode = "run"
    if not KEY:
        sys.exit("no ANTHROPIC_API_KEY (looked in /etc/nz-home.env)")
    now = time.time()
    gone = ("dead", "sold", "gone", "lost", "traded", "removed")
    live = [c for c in corals() if coral_file(c["id"])[1].get("status", "alive").lower() not in gone]
    if mode == "one":
        cid = sys.argv[2].upper()
        r = review(next(c for c in corals() if c["id"] == cid))
        print(json.dumps({k: (str(v) if isinstance(v, Path) else v) for k, v in (r or {}).items()}, indent=1))
        return
    results, stale = [], []
    for c in live:
        _, _, _, photos, _ = coral_file(c["id"])
        last = ts(photos[-1]["time"]) if photos else None
        if last is None or now - last > STALE_DAYS * 86400:
            stale.append((c, last))
        if last is not None and now - last <= WEEK:
            try:
                r = review(c)
                if r:
                    results.append(r)
            except Exception as e:
                results.append({"id": c["id"], "name": c["name"], "error": str(e)})
    day = time.strftime("%Y-%m-%d")
    lines = [f"# Coral photo review {day}", "", f"Model {MODEL}. Observations from photos, not diagnoses.", ""]
    for r in results:
        if r.get("error"):
            lines.append(f"- {r['id']} {r['name']}: review failed ({r['error']})")
        else:
            vs = f" vs {r['prev'][:10]}" if r["prev"] else " (first photo, baseline)"
            fl = f" **{r['flag'].upper()}**: {r['flag_reason']}" if r.get("flag") in ("watch", "look") else ""
            lines.append(f"- {r['id']} {r['name']} (photo {r['photo'][:10]}{vs}; confidence {r.get('confidence')}): {r['note']}{fl}")
    never = [c for c, last in stale if last is None]
    old = sorted(((c, last) for c, last in stale if last), key=lambda x: x[1])
    lines += ["", f"Photos wanted: {len(stale)} corals with no photo in {STALE_DAYS} days "
                  f"({len(never)} never photographed)."]
    report = "\n".join(lines) + "\n"
    print(report)
    print(f"[{sum(r.get('tokens', 0) for r in results)} tokens]")
    if mode != "run":
        print("(dry run: nothing written or sent)")
        return
    stamp = time.strftime("%Y-%m-%d %H:%M")
    for r in results:
        if r.get("error"):
            continue
        vs = f" vs {r['prev'][:10]}" if r["prev"] else ""
        with open(r["file"], "a") as g:
            g.write(f"- {stamp} review: {r['note']} (Claude photo review of {r['photo'][:10]}{vs}"
                    f"{'; ' + r['flag'] + ': ' + r['flag_reason'] if r.get('flag') in ('watch', 'look') else ''})\n")
    REVIEWS.mkdir(parents=True, exist_ok=True)
    (REVIEWS / f"{day}.md").write_text(report)
    ok = [r for r in results if not r.get("error")]
    flagged = [r for r in ok if r.get("flag") in ("watch", "look")]
    msg = [f"🪸 Weekly coral photo review: {len(ok)} reviewed"]
    for r in flagged:
        msg.append(f"{'👀' if r['flag'] == 'look' else '•'} {r['id']} {r['name']}: {r['flag_reason'] or r['note']}")
    if ok and not flagged:
        msg.append("Nothing to flag; notes are on each coral's page.")
    if not ok:
        msg.append("No new coral photos this week.")
    want = [c["id"] + " " + c["name"] for c, _ in (old + [(c, None) for c in never])][:8]
    if want:
        msg.append(f"Photos wanted ({len(stale)} with none in {STALE_DAYS} d): " + ", ".join(want) + (" …" if len(stale) > 8 else ""))
    msg.append("Send a photo to the bot with the coral id in the caption (e.g. C-012), or + Add photo on the coral page.")
    OUTBOX.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTBOX, "a") as g:
        g.write(json.dumps({"ts": int(now), "text": "\n".join(msg), "buttons": []}) + "\n")
    try:                                       # also to the home-screen app
        import importlib.util as _iu
        _sp = _iu.spec_from_file_location("webpush", "/opt/nz-home/webpush.py")
        _wp = _iu.module_from_spec(_sp); _sp.loader.exec_module(_wp)
        _wp.send("Coral photo review", " ".join(msg[:2])[:180], "/corals", "coral-review")
    except Exception as e:
        print(f"push failed: {e}")
    print("written: timelines, " + str(REVIEWS / f"{day}.md") + ", Telegram summary queued")


if __name__ == "__main__":
    main()
