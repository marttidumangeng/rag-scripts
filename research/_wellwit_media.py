"""Localize Wellwit heroes to CDN — the data pass set the scalar `image` but never
created a photo relation, so copy-media had nothing to localize. Use the proven
pattern (bulk_import replace_media=[og] + patch + copy-media)."""
from __future__ import annotations
import json, os, time
import requests
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient  # noqa: E402

plan = {x["id"]: x for x in json.load(open(os.path.join(os.environ["TEMP"], "wellwit_plan.json"), encoding="utf-8"))}
client = ResearchApiClient()


def _admin_base():
    return os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")


def _headers():
    return {"X-Internal-Secret": os.environ["INTERNAL_API_SECRET"].strip()}


def copy_media(rid):
    return requests.post(f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1",
                         headers=_headers(), timeout=240).status_code


def bo(fn):
    for a in range(7):
        try:
            return fn()
        except Exception as e:
            if any(c in str(e) for c in ("429", "502", "503")):
                time.sleep(4 * (a + 1)); continue
            raise
    raise SystemExit("gave up")


# only touch robots whose hero is not yet owned CDN
robots = bo(lambda: client.list_robots_for_company(1423))
todo = [r["id"] for r in robots if "cdn.robotaigeek.com" not in str(r.get("s3_image") or r.get("image") or "")]
print("to localize:", len(todo))
ok = 0
for rid in todo:
    og = plan[rid]["og"]
    row = {"id": rid, "name": plan[rid]["model"], "company_slug": "shenzhen-wellwit-robotics-co-ltd",
           "company_name": "Shenzhen Wellwit Robotics Co., Ltd.", "image": og, "images": [og], "s3_image": None}
    bo(lambda: client.bulk_import_robots([row], update_existing=True, patch_existing=True,
                                         skip_company_update=True, replace_media=True, status="pending_review"))
    bo(lambda: client._patch(f"robots/robots/{rid}/", {"image": og, "s3_image": None}))
    cm = copy_media(rid)
    after = bo(lambda: client._get(f"robots/robots/{rid}/"))
    owned = "cdn.robotaigeek.com" in str(after.get("s3_image") or after.get("image") or "")
    ok += owned
    print(f"  {rid} {plan[rid]['model']:15} copy-media={cm} owned_cdn={owned}")
print(f"localized {ok}/{len(todo)}")
