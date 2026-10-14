"""Stage the Shandong Kewei / KOWELL catalogue (company 1604) for import.

SPECS are transcribed from each model's parameter-table IMAGE (the site publishes
no spec text). Six models publish no parameter table at all; for those only what
the page prose states in words is recorded, and reach is left blank rather than
inferred from the model code — the code is demonstrably approximate (KW1030M-1835
is described on-site as a 1850 mm working radius).

The KW1012B-2010 page is already in prod as robot 6737 and is skipped.
"""
import json
import re
import sys

SP = ("C:/Users/tramk/AppData/Local/Temp/claude/"
      "C--Github-Personal-robot-ai-geek/9cff51dd-ca8d-479a-8bd9-29d05105ebd3/scratchpad/")
OUT_DIR = "staging/robots/kewei"
ALREADY_IN_PROD = {"KW1012B-2010"}     # robot 6737

# code: (dof, payload_kg, reach_mm, repeatability_mm, weight_kg, kva, install, ip, main_uses)
SPECS = {
    "KW1010B-1440": (6, 10, 1440, 0.05, 210, "4.5", "floor/bracket/inverted", "IP56/IP67", "welding"),
    "KW1012B-1550": (6, 12, 1550, 0.05, 210, "4.5", "floor/bracket/inverted", "IP56/IP67", "multi"),
    "KW1015B-1700": (6, 15, 1700, 0.05, 215, "2.0", "ground", "IP54", "handling"),
    "KW1020B-2000": (6, 20, 2000, 0.05, 195, "3.0", "ground", "IP54", "handling"),
    "KW1030B-1850": (6, 30, 1850, 0.05, 190, "3.0", "ground", "IP54", "handling"),
    "KW1030D-1800": (6, 30, 1800, 0.10, 400, "2.0", "ground", "IP54", "palletizing"),
    "KW1030M-1835": (4, 30, 1835, 0.05, 220, "3.0", "ground", "IP54", "handling"),
    "KW1035B-1850": (6, 35, 1850, 0.05, 190, "3.0", "ground", "IP54", "handling"),
    "KW1040D-2000": (6, 40, 2000, 0.08, 750, "3.0", "ground", "IP54", "palletizing"),
    "KW1050B-2100": (6, 50, 2100, 0.05, 540, "5.0", "ground", "IP54", "handling"),
    "KW1060M-2100": (4, 60, 2100, 0.20, 500, "5.0", "ground", "IP54", "handling"),
    "KW1070B-2100": (6, 70, 2100, 0.05, 540, "5.0", "ground", "IP54", "handling"),
    "KW1080B-2200": (6, 80, 2200, 0.05, 540, "5.0", "ground", "IP54", "handling"),
    "KW1080B-2700": (6, 80, 2700, 0.05, 570, "5.0", "ground", "IP54", "handling"),
    "KW1170B-2700": (6, 170, 2700, 0.06, 1020, "11", "ground", "IP54", "handling"),
    "KW1220B-2700": (6, 220, 2700, 0.06, 1020, "11", "ground", "IP54", "handling"),
    "KW1220B-3200": (6, 220, 3200, 0.06, 1050, "11", "ground", "IP54", "handling"),
    "KW1280B-2700": (6, 280, 2700, 0.06, 1020, "11", "ground", "IP54", "handling"),
    "KW1300M-3200": (4, 300, 3200, 0.20, 1200, "12", "ground", "IP54", "handling"),
}

# These four DO publish a parameter table, just a small one (~1300px wide) that the
# >=3500px spec-image detector missed. Read at full resolution. Note the working
# radius is NOT the number in the model code — KW1005B-950 is 948 mm and
# KW1008B-830 is 827 mm — which is why reach is never inferred from a code.
SPECS.update({
    "KW1005B-950":  (6, 5, 948, 0.05, 43, "3.0", "ground", "IP65", "small"),
    "KW1008B-830":  (6, 8, 827, 0.05, 42, "3.0", "ground", "IP65", "small"),
    "KW1010B-920":  (6, 10, 920, 0.02, 47, "3.0", "floor/bracket/inverted", "IP67", "small"),
    "KW1010M-1500": (4, 10, 1500, 0.05, 165, "3.0", "floor/bracket/inverted", "IP56/IP67", "handling"),
})

# Only these two genuinely publish no table.
PROSE_ONLY = {
    "KW1080M-3000": (None, None, None, "wood"),
    "KW1080M-3400": (None, None, None, "wood"),
}

_B = "https://cdn.cnyandex.com/kw_en/uploads/"
# Explicit media for models whose automatic pick was wrong: the small spec table
# was being chosen as the HERO, and gerfg-1.jpg (a generic 6-axis arm) appears on
# both wood-board pages, so it is not either robot's photo.
MEDIA_OVERRIDE = {
    "KW1005B-950":  [_B + "KW1005B-950-1-scaled.jpg", _B + "05.jpg", _B + "0509.jpg"],
    "KW1008B-830":  [_B + "08.jpg", _B + "08-1.jpg", _B + "0808.jpg"],
    "KW1010B-920":  [_B + "10.jpg", _B + "10-1.jpg", _B + "fwefdwe.png"],
    "KW1010M-1500": [_B + "fewrfw.jpg", _B + "vfrefwefd.png", _B + "vwefvwe.png"],
    "KW1080M-3000": [_B + "3000.jpg", _B + "3000-1.jpg"],
    "KW1080M-3400": [_B + "3400.jpg", _B + "123.jpg"],
}

USES = {
    "welding":    "welding|assembly|material-handling",
    "multi":      "welding|material-handling|packaging|loading|unloading|spraying",
    "handling":   "material-handling|palletizing|loading|unloading",
    "palletizing": "material-handling|palletizing",
    "small":      "sorting|testing|assembly|material-handling|dispensing|loading|unloading",
    "wood":       "material-handling|loading|unloading",
}
INDUSTRIES = {
    "welding": "manufacturing|automotive", "multi": "manufacturing|electronics",
    "handling": "manufacturing|logistics", "palletizing": "manufacturing|logistics",
    "small": "electronics|manufacturing|healthcare", "wood": "manufacturing",
}
TAGS = {
    "welding": "Welding|arc-welding|spot-welding|6-Axis|Industrial Robot|Robotic Arm|Automation|Manufacturing",
    "multi": "Welding|6-Axis|Industrial Robot|Robotic Arm|Automation|Manufacturing",
    "handling": "Palletizing|Material Handling|Industrial Robot|Robotic Arm|Automation|Manufacturing",
    "palletizing": "Palletizing|Material Handling|Industrial Robot|Robotic Arm|Automation|Manufacturing",
    "small": "6-Axis|Industrial Robot|Robotic Arm|Assembly|Automation|Manufacturing",
    "wood": "Material Handling|Industrial Robot|Robotic Arm|Automation|Manufacturing",
}
PURPOSE = {
    "welding": "Robotic arc and spot welding in industrial weld cells.",
    "multi": "General-purpose industrial handling, cutting, laser welding and spraying.",
    "handling": "Handling, palletizing and machine loading/unloading in industry.",
    "palletizing": "Automated handling and palletizing.",
    "small": "Light-duty sorting, testing, labelling, assembly, dispensing and machine tending.",
    "wood": "Loading and handling boards for woodworking machinery.",
}


def slug(code: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", code.lower()).strip("-")



def clean_desc(body, code, title, payload, reach, dof, spec, kind):
    """Vendor prose, trimmed to a sentence boundary and de-stubbed.

    The raw copy opens either "It is a six axis robot arm..." or by restating the
    model name ("Arm robot 6 axis KW1008B-830 with a payload of 8kg..."), and a
    hard character cut leaves a half-word. Both are fixed here."""
    if not body:
        return ""
    t = body.strip()
    # strip a leading restatement of the product name / bare "It is a"
    for prefix in (title or "", code, "It is a ", "It is an ", "The "):
        if prefix and t.lower().startswith(prefix.lower()):
            t = t[len(prefix):].lstrip(" ,-–:")
            break
    if t[:1].islower():
        t = t[0].upper() + t[1:]
    if len(t) > 620:
        cut = t[:620]
        stop = max(cut.rfind(". "), cut.rfind("; "))
        t = (cut[:stop + 1] if stop > 200 else cut.rsplit(" ", 1)[0] + "...")
    t = t.strip()
    # Stripping the name can leave a fragment ("With a payload of 8kg, ...") or too
    # little to stand on its own — lead with the measured spec sentence instead.
    if spec and (t.startswith(("With ", "with ")) or len(t) < 200):
        axes = "six-axis" if dof == 6 else ("four-axis" if dof == 4 else f"{dof}-axis")
        art = "An" if str(payload)[0] in "811" and str(payload).startswith(("8", "11", "18")) else "A"
        lead = (f"{art} {payload} kg {axes} industrial arm with a {reach:,} mm working radius, "
                f"repeatable to ±{spec[3]} mm at {spec[4]} kg body weight.")
        tail = t[0].lower() + t[1:] if t[:1].isupper() else t
        # the vendor tail repeats the payload we just stated — drop that clause
        tail = re.sub(r"^with a payload of [\d.]+\s*kg,\s*", "", tail, flags=re.I)
        tail = tail[0].upper() + tail[1:] if tail else tail
        t = f"{lead} {tail}"
    return t.strip()


def build(code, rec, spec, prose):
    kind = spec[8] if spec else prose[3]
    dof = spec[0] if spec else prose[0]
    payload = spec[1] if spec else prose[1]
    reach = spec[2] if spec else prose[2]

    feats = []
    if dof and payload:
        axes = "six-axis" if dof == 6 else ("four-axis" if dof == 4 else f"{dof}-axis")
        reach_txt = f" with a {reach:,} mm working radius" if reach else ""
        feats.append(f"Vertically articulated {axes} arm rated {payload} kg payload{reach_txt}.")
    if spec:
        feats += [
            f"Position repetition accuracy of ±{spec[3]} mm; body weight {spec[4]} kg.",
            f"Power capacity {spec[5]} kVA; protection rated equivalent to {spec[7]}.",
            ("Mounts floor standing, bracket standing or inverted (hanging)."
             if spec[6].startswith("floor") else "Ground (floor) mounted installation."),
            "Rated for 0-45 °C and 20-80% RH, non-condensing.",
        ]
    body = (rec["body"] or "").strip()
    if body:
        feats.append(body if len(body) < 300 else body[:297].rsplit(" ", 1)[0] + "...")

    desc = clean_desc(body, code, rec["title"], payload, reach, dof, spec, kind)
    if not desc and spec:
        desc = (f"A {payload} kg, {reach:,} mm {'six' if dof == 6 else 'four'}-axis industrial arm "
                f"from Kewei, rated to ±{spec[3]} mm repeatability at {spec[4]} kg body weight, "
                f"published for {'welding' if kind == 'welding' else 'handling and palletizing'} duty.")

    row = {
        "name": rec["title"] or code,
        "company_slug": "shandong-kewei-robot", "company_name": "Shandong Kewei Robot",
        "model_name": code, "variant_code": code,
        "family_name": "Kewei KW Series", "family_key": "kewei:kw-series",
        "url": rec["url"], "product_url_scope": "exact_variant",
        "manufacturer_country_code": "CN", "source_locale": "en",
        "description": desc, "purpose": PURPOSE[kind], "features": "\n".join(feats),
        "availability_status_key": "released",
        "movement_type_keys": "stationary",
        "industry_keys": INDUSTRIES[kind], "use_keys": USES[kind],
        "category_slugs": "industrial-robot|robotic-arms",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS[kind],
        "environment": "Indoor industrial; 0-45 °C, 20-80% RH, non-condensing." if spec else "",
        "research_notes": (
            f"Specs transcribed from the vendor parameter-table image {rec['spec_image']}"
            if spec else
            "No parameter table published for this model; only figures stated in the page prose are "
            "recorded. Reach left blank rather than inferred from the model code, which is "
            "approximate (KW1030M-1835 is described on-site as 1850 mm)."),
    }
    if payload:
        row["payload_kg"] = float(payload)
    if reach:
        row["reach_mm"] = float(reach)
    if dof:
        row["dof"] = int(dof)
    if spec:
        row["repeatability_mm"] = float(spec[3])
        row["weight_kg"] = float(spec[4])
        row["mounting_options"] = ("Floor standing, bracket standing, or inverted (hanging)."
                                   if spec[6].startswith("floor") else "Ground (floor) mounted.")
    # The parameter-table image is the only place the specs exist, so it is cited
    # as a datasheet source alongside the product page.
    srcs = [{"url": rec["url"], "type": "website", "title": rec["title"] or code}]
    spec_img = rec.get("spec_image") or ""
    if not spec_img and code in MEDIA_OVERRIDE and len(MEDIA_OVERRIDE[code]) > 1:
        spec_img = MEDIA_OVERRIDE[code][1]
    if spec_img and spec:
        srcs.append({"url": spec_img, "type": "datasheet",
                     "title": f"{code} parameter table"})
    row["sources"] = srcs
    row["information_source_urls"] = "|".join(x["url"] for x in srcs)

    if code in MEDIA_OVERRIDE:
        imgs = list(MEDIA_OVERRIDE[code])
    else:
        imgs = list(rec["photos"]) + list(rec["envelope_images"])
        if rec["spec_image"]:
            imgs.append(rec["spec_image"])
    if imgs:
        row["image"] = imgs[0]
        row["images"] = imgs[:5]
    return row


def main() -> int:
    import os
    models = json.load(open(SP + "kewei_classified.json", encoding="utf-8"))["models"]
    os.makedirs(OUT_DIR, exist_ok=True)
    built = 0
    for code, rec in sorted(models.items()):
        if code in ALREADY_IN_PROD:
            print(f"  {code}: already prod robot 6737, skipping")
            continue
        spec, prose = SPECS.get(code), PROSE_ONLY.get(code)
        if not spec and not prose:
            print(f"  {code}: NO spec and NO prose entry — skipping")
            continue
        row = build(code, rec, spec, prose)
        with open(f"{OUT_DIR}/{slug(code)}.json", "w", encoding="utf-8") as fh:
            json.dump(row, fh, ensure_ascii=False, indent=1)
        built += 1
        print(f"  {code:14s} payload={row.get('payload_kg')} reach={row.get('reach_mm')} "
              f"dof={row.get('dof')} imgs={len(row.get('images', []))} | {row['name'][:40]}")
    print(f"\nstaged {built} files in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
