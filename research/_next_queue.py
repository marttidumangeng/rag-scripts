import json
from pathlib import Path

done = json.loads(Path("state/content_queue_done.json").read_text(encoding="utf-8"))
rep = json.loads(Path("staging/reports/content-queue-triage.json").read_text(encoding="utf-8"))
done_set = set(done.get("companies") or [])
print("done", len(done_set), "192 done?", 192 in done_set)
print("top remaining:")
n = 0
for c in rep.get("top") or []:
    cid = c.get("company_id")
    if cid in done_set:
        continue
    n += 1
    print(
        f"  #{n} score={c.get('rank_score')} n={c.get('incomplete_count')} "
        f"id={cid} {(c.get('company_name') or '')[:48]} site={c.get('website') or '-'}"
    )
    if n >= 5:
        break
