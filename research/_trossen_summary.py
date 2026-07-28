import json
from pathlib import Path

r = json.loads(Path("staging/reports/trossen-heroes/scrape-report.json").read_text(encoding="utf-8"))
for e in r["robots"]:
    yt = e.get("youtube", {})
    acc = yt.get("accepted") or []
    rej = yt.get("rejected") or []
    print("=" * 60)
    print(e["id"], e["name"])
    print("URL:", e["url"])
    print("JS shell:", e.get("js_shell"), "HTTP:", e.get("http_status"))
    print("Hero:", (e.get("hero") or "")[:90])
    print("Features:", len(e.get("features") or []))
    for f in (e.get("features") or [])[:3]:
        print("  -", f[:100])
    print("Specs:", e.get("specs"))
    print("YT accepted:", len(acc))
    for v in acc:
        print("  +", (v.get("title") or "")[:70], "|", v.get("reason", ""))
    print("YT rejected sample:", len(rej))
    for v in rej[:3]:
        print("  -", (v.get("title") or "")[:60], "|", v.get("reason", ""))
    print("CRM:", e.get("crm_recommendations"))
    print("Notes:", e.get("notes"))
