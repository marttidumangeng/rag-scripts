"""Clean the Unical staging batch before import. DRY RUN unless APPLY=1.

Three defects, all visible in the staged rows:

1. NOT A ROBOT. "Full Unit Customization with 3D Vision and Robot" came from
   /solutions/, which the site's own nav files under "Case studies" - an
   application story, not a product. Same class as Effidence's "Gamme d'AMR".
   Dropped rather than imported and rejected later.

2. HOMEPAGE URLS. iR18-1200 and iR20-20-160 were staged with
   https://unical-robot.com/ as their source - the homepage, not their product
   page. Both have real pages; repointed.

3. THIN CONTENT IS NOT FIXED, because it is not a defect on our side. The whole
   product body on these pages is "iR18-600 Description Payload: 10 kg Maximum
   Reach: 817 mm" - 2,134 characters of which almost all is navigation. The
   ~135-character descriptions are a faithful reflection of the source, so
   short_description will fire and that is the honest outcome.
"""
import glob
import json
import os

STAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "staging", "robots", "unical-robot")
APPLY = os.environ.get("APPLY") == "1"

DROP = {"Full Unit Customization with 3D Vision and Robot"}
FIX_URL = {
    "UniBot iR18-1200": "https://unical-robot.com/products/ir18-1200/",
    "UniBot iR20-20-160": "https://unical-robot.com/products/ir20-20-160/",
}

for f in sorted(glob.glob(os.path.join(STAGE, "*.json"))):
    d = json.load(open(f, encoding="utf-8"))
    name = (d.get("name") or "").strip()

    if name in DROP:
        print(f"  DROP  {name[:44]}  (a /solutions/ case study, not a robot)")
        if APPLY:
            os.remove(f)
        continue

    if name in FIX_URL and (d.get("url") or "").rstrip("/") == "https://unical-robot.com":
        print(f"  URL   {name[:24]:<26} homepage -> {FIX_URL[name]}")
        if APPLY:
            d["url"] = FIX_URL[name]
            src = d.get("information_source_urls")
            if isinstance(src, str) and "unical-robot.com/" in src:
                d["information_source_urls"] = FIX_URL[name]
            json.dump(d, open(f, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

print("\n(DRY RUN)" if not APPLY else "\n  staging cleaned")
print("\nremaining:")
for f in sorted(glob.glob(os.path.join(STAGE, "*.json"))):
    d = json.load(open(f, encoding="utf-8"))
    print(f"  {d.get('name','')[:24]:<26} payload={str(d.get('payload_kg')):<6} "
          f"reach={str(d.get('reach_mm')):<7} imgs={len(d.get('images') or [])} "
          f"{(d.get('url') or '')[-34:]}")
