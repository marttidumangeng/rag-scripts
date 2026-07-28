"""Attach sourced FANUC renders to the 20 no-image robots (of 22; 2 have no live page).

These robots carry NO image at all, so there is nothing to purge — we simply PATCH
`images` (external craft.cloud url FIRST so Robot.image becomes a downloadable external
hero) then force copy-media to pull it into s3_image. Same external-first + force pattern
proven on the junk-hero repair; here it just fills blanks.

Every hero below was VISUALLY verified from the fanucamerica series page (contact sheets
staging/_fni/_contact.png + staging/_fdeep/_contact.png): a real FANUC robot of the right
series, no marketing card / label graphic / training photo. Series-level sharing across
variants is the accepted family trade (a real series arm beats a blank card).

No render exists for: 4115 M-800iA/60W, 4117 M-810iA/45 (no live page). Left blank + reported.

Usage:
  python attach_fanuc_noimg.py            # dry-run
  python attach_fanuc_noimg.py --ids 4098 # single test
  python attach_fanuc_noimg.py --apply
"""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path

_RD = Path(__file__).resolve().parent
if str(_RD) not in sys.path:
    sys.path.insert(0, str(_RD))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from load_env import load_research_env
load_research_env(local="--local" in sys.argv)
import requests
from api_client import ResearchApiClient

COMPANY_ID = 189
CDN = "https://cdn.craft.cloud/6166486b-1eb4-43d5-990c-ea573de4e750/assets/images/"

# per-robot image basenames, HERO FIRST (all visually verified genuine)
IMG = {
    4098: ["fanuc-lr-10ia-10-robot-arm-closeup.jpg"],
    4099: ["imts10_m1ia019180.jpg", "m-1ia-battery-picking.jpg"],
    4100: ["imts10_m1ia019180.jpg", "m-1ia-battery-picking.jpg"],
    # M-2iA hero lives under /assets/products/m-2/ (not /assets/images/) — full URL
    4101: ["https://cdn.craft.cloud/6166486b-1eb4-43d5-990c-ea573de4e750/assets/products/m-2/FANUC-M-2iA-stacking-waffles_2026-06-05-201856_gwvd.jpg", "m-2ia-indexing_2026-03-20-145444_edyu.jpg"],
    4102: ["https://cdn.craft.cloud/6166486b-1eb4-43d5-990c-ea573de4e750/assets/products/m-2/FANUC-M-2iA-stacking-waffles_2026-06-05-201856_gwvd.jpg", "m-2ia-indexing_2026-03-20-145444_edyu.jpg"],
    4103: ["m-3ia-3-axis-wrist.jpg", "m-3ia-packing-chocolate-boxes.jpg"],
    4104: ["m-3ia-3-axis-wrist.jpg", "m-3ia-packing-chocolate-boxes.jpg"],
    4105: ["r-1000ia-120f7b-spot-welding-solution-arm-dressout.jpg", "r-1000ia-120fb-spot-welding-car-body.jpg"],
    4106: ["r-1000ia-120f7b-spot-welding-solution-arm-dressout.jpg", "r-1000ia-120fb-spot-welding-car-body.jpg"],
    4107: ["r-1000ia-120f7b-spot-welding-solution-arm-dressout.jpg", "r-1000ia-120fb-spot-welding-car-body.jpg"],
    # R-2000iD hero lives under /assets/products/r-2000/ — full URL (shared series arm)
    4109: ["https://cdn.craft.cloud/6166486b-1eb4-43d5-990c-ea573de4e750/assets/products/r-2000/R-2000iC-165F-Transfer-Case-Handling-System.jpg"],
    4110: ["https://cdn.craft.cloud/6166486b-1eb4-43d5-990c-ea573de4e750/assets/products/r-2000/R-2000iC-165F-Transfer-Case-Handling-System.jpg"],
    4111: ["https://cdn.craft.cloud/6166486b-1eb4-43d5-990c-ea573de4e750/assets/products/r-2000/R-2000iC-165F-Transfer-Case-Handling-System.jpg"],
    4112: ["https://cdn.craft.cloud/6166486b-1eb4-43d5-990c-ea573de4e750/assets/products/r-2000/R-2000iC-165F-Transfer-Case-Handling-System.jpg"],
    4113: ["https://cdn.craft.cloud/6166486b-1eb4-43d5-990c-ea573de4e750/assets/products/r-2000/R-2000iC-165F-Transfer-Case-Handling-System.jpg"],
    4114: ["m-800ia60_black-gb.jpg", "m-800ia60_end-effector.jpg"],
    4116: ["fanuc-m-1000ia.jpg", "m1000ia_wrist.jpg"],
    4118: ["m-950ia-500-automotive-side-panel-handling.jpg"],
    4122: ["precision-image.jpg"],
    4123: ["dr3ib-6-stainless.jpg", "dr3ib_irpicktool-1.png"],
}
NO_RENDER = {4115: "M-800iA/60W (no live page)", 4117: "M-810iA/45 (no live page)"}


def _admin_base() -> str:
    return os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")


def _secret() -> str:
    s = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if s:
        return s
    env = _RD.parents[1] / "robotaigeek-server" / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip()
    return ""


def _copy_media(rid: int, secret: str) -> str:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    try:
        r = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
        return "ok" if r.ok else f"HTTP {r.status_code}"
    except requests.RequestException as e:
        return f"ERR {str(e)[:40]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(COMPANY_ID); break
        except Exception as e:
            print(f"list retry {a}: {str(e)[:60]}", file=sys.stderr); time.sleep(5)
    if robots is None:
        print("ERROR: fetch failed", file=sys.stderr); return 1
    by_id = {int(r["id"]): r for r in robots}

    # verify every candidate URL is a live image before planning
    S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    def healthy(u: str) -> bool:
        try:
            r = S.get(u, timeout=25)
            return bool(r.ok and r.headers.get("Content-Type", "").startswith("image") and len(r.content) > 6000)
        except Exception:
            return False

    ids = set(args.ids) if args.ids else set(IMG)
    plan, bad = [], []
    for rid in sorted(ids):
        r = by_id.get(rid)
        if not r:
            print(f"  {rid}: NOT in company {COMPANY_ID} pending set — skip", file=sys.stderr); continue
        if str(r.get("status") or "").lower() != "pending_review":
            print(f"  {rid} {r['name']}: status {r.get('status')} — SKIP (only touch pending_review)", file=sys.stderr); continue
        urls = [b if b.startswith("http") else CDN + b for b in IMG[rid]]
        live = [u for u in urls if healthy(u)]
        for u in urls:
            if u not in live:
                bad.append((rid, u.split("/")[-1]))
        if not live:
            print(f"  {rid} {r['name']}: NO healthy candidate — skip"); continue
        plan.append({"id": rid, "name": r["name"], "images": live})
        print(f"  {rid:<6}{r['name'][:24]:<25} -> {len(live)} img  {live[0].split('/')[-1][:44]}")

    print(f"\nto attach: {len(plan)} | dead candidate urls: {len(bad)} | no-render (left blank): {len(NO_RENDER)}")
    for rid, why in NO_RENDER.items():
        print(f"   NO-RENDER {rid}: {why}")
    for rid, fn in bad:
        print(f"   DEAD {rid}: {fn}")
    (_RD / "staging" / "reports" / "fanuc-noimg-attach-preview.json").write_text(
        json.dumps({"plan": plan, "dead": bad, "no_render": NO_RENDER}, indent=2, ensure_ascii=False), encoding="utf-8")
    if not args.apply:
        print("\nDry-run. Re-run with --apply (or --ids N)."); return 0

    secret = _secret()
    if not secret:
        print("ERROR: INTERNAL_API_SECRET missing", file=sys.stderr); return 1
    ok = fail = cm_warn = 0
    for p in plan:
        rid = p["id"]
        try:
            client._patch(f"robots/robots/{rid}/", {"images": p["images"]})
        except Exception as e:
            fail += 1; print(f"  FAIL {rid}: {str(e)[:70]}", file=sys.stderr); continue
        cm = _copy_media(rid, secret)
        if cm != "ok":
            cm_warn += 1
        ok += 1
        print(f"  ok {rid} {p['name']}: {len(p['images'])} imgs (copy_media={cm})")
        time.sleep(0.2)
    out = {"ok": fail == 0, "attached": ok, "failed": fail, "copy_media_warnings": cm_warn,
           "no_render": list(NO_RENDER)}
    print(json.dumps(out, indent=2))
    (_RD / "staging" / "reports" / "fanuc-noimg-attach-result.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
