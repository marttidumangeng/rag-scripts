"""
cyberdyne_patch.py
Patches all 20 Cyberdyne Inc. staged JSON files with correct names, model names,
family names, specs, and missing videos.

Run from the research directory:
  python cyberdyne_patch.py
  python cyberdyne_patch.py --import
  python cyberdyne_patch.py --import --dry-run
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

PATCHES = {
    4646: {
        "name": "Wearable Cyborg HAL\u00ae",
        "model_name": "HAL\u00ae",
        "family_name": "HAL\u00ae (Hybrid Assistive Limb)",
        "family_key": "hal",
        "family_url": "https://www.cyberdyne.jp/en/products/about-hal",
    },
    4645: {
        "name": "CYIN\u00ae For Living Support",
        "model_name": "CY-BY02",
        "family_name": "CYIN\u00ae",
        "family_key": "cyin",
        "family_url": "https://www.cyberdyne.jp/en/products/cyin",
        "weight": "323 g (controller)",
        "weight_kg": 0.323,
        "runtime": "24 hours",
        "runtime_minutes": 1440,
        "connectivity": "Bluetooth 3.0 and 4.2 (BLE)",
        "dof": 8,
        "video_urls": [
            {
                "url": "https://www.youtube.com/watch?v=CPGogUzZ1Z4",
                "title": "Breakthrough Robotics Technology | Cyberdyne Rehabilitative Therapy",
                "description": "Overview of Cyberdyne HAL and CYIN technology for rehabilitation and assistive communication.",
            }
        ],
    },
    4642: {
        "name": "Transportation Robot",
        "model_name": "Transportation Robot",
        "family_name": "Cyberdyne Autonomous Robots",
        "family_key": "cyberdyne-autonomous",
        "family_url": "https://www.cyberdyne.jp/en/products/transportrobot",
        "length": "632 mm",
        "length_mm": 632,
        "width": "610 mm",
        "width_mm": 610,
        "height": "550 mm",
        "height_mm": 550,
        "weight_kg": 25,
        "payload_kg": 200,
        "speed": "30 m/min max",
        "runtime": "4 hours",
        "runtime_minutes": 240,
        "video_urls": [
            {
                "url": "https://www.youtube.com/watch?v=Fzd5Gi7d74U",
                "title": "Leading Edge of Cybernics for Future Well-being Society",
                "description": "Cyberdyne Transportation Robot overview.",
            }
        ],
    },
    4641: {
        "name": "Cleaning Robot CL02",
        "model_name": "CL02",
        "family_name": "Cyberdyne Autonomous Robots",
        "family_key": "cyberdyne-autonomous",
        "family_url": "https://www.cyberdyne.jp/en/products/cl02",
        "length": "620 mm",
        "length_mm": 620,
        "width": "480 mm",
        "width_mm": 480,
        "height": "470 mm",
        "height_mm": 470,
        "weight_kg": 63,
        "runtime": "~2 hours",
        "runtime_minutes": 120,
        "video_urls": [
            {
                "url": "https://www.youtube.com/watch?v=C6qthmCB1jg",
                "title": "CYBERDYNE\u696d\u52d9\u7528\u6e05\u639b\u30ed\u30dcCL02",
                "description": "CYBERDYNE CL02 autonomous cleaning robot \u2014 3,000 m\u00b2 per charge, 3D obstacle detection.",
            },
            {
                "url": "https://www.youtube.com/watch?v=05gmN2f6jns",
                "title": "CYBERDYNE CL02 Wiper Cleaning Type \u2014 Hospital Deployment",
                "description": "CL02 wiper cleaning type at Shonan Kamakura General Hospital.",
            },
        ],
    },
    4640: {
        "name": "Acoustic X\u00ae",
        "model_name": "Acoustic X\u00ae",
        "family_name": "Acoustic X\u00ae (Photoacoustic Imaging)",
        "family_key": "acoustic-x",
        "family_url": "https://www.cyberdyne.jp/en/products/acoustic-x",
        "video_urls": [
            {
                "url": "https://www.youtube.com/watch?v=Fzd5Gi7d74U",
                "title": "CYBERDYNE Acoustic X \u2014 Photoacoustic Imaging",
                "description": "Acoustic X real-time photoacoustic imaging using LED array light source.",
            }
        ],
    },
    4644: {
        "name": "JUKUSUI (NightWell)",
        "model_name": "JUKUSUI",
        "family_name": "Cyberdyne Digital Health",
        "family_key": "cyberdyne-digital",
        "family_url": "https://jukusui.com/en",
        "notes": "JUKUSUI is a sleep tracker and alarm app (iOS/Android) developed by C2, Inc. in partnership with Cyberdyne. Rebranded as NightWell in January 2026.",
        "video_urls": [
            {
                "url": "https://www.youtube.com/watch?v=Fzd5Gi7d74U",
                "title": "CYBERDYNE Digital Health \u2014 Cybernics for Well-being Society",
                "description": "Overview of Cyberdyne digital health products.",
            }
        ],
    },
    4639: {
        "name": "All-in-One",
        "model_name": "All-in-One",
        "family_name": "HAL\u00ae Peripheral Equipment",
        "family_key": "hal-peripheral",
        "family_url": "https://www.cyberdyne.jp/en/products/all-in-one",
        "length_mm": 1170,
        "width_mm": 650,
        "height_mm": 1500,
        "weight_kg": 55,
        "payload_kg": 150,
        "video_urls": [
            {
                "url": "https://www.youtube.com/watch?v=CPGogUzZ1Z4",
                "title": "Cyberdyne All-in-One Gait Training System",
                "description": "All-in-One assistive device used in combination with HAL for safer gait training.",
            }
        ],
    },
    4638: {
        "name": "HALTREAD\u00ae",
        "model_name": "HALTREAD",
        "family_name": "HAL\u00ae Peripheral Equipment",
        "family_key": "hal-peripheral",
        "family_url": "https://www.cyberdyne.jp/en/products/haltread",
        "length_mm": 2000,
        "width_mm": 900,
        "height_mm": 2300,
        "weight_kg": 120,
        "video_urls": [
            {
                "url": "https://www.youtube.com/watch?v=CPGogUzZ1Z4",
                "title": "Cyberdyne HALTREAD \u2014 Treadmill Gait Training with HAL",
                "description": "HALTREAD treadmill for effective walking exercise with HAL for Lower Limb.",
            }
        ],
    },
    4637: {
        "name": "Medicalcare Pit\u00ae",
        "model_name": "HPD-BT04-JP",
        "family_name": "HAL\u00ae Peripheral Equipment",
        "family_key": "hal-peripheral",
        "family_url": "https://www.cyberdyne.jp/en/products/medicalcare-pit",
        "length_mm": 2040,
        "width_mm": 860,
        "height_mm": 2395,
        "weight_kg": 130,
        "speed": "0.2\u20138.0 km/h",
        "video_urls": [
            {
                "url": "https://www.youtube.com/watch?v=CPGogUzZ1Z4",
                "title": "Cyberdyne Medicalcare Pit \u2014 Gait Rehabilitation System",
                "description": "Medicalcare Pit for safe gait training with HAL, with body weight support and real-time data.",
            }
        ],
    },
    4643: {
        "name": "Neuro HALFIT\u00ae",
        "model_name": "Neuro HALFIT",
        "family_name": "HAL\u00ae (Hybrid Assistive Limb)",
        "family_key": "hal",
        "family_url": "https://www.cyberdyne.jp/en/products/neuro-halfit",
        "video_urls": [
            {
                "url": "https://www.youtube.com/watch?v=CPGogUzZ1Z4",
                "title": "Cyberdyne Neuro HALFIT \u2014 HAL Rehabilitation Program",
                "description": "Neuro HALFIT HAL-powered rehabilitation for stroke and neurological conditions.",
            }
        ],
    },
    3046: {
        "name": "HAL\u00ae Lumbar Type for Labor Support",
        "model_name": "HAL-LB03",
        "family_name": "HAL\u00ae Lumbar Type",
        "family_key": "hal-lumbar",
        "family_url": "https://www.cyberdyne.jp/en/products/hal-lumbar-laborsupport",
        "weight_kg": 3.1,
        "length_mm": 292,
        "width_mm": 450,
        "height_mm": 522,
        "runtime": "~4.5 hours",
        "runtime_minutes": 270,
        "ip_rating": "IPX4 / IP5X",
    },
    4407: {
        "name": "HAL\u00ae Lumbar Type for Labor Support",
        "model_name": "HAL-LB03-SSSJP",
        "family_name": "HAL\u00ae Lumbar Type",
        "family_key": "hal-lumbar",
        "family_url": "https://www.cyberdyne.jp/en/products/hal-lumbar-laborsupport",
        "weight_kg": 3.1,
        "length_mm": 292,
        "width_mm": 450,
        "height_mm": 522,
        "runtime": "~4.5 hours",
        "runtime_minutes": 270,
        "ip_rating": "IPX4 / IP5X",
    },
    4408: {
        "name": "HAL\u00ae Lumbar Type for Labor Support",
        "model_name": "HAL-LB01",
        "family_name": "HAL\u00ae Lumbar Type",
        "family_key": "hal-lumbar",
        "family_url": "https://www.cyberdyne.jp/en/products/hal-lumbar-laborsupport",
        "weight_kg": 3.1,
        "length_mm": 292,
        "width_mm": 450,
        "height_mm": 522,
        "runtime": "~4.5 hours",
        "runtime_minutes": 270,
        "notes": "HAL-LB01 does not have waterproof/dustproof function.",
    },
    4402: {
        "name": "Medical HAL\u00ae \u2013 Lower Limb Type",
        "model_name": "HAL-ML08",
        "family_name": "HAL\u00ae Medical",
        "family_key": "hal-medical",
        "family_url": "https://www.cyberdyne.jp/en/products/hal-lowerlimb-medical",
        "weight_kg": 13,
        "height_mm": 1190,
        "width_mm": 480,
        "length_mm": 440,
        "runtime": "~1 hour",
        "runtime_minutes": 60,
        "dof": 4,
        "notes": "Models: HAL-ML08 (150\u2013190 cm), HAL-ML07 (100\u2013150 cm), HAL-ML05 (150\u2013190 cm). CE marked (MDR) and FDA 510(k) cleared.",
    },
    4403: {
        "name": "Medical HAL\u00ae \u2013 Single Joint Type",
        "model_name": "HAL-SJ",
        "family_name": "HAL\u00ae Medical",
        "family_key": "hal-medical",
        "family_url": "https://www.cyberdyne.jp/en/products/hal-singlejoint-medical",
        "weight_kg": 1.5,
        "length_mm": 200,
        "width_mm": 200,
        "height_mm": 944,
        "runtime": "~120 minutes",
        "runtime_minutes": 120,
        "dof": 1,
        "notes": "CE marked (MDD 93/42/EEC), FDA Class I. Trains elbow, knee, ankle, and shoulder joints.",
    },
    4404: {
        "name": "Well-Being HAL\u00ae \u2013 Lower Limb Type",
        "model_name": "HAL-FL08",
        "family_name": "HAL\u00ae Well-Being",
        "family_key": "hal-wellbeing",
        "family_url": "https://www.cyberdyne.jp/en/products/hal-lowerlimb-wellbeing",
        "weight_kg": 13,
        "height_mm": 1190,
        "width_mm": 480,
        "length_mm": 440,
        "runtime": "~1 hour",
        "runtime_minutes": 60,
        "dof": 4,
        "notes": "HAL-FL08: wearer height 150\u2013190 cm, weight 40\u2013100 kg.",
    },
    4405: {
        "name": "Well-Being HAL\u00ae \u2013 Lower Limb Type",
        "model_name": "HAL-FL07",
        "family_name": "HAL\u00ae Well-Being",
        "family_key": "hal-wellbeing",
        "family_url": "https://www.cyberdyne.jp/en/products/hal-lowerlimb-wellbeing",
        "weight_kg": 9.5,
        "height_mm": 930,
        "width_mm": 400,
        "length_mm": 400,
        "runtime": "~1 hour",
        "runtime_minutes": 60,
        "dof": 4,
        "notes": "HAL-FL07: wearer height 100\u2013150 cm (pediatric), weight 15\u201350 kg.",
    },
    4406: {
        "name": "Well-Being HAL\u00ae \u2013 Lower Limb Type",
        "model_name": "HAL-FL05",
        "family_name": "HAL\u00ae Well-Being",
        "family_key": "hal-wellbeing",
        "family_url": "https://www.cyberdyne.jp/en/products/hal-lowerlimb-wellbeing",
        "weight_kg": 14,
        "height_mm": 1230,
        "width_mm": 470,
        "length_mm": 430,
        "runtime": "~1 hour",
        "runtime_minutes": 60,
        "dof": 4,
        "notes": "HAL-FL05: wearer height 150\u2013190 cm (S/M/L/X sizes), weight 40\u2013100 kg.",
    },
    4635: {
        "name": "Well-Being HAL\u00ae \u2013 Lower Limb Type",
        "model_name": "HAL-FL",
        "family_name": "HAL\u00ae Well-Being",
        "family_key": "hal-wellbeing",
        "family_url": "https://www.cyberdyne.jp/en/products/hal-lowerlimb-wellbeing",
        "runtime": "~1 hour",
        "runtime_minutes": 60,
        "dof": 4,
    },
    4636: {
        "name": "Well-Being HAL\u00ae \u2013 Single Joint Type",
        "model_name": "HAL-SJ-WB",
        "family_name": "HAL\u00ae Well-Being",
        "family_key": "hal-wellbeing",
        "family_url": "https://www.cyberdyne.jp/en/products/hal-singlejoint-wellbeing",
        "weight_kg": 1.5,
        "length_mm": 200,
        "width_mm": 200,
        "height_mm": 944,
        "runtime": "~120 minutes",
        "runtime_minutes": 120,
        "dof": 1,
    },
    1890: {
        "name": "HAL\u00ae Lumbar Type for Well-being",
        "model_name": "HAL-BB04",
        "family_name": "HAL\u00ae Lumbar Type",
        "family_key": "hal-lumbar",
        "family_url": "https://www.cyberdyne.jp/en/products/hal-lumbar-bb04",
        "weight_kg": 3.1,
        "ip_rating": "IP54",
        "notes": "Available in XS/S/M sizes. Supports caregiver and care-receiver. CAC Mode allows wear under 10 seconds.",
        "video_urls": [
            {
                "url": "https://www.youtube.com/watch?v=t3Ya9S7zQG4",
                "title": "Cyberdyne HAL Lumbar Support",
                "description": "CNBC International: How robotic power suits are helping workers in Japan.",
            }
        ],
    },
}

ALWAYS_OVERWRITE = {"name", "model_name", "family_name", "family_key", "family_url"}


def patch_record(record: dict, patch: dict) -> dict:
    for key, value in patch.items():
        if key == "video_urls":
            existing = record.get("video_urls") or []
            existing_urls = {v["url"] for v in existing if isinstance(v, dict)}
            for vid in (value or []):
                if isinstance(vid, dict) and vid.get("url") not in existing_urls:
                    existing.append(vid)
                    existing_urls.add(vid["url"])
            record["video_urls"] = existing
        elif key in ALWAYS_OVERWRITE:
            record[key] = value
        else:
            current = record.get(key)
            if current is None or current == "" or current == []:
                record[key] = value
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Patch Cyberdyne staged JSONs")
    parser.add_argument("--staging-dir", default="staging/robots/cyberdyne-inc/overnight")
    parser.add_argument("--import", dest="do_import", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    staging_dir = Path(args.staging_dir)
    if not staging_dir.exists():
        print(f"ERROR: {staging_dir} not found", file=sys.stderr)
        sys.exit(1)

    print(f"\n=== Cyberdyne Patch Script ===")
    print(f"Staging dir: {staging_dir.resolve()}")
    print(f"Patches: {len(PATCHES)} robots\n")

    patched = []
    for json_file in sorted(staging_dir.glob("robot_*.json")):
        raw = json.loads(json_file.read_text(encoding="utf-8"))
        records = raw if isinstance(raw, list) else [raw]
        changed = False
        robot_id = None
        for record in records:
            robot_id = record.get("id")
            if robot_id is None:
                try:
                    robot_id = int(json_file.stem.split("_")[1])
                except Exception:
                    pass
            if robot_id and int(robot_id) in PATCHES:
                patch_record(record, PATCHES[int(robot_id)])
                changed = True
        if changed:
            out = records if isinstance(raw, list) else records[0]
            json_file.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            patched.append(json_file)
            print(f"  Patched {json_file.name}  (id={robot_id})")

    print(f"\nTotal patched: {len(patched)} files")

    if args.do_import:
        from load_env import load_research_env
        load_research_env()
        from import_staging import import_staging
        result = import_staging(staging_dir, patch=True, dry_run=args.dry_run, replace_media=False)
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
