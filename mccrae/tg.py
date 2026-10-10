#!/usr/bin/env python3
"""Reef Log Telegram helper (mccrae). stdlib only.

  tg.py listen               run forever, answer at once (systemd service reef-log-bot)
  tg.py collect              same, one pass (fallback from cron):
                               - "alk 7.4", "ca 430 mg 1350" ... -> hand test, queued for reefchem
                               - 👍 / 👎 buttons under a digest -> filed as agree / disagree
                               - anything else -> filed as Joe's reply in the next morning's log run
  tg.py take                 print pending replies and clear them (used by reef-log.sh)
  tg.py send FILE [--buttons DATE]   send FILE's text; --buttons adds 👍/👎 for that day's entry
"""
import json, os, re, subprocess, sys, threading, time, urllib.parse, urllib.request

BASE = "/root/reef-log"
ENV = f"{BASE}/telegram.env"
OFFSET = f"{BASE}/state/tg-offset"
PENDING = f"{BASE}/state/replies-pending.txt"
INBOX = "/mnt/reef-lab/data/inbox/hand-tests.jsonl"   # reefchem pull on reefcore ingests this
CORALS = "/mnt/reef-lab/corals"                         # registry.md + C-###.md timelines
PHOTOS = "/mnt/reef-lab/photos"                         # photos Joe sends, YYYY/MM/YYYY-MM-DD_HHMM_<subject>.jpg
HAND = {"alk": "alk", "kh": "alk", "dkh": "alk", "ca": "calc", "calc": "calc", "mg": "mag", "mag": "mag",
        "ph": "ph", "temp": "temp", "sal": "salinity", "salinity": "salinity", "no3": "no3", "po4": "po4"}
WC_RE = [re.compile(r"\b(?:wc|water ?change|changed|swapped)\b\D{0,20}?(\d+(?:\.\d+)?)\s*(?:g|gal|gals|gallons?)\b", re.I),
         re.compile(r"(\d+(?:\.\d+)?)\s*(?:g|gal|gals|gallons?)\b.{0,20}?\b(?:wc|water ?change)", re.I)]
PAIR = re.compile(r"^\s*([a-zA-Z0-9]+)\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*$")


def env():
    vals = {}
    with open(ENV) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"')
    return vals["TG_TOKEN"], vals["TG_CHAT"]


def api(token, method, params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", data, timeout=60) as r:
        out = json.load(r)
    if not out.get("ok"):
        raise SystemExit(f"telegram {method} failed: {out}")
    return out["result"]


def soft(token, method, params):
    """Replies, button edits, confirmations: never let a failure stop collection."""
    try:
        return api(token, method, params)
    except Exception as e:
        print(f"telegram {method} skipped: {e}", file=sys.stderr)


def bands():
    out = {}
    try:
        for l in open("/mnt/reef-lab/data/reef-baselines.md"):
            c = [x.strip() for x in l.strip().strip("|").split("|")]
            if len(c) == 5:
                try:
                    out[c[0]] = (float(c[3]), float(c[4]))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def hand_test(text):
    """'alk 7.4 ca 430' / 'alk 7.4, ca 430' -> [(param, value)] or None if it isn't purely hand tests."""
    toks = re.split(r"[,;\n]+|\s+(?=[a-zA-Z])", text.strip())
    out = []
    for tok in toks:
        if not tok.strip():
            continue
        m = PAIR.match(tok)
        if not m or m.group(1).lower() not in HAND:
            return None
        out.append((HAND[m.group(1).lower()], float(m.group(2))))
    return out or None


SYSTEM_L = 2800   # approx system water volume in litres (TBD, Joe to confirm)
RODI_WORD = r"(?:ro\s*/\s*di|rodi|ro\s+di|ro\s+water|fresh\s*water|freshwater)"
UNIT = r"(gal|gals|gallons?|g|l|liters?|litres?)"
RODI_RE = [re.compile(r"(\d+(?:\.\d+)?)\s*" + UNIT + r"\b[^\d]{0,30}?\b" + RODI_WORD + r"\b", re.I),
           re.compile(r"\b" + RODI_WORD + r"\b[^\d]{0,20}?(\d+(?:\.\d+)?)\s*" + UNIT + r"\b", re.I)]


def rodi_swap(text):
    """'added 10 gal rodi' / 'swapped 5 gallons for ro/di' / 'rodi 20 L' -> gallons, else None."""
    for r in RODI_RE:
        m = r.search(text)
        if m:
            v, u = float(m.group(1)), m.group(2).lower()
            return round(v / 3.785, 2) if u.startswith("l") else v
    return None


def latest_salinity():
    try:
        import sqlite3
        db = sqlite3.connect("file:/mnt/reef-lab/data/reefchem.db?mode=ro", uri=True, timeout=5)
        r = db.execute("SELECT value FROM readings WHERE param='salinity' AND source='hydros' "
                       "ORDER BY ts DESC LIMIT 1").fetchone()
        return r[0] if r else None
    except Exception:
        return None


def water_change(text):
    for r in WC_RE:
        m = r.search(text)
        if m:
            return float(m.group(1))
    return None


CID = re.compile(r"^\s*c-?(\d{1,4})\b[\s:,-]*(.*)$", re.I | re.S)


def coral_id(text):
    """'C-3 looks great' / 'c003: note' -> ('C-003', 'looks great'); None if not a coral reference."""
    m = CID.match(text or "")
    return (f"C-{int(m.group(1)):03d}", m.group(2).strip()) if m else None


def registry():
    rows = {}
    try:
        for l in open(os.path.join(CORALS, "registry.md")):
            c = [x.strip() for x in l.strip().strip("|").split("|")]
            if len(c) >= 8 and re.match(r"C-\d{3}$", c[0]):
                rows[c[0]] = c
    except OSError:
        pass
    return rows


FIELDS = ["common_name", "scientific_name", "family", "type", "morph", "source", "acquired", "cost",
          "size_at_acquisition", "buoyant_weight_g", "location", "par", "flow", "aggressive", "feeding",
          "parent", "children", "frag_count", "last_fragged", "status", "sold_to", "sold_date", "price", "notes"]
ALIAS = {"name": "common_name", "common": "common_name", "trade": "common_name", "species": "scientific_name",
         "scientific": "scientific_name", "latin": "scientific_name", "from": "source", "vendor": "source",
         "bought": "acquired", "weight": "buoyant_weight_g", "size": "size_at_acquisition", "at": "location",
         "where": "location", "price paid": "cost", "paid": "cost", "kind": "type", "color": "morph",
         "colour": "morph", "sold": "sold_date", "sweepers": "aggressive"}


def coral_path(cid):
    return os.path.join(CORALS, f"{cid}.md")


def ensure_coral(cid, name=""):
    path = coral_path(cid)
    if not os.path.exists(path):
        row = registry().get(cid)
        name = name or (row[1] if row else "")
        fm = {k: "" for k in FIELDS}
        fm.update(common_name=name, status="alive", children="[]", frag_count="0")
        if row:
            fm.update(location=row[3] if row[3] != "TBD" else "", parent=row[6] if row[6] != "-" else "")
        with open(path, "w") as f:
            f.write("---\nid: " + cid + "\n" + "".join(f"{k}: {v}\n" for k, v in fm.items()) + "---\n")
            f.write(f"# {cid} {name}\n\nTimeline (newest last): photos, notes, weights, frags, observations.\n\n")
    return path


def coral_note(cid, text, ts=None):
    ts = ts or time.strftime("%Y-%m-%d %H:%M")
    with open(ensure_coral(cid), "a") as f:
        f.write(f"- {ts} {text}\n")


def set_field(cid, field, value):
    key = ALIAS.get(field.lower().strip(), field.lower().strip().replace(" ", "_"))
    if key not in FIELDS:
        return None
    path = ensure_coral(cid)
    lines = open(path).read().split("\n")
    for i, l in enumerate(lines):
        if l.startswith(key + ":"):
            lines[i] = f"{key}: {value}"
            break
    open(path, "w").write("\n".join(lines))
    coral_note(cid, f"set {key} = {value}")
    return key


def get_field(cid, key):
    try:
        for l in open(coral_path(cid)):
            if l.startswith(key + ":"):
                return l.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


def frag(cid, n, location):
    """Frag a colony: n children registered with parent = cid; parent's children/frag history updated."""
    name = registry().get(cid, [cid, cid])[1]
    kids = []
    for i in range(n):
        kid = register(f"{name} frag", location, cid)
        set_field(kid, "parent", cid)
        kids.append(kid)
    old = get_field(cid, "children").strip("[] ")
    allk = [k for k in (old.split(", ") if old else []) if k] + kids
    set_field(cid, "children", "[" + ", ".join(allk) + "]")
    set_field(cid, "frag_count", str(int(get_field(cid, "frag_count") or 0) + n))
    set_field(cid, "last_fragged", time.strftime("%Y-%m-%d"))
    coral_note(cid, f"fragged into {n}: {', '.join(kids)}" + (f" @ {location}" if location else ""))
    return kids


def register(name, location, parent="-"):
    rows = registry()
    n = max([int(k[2:]) for k in rows] + [0]) + 1
    cid = f"C-{n:03d}"
    with open(os.path.join(CORALS, "registry.md"), "a") as f:
        f.write(f"| {cid} | {name} | TBD | {location or 'TBD'} | TBD | {time.strftime('%Y-%m-%d')} | {parent} | new |\n")
    coral_note(cid, f"registered: {name}" + (f" @ {location}" if location else ""))
    return cid


LIVE = "/mnt/reef-lab/livestock"                         # registry.md + L-###.md timelines (fish, inverts)
LFIELDS = ["common_name", "scientific_name", "kind", "count", "location", "source", "acquired", "cost", "status", "notes"]
LALIAS = {"name": "common_name", "common": "common_name", "species": "scientific_name", "latin": "scientific_name",
          "where": "location", "at": "location", "qty": "count", "how many": "count", "from": "source", "vendor": "source",
          "bought": "acquired", "paid": "cost", "type": "kind"}
LID = re.compile(r"^\s*l-?(\d{1,4})\b[\s:,-]*(.*)$", re.I | re.S)
LHEAD = ("# Livestock registry\n\nFish and invertebrates (corals are in corals/). One row per animal or group.\n"
         "Each has a timeline file next to this one: L-001.md, ...\n\n"
         "| id | name | species | kind | location | added | count | status |\n"
         "|----|------|---------|------|----------|-------|-------|--------|\n")


def live_id(text):
    """'L-3 eating well' -> ('L-003', 'eating well'); None if not a livestock reference."""
    m = LID.match(text or "")
    return (f"L-{int(m.group(1)):03d}", m.group(2).strip()) if m else None


def live_rows():
    rows = {}
    try:
        for l in open(os.path.join(LIVE, "registry.md")):
            c = [x.strip() for x in l.strip().strip("|").split("|")]
            if len(c) >= 8 and re.match(r"L-\d{3}$", c[0]):
                rows[c[0]] = c
    except OSError:
        pass
    return rows


def ensure_live(lid):
    path = os.path.join(LIVE, f"{lid}.md")
    if not os.path.exists(path):
        row = live_rows().get(lid)
        fm = {k: "" for k in LFIELDS}
        if row:
            fm.update(common_name=row[1], kind=row[3], location=row[4] if row[4] != "TBD" else "",
                      acquired=row[5], count=row[6], status="alive")
        with open(path, "w") as f:
            f.write("---\nid: " + lid + "\n" + "".join(f"{k}: {v}\n" for k, v in fm.items()) + "---\n")
            f.write(f"# {lid} {fm['common_name']}\n\nTimeline (newest last): photos, notes, observations.\n\n")
    return path


def live_note(lid, text, ts=None):
    ts = ts or time.strftime("%Y-%m-%d %H:%M")
    with open(ensure_live(lid), "a") as f:
        f.write(f"- {ts} {text}\n")


def live_set(lid, field, value):
    key = LALIAS.get(field.lower().strip(), field.lower().strip().replace(" ", "_"))
    if key not in LFIELDS:
        return None
    path = ensure_live(lid)
    lines = open(path).read().split("\n")
    for i, l in enumerate(lines):
        if l.startswith(key + ":"):
            lines[i] = f"{key}: {value}"
            break
    open(path, "w").write("\n".join(lines))
    reg = os.path.join(LIVE, "registry.md")
    col = {"common_name": 1, "scientific_name": 2, "kind": 3, "location": 4, "count": 6, "status": 7}.get(key)
    if col and os.path.exists(reg):
        out = []
        for l in open(reg).read().split("\n"):
            c = [x.strip() for x in l.strip().strip("|").split("|")]
            if len(c) >= 8 and c[0] == lid:
                c[col] = value
                l = "| " + " | ".join(c) + " |"
            out.append(l)
        open(reg, "w").write("\n".join(out))
    live_note(lid, f"set {key} = {value}")
    return key


def live_register(name, kind, location, count="1"):
    os.makedirs(LIVE, exist_ok=True)
    reg = os.path.join(LIVE, "registry.md")
    if not os.path.exists(reg):
        open(reg, "w").write(LHEAD)
    n = max([int(k[2:]) for k in live_rows()] + [0]) + 1
    lid = f"L-{n:03d}"
    with open(reg, "a") as f:
        f.write(f"| {lid} | {name} | TBD | {kind} | {location or 'TBD'} | {time.strftime('%Y-%m-%d')} | {count} | alive |\n")
    live_note(lid, f"added: {name} ({kind}" + (f", x{count}" if count != "1" else "") + ")" + (f" @ {location}" if location else ""))
    return lid


def subject_slug(caption):
    c = coral_id(caption or "")
    l = live_id(caption or "")
    if l:
        return l[0].lower()
    if c:
        return c[0].lower()
    s = re.sub(r"[^a-z0-9]+", "-", (caption or "tank").lower()).strip("-")
    return (s or "tank")[:40]


def save_photo(token, msg):
    """Download the largest size of a Telegram photo; return the saved path."""
    ph = max(msg["photo"], key=lambda x: x.get("file_size", 0))
    info = api(token, "getFile", {"file_id": ph["file_id"]})
    lt = time.localtime(msg["date"])
    d = os.path.join(PHOTOS, time.strftime("%Y/%m", lt))
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, time.strftime("%Y-%m-%d_%H%M", lt) + "_" + subject_slug(msg.get("caption")) + ".jpg")
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{token}/{info['file_path']}", timeout=120) as r, \
            open(path, "wb") as f:
        f.write(r.read())
    return path


ASK_LOCK = threading.Lock()
ASK_PROMPT = """Joe asked you a question on Telegram about his reef. Answer it like a knowledgeable reef friend:
direct, short (under 150 words), plain text, no markdown headers. He has kept reefs for 20+ years.
Context you may read (only what you need): tank profile /mnt/reef-lab/data/tank-profile.md; recipes, dosing
and jug forecast /mnt/reef-lab/data/recipes.md; maintenance schedule /mnt/reef-lab/data/maintenance.md and log
/mnt/reef-lab/data/maintenance-log.md; coral registry /mnt/reef-lab/corals/registry.md (+ C-###.md);
livestock registry /mnt/reef-lab/livestock/registry.md (+ L-###.md); latest data report
(newest file in /mnt/reef-lab/data/reports/, not backfill/); recent log entries under /mnt/reef-lab/log/;
palomino search tools for his reef library and past notes. Numbers you quote must come from those files.
Never recommend dosing or supplement changes; he decides those. If he sent photos, Read them. For coral IDs give
your best guess with confidence and what would confirm it; photos from a phone under reef lights shift colour.
If you don't know, say so."""


def ask(token, chat, question, photos):
    """Answer a question right away with Claude Code (Max plan), in a background thread."""
    def run():
        with ASK_LOCK:
            soft(token, "sendMessage", {"chat_id": chat, "text": "🤔 Looking into it…"})
            ids = sorted({f"C-{int(x):03d}" for x in re.findall(r"\bc-?(\d{1,4})\b", question, re.I)})
            prompt = ASK_PROMPT + "\nCoral registry: /mnt/reef-lab/corals/registry.md; each coral's history: "
            prompt += "/mnt/reef-lab/corals/C-###.md" + (f" (this question is about {', '.join(ids)}: read those)" if ids else "")
            prompt += f"\n\nQUESTION: {question}\n" + (
                "PHOTOS: " + ", ".join(photos) + "\n" if photos else "")
            envr = dict(os.environ, HOME="/root",
                        PATH="/root/.npm-global/bin:/usr/local/bin:/usr/bin:/bin")
            try:
                r = subprocess.run(
                    ["claude", "-p", prompt, "--add-dir", "/mnt/reef-lab", "--allowedTools", "Read", "Glob", "Grep",
                     "mcp__palomino__search_reef", "mcp__palomino__read_document",
                     "mcp__palomino__search_lab_notes", "mcp__palomino__read_lab_note"],
                    cwd="/mnt/reef-lab", env=envr, capture_output=True, text=True, timeout=300)
                answer = r.stdout.strip() or f"(no answer; {r.stderr.strip()[-300:]})"
            except Exception as e:
                answer = f"⚠️ Couldn't answer: {e}"
            for i in range(0, len(answer), 4000):
                soft(token, "sendMessage", {"chat_id": chat, "text": answer[i:i + 4000]})
            try:
                with open(PENDING, "a") as f:
                    f.write(f"[{time.strftime('%Y-%m-%d %H:%M')}] asked: {question}"
                            + (f" (photos: {', '.join(photos)})" if photos else "")
                            + f" | answered: {answer[:300].replace(chr(10), ' ')}\n")
            except OSError:
                pass
    threading.Thread(target=run, daemon=True).start()


CARE_PROMPT = """Write or refresh the care sheet for coral {cid} in Joe's registry. File: {path}
Read the file first (its profile has the names Joe or Claude set). Use the coral's scientific and common name.
Sources: your knowledge, Joe's reef library (palomino search_reef), and WebSearch for current taxonomy and care
(e.g. renamed genera). Put the section right after the '# {cid} ...' title line and before 'Timeline', replacing
any existing '## Care sheet' section. Edit only that section; never touch the profile or the timeline.
Format exactly:

## Care sheet (general guidance, Claude {date}; Joe's own experience overrides)
- **ID:** scientific name (current), former names, common/trade names, family; ID confidence if not confirmed
- **Type / difficulty / growth:** SPS|LPS|soft..., easy|moderate|hard, slow|medium|fast
- **Light:** PAR range (and what too much/too little looks like)
- **Flow:** low|moderate|high, direct or indirect
- **Placement:** where in the tank, spacing
- **Aggression:** sweeper tentacles / stinging reach, chemical warfare, safe distance
- **Feeding / nutrients:** feeds or not, what, how often; nutrient preference (NO3/PO4 lean or richer)
- **Parameters:** alk/Ca/Mg/temp sensitivity, stability notes
- **Pests and problems:** pests specific to this coral and what they look like; common diseases
  (e.g. brown jelly, RTN/STN, recession); early warning signs
- **Fragging:** method and tips, recovery time
- **Notes for Joe's tank:** one or two lines tying it to his tank profile (LPS-dominated, alk ~7, daily water change)
- **Sources:** short list (library paths / web pages)

Keep it to about 30 lines. Say plainly when sources disagree or when an item is uncertain.
Final response: one line summary for Telegram."""


def caresheet(token, chat, cid):
    def run():
        with ASK_LOCK:
            path = ensure_coral(cid)
            soft(token, "sendMessage", {"chat_id": chat, "text": f"📖 Writing the care sheet for {cid}…"})
            envr = dict(os.environ, HOME="/root", PATH="/root/.npm-global/bin:/usr/local/bin:/usr/bin:/bin")
            try:
                r = subprocess.run(
                    ["claude", "-p", CARE_PROMPT.format(cid=cid, path=path, date=time.strftime("%Y-%m-%d")),
                     "--add-dir", "/mnt/reef-lab", "--allowedTools", "Read", "Edit", "Glob", "WebSearch", "WebFetch",
                     "mcp__palomino__search_reef", "mcp__palomino__read_document"],
                    cwd="/mnt/reef-lab", env=envr, capture_output=True, text=True, timeout=600)
                out = r.stdout.strip() or f"(no output; {r.stderr.strip()[-300:]})"
            except Exception as e:
                out = f"⚠️ Care sheet failed: {e}"
            ok = "## Care sheet" in open(path).read()
            soft(token, "sendMessage", {"chat_id": chat, "text": (f"📖 {cid} care sheet ready. " if ok else "⚠️ ") + out[:3500]})
    threading.Thread(target=run, daemon=True).start()


MAINT = "/mnt/reef-lab/data/maintenance.md"
MAINT_LOG = "/mnt/reef-lab/data/maintenance-log.md"
MAINT_VERB = re.compile(r"\b(clean(ed)?|chang(e|ed)|replac(e|ed)|swap(ped)?|new|calibrat(e|ed)|check(ed)?|servic(e|ed)|"
                        r"install(ed)?|refill(ed)?|measur(e|ed)|did|done|flush(ed)?|rins(e|ed)|scrub(bed)?)\b", re.I)


RECIPES = "/mnt/reef-lab/data/recipes.md"
MIX_VERB = re.compile(r"\b(mix(ed)?|made|new batch|refill(ed)?|topped up)\b", re.I)


def jug_rows():
    rows = []
    try:
        for l in open(RECIPES):
            c = [x.strip() for x in l.strip().strip("|").split("|")]
            if len(c) >= 7 and re.match(r"J\d+$", c[0]):
                rows.append(c)
    except OSError:
        pass
    return rows


def jug_days_left(c, today=None):
    import datetime as dt
    today = today or dt.date.today()
    try:
        jug, per = float(c[3]) * 1000, float(c[4])
        last = dt.date.fromisoformat(c[5][:10])
    except ValueError:
        return None
    return round((jug - per * (today - last).days) / per, 1) if per else None


def mix_match(text):
    if not MIX_VERB.search(text):
        return None
    low, best = text.lower(), None
    for r in jug_rows():
        for a in [x.strip().lower() for x in r[6].split(",") if x.strip()]:
            if re.search(r"\b" + re.escape(a) + r"\b", low) and (not best or len(a) > best[1]):
                best = (r, len(a))
    return best[0] if best else None


def mix_done(row, ts):
    lines = open(RECIPES).read().split("\n")
    for i, l in enumerate(lines):
        c = [x.strip() for x in l.strip().strip("|").split("|")]
        if c and c[0] == row[0]:
            c[5] = ts[:10]
            lines[i] = "| " + " | ".join(c) + " |"
    open(RECIPES, "w").write("\n".join(lines))
    new = not os.path.exists(MAINT_LOG)
    with open(MAINT_LOG, "a") as f:
        if new:
            f.write("# Maintenance log (newest last)\n\n")
        f.write(f"- {ts} {row[0]} mixed: {row[1]}\n")
    return jug_days_left(row[:5] + [ts[:10]] + row[6:])


def maint_rows():
    rows = []
    try:
        for l in open(MAINT):
            c = [x.strip() for x in l.strip().strip("|").split("|")]
            if len(c) >= 6 and re.match(r"M\d+$", c[0]):
                rows.append(c)
    except OSError:
        pass
    return rows


def maint_due(row, today=None):
    import datetime as dt
    today = today or dt.date.today()
    every = int(re.sub(r"\D", "", row[2]) or 0)
    if not every:
        return None, None
    if row[3] in ("", "-"):
        return "never logged", None
    nxt = dt.date.fromisoformat(row[3][:10]) + dt.timedelta(days=every)
    return (nxt - today).days, nxt


def maint_match(text):
    if not MAINT_VERB.search(text):
        return None
    low, best = text.lower(), None
    for r in maint_rows():
        for a in [x.strip().lower() for x in r[4].split(",") if x.strip()]:
            if re.search(r"\b" + re.escape(a) + r"(s|es)?\b", low) and (not best or len(a) > best[1]):
                best = (r, len(a))
    return best[0] if best else None


def maint_done(row, text, ts):
    today = ts[:10]
    lines = open(MAINT).read().split("\n")
    for i, l in enumerate(lines):
        c = [x.strip() for x in l.strip().strip("|").split("|")]
        if c and c[0] == row[0]:
            c[3] = today
            lines[i] = "| " + " | ".join(c) + " |"
    open(MAINT, "w").write("\n".join(lines))
    new = not os.path.exists(MAINT_LOG)
    with open(MAINT_LOG, "a") as f:
        if new:
            f.write("# Maintenance log (newest last)\n\n")
        f.write(f"- {ts} {row[0]} {row[1]}: {text}\n")
    row = row[:3] + [today] + row[4:]
    return maint_due(row)


def maint_status():
    out = []
    for r in maint_rows():
        d, nxt = maint_due(r)
        if d is None:
            continue
        if d == "never logged":
            out.append((9998, f"{r[1]}: never logged"))
        elif d < 0:
            out.append((d, f"{r[1]}: OVERDUE {-d} days"))
        elif d <= 7:
            out.append((d, f"{r[1]}: due in {d} days"))
    return [s for _, s in sorted(out)]


def queue_hand(ts, pairs):
    os.makedirs(os.path.dirname(INBOX), exist_ok=True)
    with open(INBOX, "a") as f:
        for p, v in pairs:
            f.write(json.dumps({"ts": ts, "param": p, "value": v}) + "\n")


def collect():
    token, chat = env()
    os.makedirs(f"{BASE}/state", exist_ok=True)
    offset = int(open(OFFSET).read().strip()) if os.path.exists(OFFSET) else 0
    updates = api(token, "getUpdates", {"offset": offset, "timeout": 0,
                                        "allowed_updates": json.dumps(["message", "edited_message", "callback_query"])})
    lines = []
    try:
        handle(token, chat, updates, lines)
    finally:
        offset = max([offset] + [u["update_id"] + 1 for u in updates])
        if lines:
            with open(PENDING, "a") as f:
                f.write("\n".join(lines) + "\n")
        with open(OFFSET, "w") as f:
            f.write(str(offset))


RECENT_PHOTOS, PENDING_ASKS = [], []


def handle(token, chat, updates, lines):
    _handle(token, chat, updates, lines)
    # questions sent with photos: collect the whole album (same media group, or photos from the last 2 min)
    while PENDING_ASKS:
        t0, grp, q = PENDING_ASKS.pop(0)
        photos = [pth for tt, g, pth in RECENT_PHOTOS if (grp and g == grp) or (not grp and abs(tt - t0) < 120)]
        ask(token, chat, q, photos)
    cutoff = time.time() - 600
    RECENT_PHOTOS[:] = [x for x in RECENT_PHOTOS if x[0] > cutoff]


def _handle(token, chat, updates, lines):
    for u in updates:
        cb = u.get("callback_query")
        if cb:
            if str(cb["from"]["id"]) != str(chat):
                continue
            data = cb.get("data", "")
            soft(token, "answerCallbackQuery", {"callback_query_id": cb["id"], "text": "Noted, filed tomorrow"})
            m = re.match(r"fb:(\d{4}-\d{2}-\d{2}):(up|down)$", data)
            if not m:
                continue
            ts = time.strftime("%Y-%m-%d %H:%M")
            lines.append(f"[{ts}] {'👍 agree' if m.group(2) == 'up' else '👎 disagree'} (button on the {m.group(1)} digest)")
            msg = cb.get("message")
            if msg:
                soft(token, "editMessageReplyMarkup", {
                    "chat_id": msg["chat"]["id"], "message_id": msg["message_id"],
                    "reply_markup": json.dumps({"inline_keyboard": [[{
                        "text": "👍 noted" if m.group(2) == "up" else "👎 noted", "callback_data": "noop"}]]})})
            continue
        m = u.get("message") or u.get("edited_message")
        if m and str(m["chat"]["id"]) == str(chat) and m.get("photo"):
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(m["date"]))
            cap = (m.get("caption") or "").strip()
            try:
                path = save_photo(token, m)
                lines.append(f"[{ts}] photo: {path}" + (f" — {cap}" if cap else ""))
                c = coral_id(cap)
                if c:
                    coral_note(c[0], f"photo: {path}" + (f" — {c[1]}" if c[1] else ""), ts)
                lv = live_id(cap)
                if lv:
                    live_note(lv[0], f"photo: {path}" + (f" — {lv[1]}" if lv[1] else ""), ts)
                RECENT_PHOTOS.append((time.time(), m.get("media_group_id"), path))
                if "?" in cap:
                    PENDING_ASKS.append((time.time(), m.get("media_group_id"), cap))
                soft(token, "sendMessage", {"chat_id": chat, "text": f"📷 Photo saved ({subject_slug(cap)}). "
                     "Tomorrow's log compares it with the last photo of the same subject."
                     + ("" if cap else " Tip: add a caption like 'acro left' so the same spot gets compared each time.")})
            except Exception as ex:
                soft(token, "sendMessage", {"chat_id": chat, "text": f"⚠️ Could not save the photo: {ex}"})
            continue
        if not m or str(m["chat"]["id"]) != str(chat) or not m.get("text"):
            continue
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(m["date"]))
        text = m["text"].strip()
        if text.startswith("/"):
            continue
        low = text.lower()
        if low in ("jugs", "dosing", "reservoirs"):
            out = []
            for c in jug_rows():
                left = jug_days_left(c)
                out.append(f"{c[1]}: " + (f"~{left:g} days left" if left is not None else "no forecast (jug size or mix date missing)"))
            soft(token, "sendMessage", {"chat_id": chat, "text": "🧪 Jugs:\n" + "\n".join(out)})
            continue
        if low in ("maintenance", "maint", "due", "what's due", "whats due"):
            st = maint_status()
            soft(token, "sendMessage", {"chat_id": chat, "text": "🔧 Maintenance:\n" + ("\n".join(st) if st else "nothing due in the next 7 days")})
            continue
        if low in ("corals", "coral list", "list corals"):
            rows = registry()
            soft(token, "sendMessage", {"chat_id": chat, "text": "🪸 Corals:\n" + "\n".join(
                f"{c[0]}  {c[1]}  ({c[3]})" for c in rows.values()) if rows else "No corals registered yet."})
            continue
        mnew = re.match(r"^(?:new|add) coral\s+(.+?)(?:\s+@\s*(.+))?$", text, re.I)
        if mnew:
            cid = register(mnew.group(1).strip(), (mnew.group(2) or "").strip())
            lines.append(f"[{ts}] new coral {cid}: {mnew.group(1).strip()}")
            soft(token, "sendMessage", {"chat_id": chat, "text": f"🪸 Registered {cid}: {mnew.group(1).strip()}. "
                 f"Caption photos '{cid}' and send notes like '{cid} polyps out' to build its history."})
            continue
        mfrag = re.match(r"^frag\s+c-?(\d{1,4})\s*(?:x\s*(\d+))?(?:\s+@\s*(.+))?$", text, re.I)
        if mfrag:
            cid = f"C-{int(mfrag.group(1)):03d}"
            kids = frag(cid, int(mfrag.group(2) or 1), (mfrag.group(3) or "").strip())
            lines.append(f"[{ts}] fragged {cid} into {', '.join(kids)}")
            soft(token, "sendMessage", {"chat_id": chat, "text": f"✂️ {cid} fragged: {', '.join(kids)} registered with parent {cid}."})
            continue
        if low in ("livestock", "fish", "inverts", "animals", "list fish"):
            rows = live_rows()
            soft(token, "sendMessage", {"chat_id": chat, "text": "🐠 Livestock:\n" + "\n".join(
                f"{r[0]}  {r[1]}  ({r[3]}, x{r[6]}, {r[7]})" for r in rows.values()) if rows else "No livestock registered yet."})
            continue
        mnl = re.match(r"^(?:new|add)\s+(fish|invert|inverts|invertebrate|snails?|crabs?|shrimps?|urchins?|starfish|clams?|cucumbers?)\s+(.+?)"
                       r"(?:\s+x\s*(\d+))?(?:\s+@\s*(.+?))?(?:\s+x\s*(\d+))?$", text, re.I)
        if mnl:
            word = mnl.group(1).lower()
            kind = "fish" if word == "fish" else "invert"
            name = mnl.group(2).strip() + ("" if word in ("fish", "invert", "inverts", "invertebrate") else f" ({word})")
            count = mnl.group(3) or mnl.group(5) or "1"
            lid = live_register(name, kind, (mnl.group(4) or "").strip(), count)
            lines.append(f"[{ts}] new {kind} {lid}: {name} x{count}")
            soft(token, "sendMessage", {"chat_id": chat, "text": f"🐠 Registered {lid}: {name} ({kind}, x{count}). "
                 f"Send notes like '{lid} eating well', photos captioned '{lid}', or '{lid} set species …'."})
            continue
        lv = live_id(text)
        if lv and lv[1] and "?" not in text:
            mls = re.match(r"^set\s+([a-z_ ]+?)\s*[:=]?\s+(.+)$", lv[1], re.I)
            if mls:
                key = live_set(lv[0], mls.group(1), mls.group(2).strip())
                soft(token, "sendMessage", {"chat_id": chat, "text": f"🐠 {lv[0]}: {key} updated." if key else
                     "Unknown field. Fields: " + ", ".join(LFIELDS)})
                lines.append(f"[{ts}] {lv[0]} {mls.group(1)} = {mls.group(2).strip()}")
            elif re.match(r"^(lost|died|dead|rip|gone|passed)\b", lv[1], re.I):
                live_set(lv[0], "status", "lost")
                live_note(lv[0], f"lost: {lv[1]}", ts)
                lines.append(f"[{ts}] {lv[0]} lost: {lv[1]}")
                soft(token, "sendMessage", {"chat_id": chat, "text": f"🐠 {lv[0]} marked lost. Sorry about that."})
            else:
                live_note(lv[0], f"note: {lv[1]}", ts)
                lines.append(f"[{ts}] {lv[0]}: {lv[1]}")
                soft(token, "sendMessage", {"chat_id": chat, "text": f"🐠 Added to {lv[0]}'s history."})
            continue
        c = coral_id(text)
        mset = re.match(r"^set\s+([a-z_ ]+?)\s*[:=]?\s+(.+)$", c[1], re.I) if c and c[1] else None
        mw = re.match(r"^weight\s*[:=]?\s*([\d.]+)\s*g?$", c[1], re.I) if c and c[1] else None
        mp = re.match(r"^par\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:par|umol|µmol)?\s*$", c[1], re.I) if c and c[1] else None
        if mp:
            set_field(c[0], "par", mp.group(1))
            lines.append(f"[{ts}] {c[0]} PAR {mp.group(1)}")
            soft(token, "sendMessage", {"chat_id": chat, "text": f"🔆 {c[0]}: PAR {mp.group(1)} logged. It shows on the coral's PAR history."})
            continue
        if c and re.match(r"^care\s*sheet$|^care$|^info$", c[1] or "", re.I):
            caresheet(token, chat, c[0])
            lines.append(f"[{ts}] {c[0]}: care sheet requested")
            continue
        if mset or mw:
            key = set_field(c[0], *(mset.groups() if mset else ("weight", mw.group(1))))
            if key:
                lines.append(f"[{ts}] {c[0]} {key} = {mset.group(2) if mset else mw.group(1)}")
                soft(token, "sendMessage", {"chat_id": chat, "text": f"🪸 {c[0]}: {key} updated."})
                if key in ("scientific_name", "common_name"):
                    caresheet(token, chat, c[0])
            else:
                soft(token, "sendMessage", {"chat_id": chat, "text": "Unknown field. Fields: " + ", ".join(FIELDS)})
            continue
        if c and c[1] and "?" not in text:
            coral_note(c[0], f"note: {c[1]}", ts)
            lines.append(f"[{ts}] {c[0]}: {c[1]}")
            soft(token, "sendMessage", {"chat_id": chat, "text": f"🪸 Added to {c[0]}'s history."})
            continue
        force = text.endswith("!")
        pairs = hand_test(text.rstrip("!"))
        if pairs and not force:
            bad = [(p, v, bands()[p]) for p, v in pairs if p in bands()
                   and not (bands()[p][0] * 0.5 <= v <= bands()[p][1] * 2)]
            if bad:
                soft(token, "sendMessage", {"chat_id": chat, "text": "⚠️ Not logged: " + ", ".join(
                    f"{p} {v:g} looks off (target {lo:g}-{hi:g})" for p, v, (lo, hi) in bad)
                    + ". Typo? Send it again, or add ! at the end to log it anyway."})
                lines.append(f"[{ts}] (rejected as a likely typo: {text})")
                pairs = None
                continue
        if pairs:
            queue_hand(m["date"], pairs)
            done = ", ".join(f"{p} {v:g}" for p, v in pairs)
            lines.append(f"[{ts}] hand test logged: {done}")
            soft(token, "sendMessage", {"chat_id": chat, "text": f"✅ Hand test logged: {done}. "
                                       "It shows up in the report within 15 minutes."})
        elif "?" in text:
            recent = [pth for tt, g, pth in RECENT_PHOTOS if time.time() - tt < 600]
            lines.append(f"[{ts}] {text}")
            ask(token, chat, text, recent)
        else:
            rgal = rodi_swap(text)
            if rgal:
                os.makedirs(os.path.dirname(INBOX), exist_ok=True)
                with open(INBOX, "a") as f:
                    f.write(json.dumps({"ts": m["date"], "kind": "rodi", "gal": rgal}) + "\n")
                    wgal = water_change(text)
                    if wgal:   # "swapped 10 gal for rodi": also a water-change window, temp left out
                        f.write(json.dumps({"ts": m["date"], "kind": "wc", "gal": wgal}) + "\n")
                sal = latest_salinity()
                frac = rgal * 3.785 / SYSTEM_L
                est = (f" That is about {frac * 100:.1f}% of the water, so salinity should drop roughly "
                       f"{(sal or 35) * frac:.2f} ppt" + (f" from {sal:.2f}." if sal else ".")) if frac < 0.5 else ""
                soft(token, "sendMessage", {"chat_id": chat, "text": f"🚰 Logged: {rgal:g} gal RO/DI.{est} "
                     "It goes into the salinity drift tracking in the daily report."})
                lines.append(f"[{ts}] {text}  [RO/DI logged: {rgal:g} gal]")
                continue
            jrow = mix_match(text)
            if jrow:
                left = mix_done(jrow, ts)
                soft(token, "sendMessage", {"chat_id": chat, "text": f"🧪 Logged: mixed {jrow[1]}."
                     + (f" At {jrow[4]} ml/day it lasts about {left:g} days." if left else
                        " Tell me the jug size and I'll forecast when it runs out.")})
                lines.append(f"[{ts}] {text}  [mixed: {jrow[0]} {jrow[1]}]")
                continue
            mrow = maint_match(text)
            if mrow:
                days, nxt = maint_done(mrow, text, ts)
                soft(token, "sendMessage", {"chat_id": chat, "text": f"🔧 Logged: {mrow[1]}."
                     + (f" Next due {nxt:%b %d}." if nxt else "")})
                lines.append(f"[{ts}] {text}  [maintenance logged: {mrow[0]} {mrow[1]}]")
                continue
            gal = water_change(text)
            if gal:
                os.makedirs(os.path.dirname(INBOX), exist_ok=True)
                with open(INBOX, "a") as f:
                    f.write(json.dumps({"ts": m["date"], "kind": "wc", "gal": gal}) + "\n")
                soft(token, "sendMessage", {"chat_id": chat, "text":
                     f"💧 Manual water change logged: {gal:g} gal at {ts[11:]}. "
                     "Temperature during it is left out of the stats, and it goes in the log as an event."})
            lines.append(f"[{ts}] {text}" + (f"  [manual water change logged: {gal:g} gal]" if gal else ""))


OUTBOX = "/mnt/reef-lab/data/outbox/alerts.jsonl"     # reefcore reef-alerts.py queues alerts here; we send them


def flush_outbox(token, chat):
    """Send alerts queued by reefcore (it has no Telegram token). Rename first so nothing is sent twice."""
    if not os.path.exists(OUTBOX) or os.path.getsize(OUTBOX) == 0:
        return
    work = OUTBOX + f".sending-{int(time.time())}"
    try:
        os.rename(OUTBOX, work)
    except OSError:
        return
    for line in open(work):
        try:
            text = json.loads(line).get("text", "")
        except ValueError:
            continue
        if text:
            soft(token, "sendMessage", {"chat_id": chat, "text": text})
    os.makedirs(os.path.dirname(OUTBOX) + "/sent", exist_ok=True)
    os.rename(work, os.path.dirname(OUTBOX) + "/sent/" + os.path.basename(work))


def listen():
    token, chat = env()
    while True:
        try:
            open("/mnt/reef-lab/data/.bot-alive", "w").write(str(int(time.time())))
        except OSError:
            pass
        try:
            flush_outbox(token, chat)
        except Exception:
            pass
        offset = int(open(OFFSET).read().strip()) if os.path.exists(OFFSET) else 0
        try:
            updates = api(token, "getUpdates", {"offset": offset, "timeout": 50, "allowed_updates":
                          json.dumps(["message", "edited_message", "callback_query"])})
        except Exception as e:
            print(f"getUpdates failed: {e}", file=sys.stderr)
            time.sleep(30)
            continue
        if not updates:
            continue
        lines = []
        try:
            handle(token, chat, updates, lines)
        except Exception as e:
            print(f"handle failed: {e}", file=sys.stderr)
        finally:
            if lines:
                with open(PENDING, "a") as f:
                    f.write("\n".join(lines) + "\n")
            with open(OFFSET, "w") as f:
                f.write(str(max(u["update_id"] for u in updates) + 1))


def listener_running():
    import subprocess
    return subprocess.run(["systemctl", "is-active", "--quiet", "reef-log-bot"]).returncode == 0


def take():
    if not listener_running():   # the listener owns getUpdates when it runs (Telegram allows one reader)
        collect()
    if os.path.exists(PENDING):
        sys.stdout.write(open(PENDING).read())
        os.remove(PENDING)


def send(path, buttons=None):
    token, chat = env()
    text = open(path).read().strip() or "(empty reef log digest)"
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
    for i, c in enumerate(chunks):
        params = {"chat_id": chat, "text": c}
        if buttons and i == len(chunks) - 1:
            params["reply_markup"] = json.dumps({"inline_keyboard": [[
                {"text": "👍", "callback_data": f"fb:{buttons}:up"},
                {"text": "👎", "callback_data": f"fb:{buttons}:down"}]]})
        api(token, "sendMessage", params)


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else ""
    if cmd == "listen":
        listen()
    elif cmd == "collect":
        collect()
    elif cmd == "take":
        take()
    elif cmd == "send" and len(a) >= 2:
        send(a[1], a[3] if len(a) >= 4 and a[2] == "--buttons" else None)
    else:
        raise SystemExit(__doc__)
