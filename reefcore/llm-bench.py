#!/usr/bin/env python3
"""Local LLM bench (reefcore CT 101). Test only: never feeds the reef log, Telegram or feedback.

  llm-bench.py [REPORT] [--model NAME]

Reads the day's reefchem report, asks the local model on pizer for a digest, and saves the
result to /root/reef-lab/bench/<date>-<model>.md (folder has .noindex). nz-home shows it.
"""
import json, re, sys, time, urllib.request
from datetime import date
from pathlib import Path

OLLAMA = "http://10.0.0.117:11434/api/chat"
MODEL = "qwen3:4b-instruct-2507-q4_K_M"   # the one already loaded; others evict it
BENCH = Path("/root/reef-lab/bench")
REPORTS = Path("/root/reef-lab/data/reports")

PROMPT = """The text below is today's reef data summary. Every number was computed by a script:
quote numbers exactly and never calculate or invent any. Write a digest of at most 10 lines:
first every item marked ALERT, STALLED?, LOW, HIGH or CHECK CALIBRATION; then one line on anything
else notable; then up to 2 possible explanations, each marked as a hypothesis.
Never recommend any dosing or supplement change.
Facts: the Trident tests alk 3 times a day and calc + mag once a day, so hours without a new
calc/mag result are normal. The Trident alk can read about 0.5 dKH low; its trend is reliable.
Reply with the digest text only.

"""


PARKED = Path("/root/reef-lab/bench/.parked")   # local LLM parked 2026-10-09; delete file to re-enable


def main():
    if PARKED.exists() and "--force" not in sys.argv:
        return
    if "--force" in sys.argv:
        sys.argv.remove("--force")
    args = sys.argv[1:]
    model = MODEL
    if "--model" in args:
        i = args.index("--model"); model = args[i + 1]; del args[i:i + 2]
    report = Path(args[0]) if args else REPORTS / f"{date.today()}.txt"
    text = report.read_text()
    m = re.search(r"\d{4}-\d{2}-\d{2}", text.splitlines()[0])
    day = m.group(0) if m else str(date.today())

    body = json.dumps({"model": model, "stream": False, "keep_alive": -1,
                       "options": {"temperature": 0.7, "num_ctx": 8192},
                       "messages": [{"role": "user", "content": PROMPT + text}]}).encode()
    t0 = time.time()
    req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=1800) as r:
            out = json.load(r)
        reply = out["message"]["content"].strip()
        reply = re.sub(r"<think>.*?</think>\s*", "", reply, flags=re.S)
        n, dur = out.get("eval_count", 0), out.get("eval_duration", 0) / 1e9
        stats = f"{time.time() - t0:.0f} s, {n} tokens, {n / dur:.1f} tok/s" if dur else f"{time.time() - t0:.0f} s"
    except Exception as e:
        reply, stats = f"(run failed: {e})", f"{time.time() - t0:.0f} s"

    BENCH.mkdir(exist_ok=True)
    (BENCH / ".noindex").touch()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", model)
    out = BENCH / f"{day}-{safe}.md"
    out.write_text(f"date: {day}\nmodel: {model}\nrun: {stats}\n---\n{reply}\n")
    print(out)


if __name__ == "__main__":
    main()
