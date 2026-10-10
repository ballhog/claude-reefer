"""Register a coral from an order email: order_import.py NAME SCI TYPE MORPH SOURCE ACQUIRED COST NOTE
Registers, fills the profile, logs the purchase, writes the care sheet (quietly)."""
import sys, threading
sys.path.insert(0, "/root/reef-log")
import tg
from pathlib import Path
name, sci, typ, morph, source, acq, cost, note = sys.argv[1:9]
cid = tg.register(name, "")
print(cid, flush=True)
for k, v in (("scientific_name", sci), ("type", typ), ("morph", morph), ("source", source), ("acquired", acq), ("cost", cost)):
    if v:
        tg.set_field(cid, k, v)
r = Path("/mnt/reef-lab/corals/registry.md")
r.write_text(r.read_text().replace(f"| {cid} | {name} | TBD | TBD | TBD |",
                                   f"| {cid} | {name} | {sci.split(' (')[0] or 'TBD'} | TBD | {source.split(',')[0] or 'TBD'} |"))
tg.coral_note(cid, "purchase: " + note)
tg.soft = lambda *a, **k: None
tg.caresheet(None, None, cid)
for th in threading.enumerate():
    if th is not threading.current_thread():
        th.join()
print("done", flush=True)
