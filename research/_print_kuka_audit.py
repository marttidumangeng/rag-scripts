import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = json.loads(open("staging/reports/kuka-1396-audit.json", encoding="utf-8").read())
print("dead", len(d["public_dead_heroes"]))
notes = {}
for e in d["public_dead_heroes"]:
    notes[e["note"]] = notes.get(e["note"], 0) + 1
    print(f"{e['id']} http={e['http']} note={e['note'][:20]:20s} {e['name'][:42]:42s} {(e['hero'] or '')[-55:]}")
print("dead by note", notes)
print("ok count", sum(1 for x in d["public_robots"] if x["md5"]))
print("pending non-hub gaps:")
for p in d["pending_robots"]:
    g = [x for x in p["gaps"] if x != "series_hub"]
    if g:
        print(p["id"], p["name"][:42], g)
