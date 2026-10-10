#!/usr/bin/env python3
"""Claude Reefer voice endpoint (mccrae). For the iPhone Action-button Shortcut: Dictate -> POST -> Speak.

POST /voice  {"text": "..."}   header Authorization: Bearer <token in /root/reef-log/voice.token>
  - questions ("?" or starting with what/when/how/why/is/does/should/can...) -> Claude answers, spoken style
  - everything else is handled exactly like a Telegram message: hand tests, water changes, coral commands, notes
Returns plain text to speak. Same files, same log, same Max plan as the Telegram bot. LAN + Tailscale only.
"""
import hmac, importlib.util, json, os, re, subprocess, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8790
TOKEN = open("/root/reef-log/voice.token").read().strip()
spec = importlib.util.spec_from_file_location("tg", "/root/reef-log/tg.py")
tg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tg)
TG_TOKEN, CHAT = tg.env()
Q_START = re.compile(r"^(what|when|where|why|how|who|which|is|are|was|were|do|does|did|should|can|could|will|would|tell me|give me)\b", re.I)
VOICE_STYLE = ("\nThis question was SPOKEN into an iPhone and your answer will be READ ALOUD. Answer in at most 3 short "
               "sentences (under 60 words), plain words, no lists, no markdown, no emoji, no file paths, numbers rounded "
               "sensibly (say 'about 6.9' not '6.88'). If you need more, give the short answer and offer details in Telegram.")


def speakable(s):
    s = re.sub(r"[\U0001F300-\U0001FAFF☀-➿️]", "", s)          # emoji
    s = re.sub(r"[*_`#>]", "", s)                                             # markdown marks
    return re.sub(r"\s+", " ", s).strip()


def answer(question):
    ids = sorted({f"C-{int(x):03d}" for x in re.findall(r"\bc-?(\d{1,4})\b", question, re.I)})
    prompt = (tg.ASK_PROMPT + VOICE_STYLE + "\nCoral registry: /mnt/reef-lab/corals/registry.md; each coral's history: "
              "/mnt/reef-lab/corals/C-###.md" + (f" (this question is about {', '.join(ids)}: read those)" if ids else "")
              + f"\n\nQUESTION: {question}\n")
    envr = dict(os.environ, HOME="/root", PATH="/root/.npm-global/bin:/usr/local/bin:/usr/bin:/bin")
    try:
        r = subprocess.run(["claude", "-p", prompt, "--add-dir", "/mnt/reef-lab", "--allowedTools", "Read", "Glob", "Grep",
                            "mcp__palomino__search_reef", "mcp__palomino__search_lab_notes"],
                           cwd="/mnt/reef-lab", env=envr, capture_output=True, text=True, timeout=110)
        out = r.stdout.strip() or "Sorry, I couldn't get an answer just now."
    except subprocess.TimeoutExpired:
        out = "That's taking too long. Ask me in Telegram and I'll answer there."
    with open(tg.PENDING, "a") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M')}] asked by voice: {question} | answered: {out[:300].replace(chr(10), ' ')}\n")
    return out


def log_like_telegram(text):
    said = []
    orig = tg.soft
    tg.soft = lambda token, method, params: said.append(params.get("text", "")) if method == "sendMessage" else None
    lines = []
    try:
        upd = [{"update_id": 0, "message": {"chat": {"id": int(CHAT)}, "date": int(time.time()), "text": text}}]
        tg._handle(TG_TOKEN, CHAT, upd, lines)
    finally:
        tg.soft = orig
    if lines:
        with open(tg.PENDING, "a") as f:
            f.write("\n".join(l.replace("] ", "] (voice) ", 1) for l in lines) + "\n")
    return said[0] if said else "Noted. It goes in tomorrow's log."


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, text):
        b = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self.reply(200, "Claude Reefer voice endpoint is up.") if self.path == "/health" else self.reply(404, "not found")

    def do_POST(self):
        if self.path != "/voice":
            return self.reply(404, "not found")
        if not hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {TOKEN}"):
            return self.reply(401, "Wrong voice token.")
        raw = self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 20000)).decode(errors="ignore")
        try:
            text = json.loads(raw).get("text", "") if raw.strip().startswith("{") else raw
        except ValueError:
            text = raw
        text = text.strip()
        if not text:
            return self.reply(200, "I didn't catch anything.")
        try:
            q = "?" in text or Q_START.match(text)
            short_topic = (len(text.split()) <= 3 and not tg.hand_test(text) and not tg.water_change(text)
                           and not (tg.coral_id(text) and tg.coral_id(text)[1]) and not re.match(r"^(new|add) coral|^frag\b|^corals$", text, re.I))
            if q:
                out = answer(text)
            elif short_topic:                     # "alkalinity", "salinity", "C-001" -> quick status
                out = answer(f"Quick status on: {text}")
            else:
                out = log_like_telegram(text)
        except Exception as e:
            out = f"Something went wrong: {e}"
        self.reply(200, speakable(out))


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
