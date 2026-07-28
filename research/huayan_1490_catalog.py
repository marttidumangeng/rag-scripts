"""Curated current catalog facts for Huayan Robotics company 1490."""
from __future__ import annotations

import re
from typing import TypedDict


class CatalogModel(TypedDict):
    model: str
    family: str
    family_url: str
    description: str
    purpose: str
    features: str
    typed: dict[str, int | float | str]
    sources: list[str]
    videos: list[str]
    dead_search: str


FAMILY_URLS = {
    "Elfin": "https://www.huayan-robotics.net/elfin-collaborative-robot",
    "Elfin-Pro": "https://www.huayan-robotics.net/elfin-pro-collaborative-robot",
    "Elfin-Ex": (
        "https://www.huayan-robotics.net/"
        "elfin-ex-explosion-proof-collaborative-robot"
    ),
    "S": "https://www.huayan-robotics.com/s",
    "Echo": "https://www.huayan-robotics.net/7-axis-humanoid-robotic-arm",
    "HY": "https://www.huayan-robotics.net/7-axis-humanoid-robotic-arm",
    "STAR": "https://www.huayan-robotics.net/star-mobile-manipulator",
    "Elfin-Li": "https://www.huayan-robotics.com/li",
    "S-Li": "https://www.huayan-robotics.com/li",
}

FAMILY_MODELS = {
    "Elfin": ("E03", "E05", "E05-L", "E10", "E10-L", "E12", "E15"),
    "Elfin-Pro": (
        "E03-Pro",
        "E05-Pro",
        "E05L-Pro",
        "E10-Pro",
        "E10L-Pro",
        "E12-Pro",
        "E15-Pro",
    ),
    "Elfin-Ex": ("E05F", "E10F", "E10F-L", "E12F", "E15F"),
    "S": ("S20", "S30", "S40", "S50", "S60"),
    "Echo": ("Echo 3", "Echo 5", "Echo 15"),
    "HY": ("HY 3", "HY 7", "HY 15"),
    "STAR": ("STAR-S", "STAR-L", "STAR-M", "STAR-H"),
    "Elfin-Li": ("E03Li", "E05Li", "E05Li-L", "E10Li", "E12Li", "E15Li"),
    "S-Li": ("S20Li", "S30Li"),
}

ELFIN_BASE = {
    "E03": (18, 4, 590, 0.02),
    "E05": (25, 7, 800, 0.02),
    "E05-L": (26, 5, 950, 0.02),
    "E10": (43, 12, 1000, 0.03),
    "E10-L": (45, 10, 1300, 0.03),
    "E12": (70, 12, 1800, 0.05),
    "E15": (60, 18, 1300, 0.05),
}
ELFIN_EX = {
    "E05F": (25, 7, 800, 0.02),
    "E10F": (43, 12, 1000, 0.03),
    "E10F-L": (45, 10, 1300, 0.03),
    "E12F": (72, 12, 1800, 0.05),
    "E15F": (60, 18, 1300, 0.05),
}
S_SERIES = {
    "S20": (64, 20, 1700, 6, 0.03),
    "S30": (93, 30, 1800, 6, 0.05),
    "S40": (89, 40, 2000, 5, 0.05),
    "S50": (156, 50, 2000, 6, 0.1),
    "S60": (151, 60, 2000, 5, 0.1),
}
SEVEN_AXIS = {
    "Echo 3": (8, 3, 555, 0.02),
    "Echo 5": (12, 5, 605, 0.03),
    "Echo 15": (22, 15, 850, 0.05),
    "HY 3": (8, 3.5, 625, 0.02),
    "HY 7": (12, 7, 670, 0.03),
    "HY 15": (22, 15, 850, 0.05),
}
STAR = {
    "STAR-S": (1.5, 360),
    "STAR-L": (1.5, 600),
    "STAR-M": (1.1, 720),
    "STAR-H": (1.5, 720),
}

EXISTING_ID_BY_MODEL = {
    "E03": 5295,
    "E05-L": 5296,
    "E05": 5297,
    "E10-L": 5298,
    "E10": 5299,
    "E12": 5300,
    "E15": 5301,
    "E03-Pro": 3670,
    "E05-Pro": 3671,
    "E05L-Pro": 3672,
    "E10-Pro": 3673,
    "E10L-Pro": 3674,
    "E12-Pro": 3675,
    "E15-Pro": 3676,
    "E05F": 3683,
    "E10F": 3684,
    "E10F-L": 3685,
    "E12F": 3686,
    "E15F": 3687,
    "S20": 3677,
    "S30": 5205,
    "S40": 3680,
    "S50": 3681,
    "S60": 3682,
}

RETIREMENT_CANDIDATES = {
    3679: "Legacy S35; absent from current model tables",
    5302: "Published Echo family shell superseded by six model records",
    5303: "Published STAR family shell superseded by four model records",
}

E10L_PRO_VIDEO = "https://www.youtube.com/watch?v=3-M9hGWkqwA"


def normalize_model_code(value: str) -> str:
    """Normalize display names without collapsing model variants."""
    text = value.casefold()
    for phrase in (
        "elfin-ex",
        "elfin ex",
        "elfin-pro",
        "elfin pro",
        "elfin",
        "collaborative robot",
        "heavy payload robot",
        "robotic arm",
        "robot",
        "series",
    ):
        text = text.replace(phrase, " ")
    return re.sub(r"[^a-z0-9]+", "", text)


def _arm_typed(values: tuple[int, int, int, float]) -> dict[str, int | float | str]:
    weight, payload, reach, repeatability = values
    return {
        "weight_kg": weight,
        "weight": f"{weight} kg",
        "payload_kg": payload,
        "reach_mm": reach,
        "repeatability_mm": repeatability,
        "dof": 6,
    }


def _arm_features(
    model: str,
    typed: dict[str, int | float | str],
    extra: str,
) -> str:
    return (
        f"Official {model} specifications: {typed['payload_kg']} kg payload, "
        f"{typed['reach_mm']} mm reach, {typed['weight_kg']} kg robot weight, "
        f"±{typed['repeatability_mm']} mm repeatability, and six axes. {extra}"
    )


def _row(
    *,
    model: str,
    family: str,
    description: str,
    purpose: str,
    features: str,
    typed: dict[str, int | float | str],
    videos: list[str] | None = None,
    dead_search: str,
) -> CatalogModel:
    family_url = FAMILY_URLS[family]
    return {
        "model": model,
        "family": family,
        "family_url": family_url,
        "description": description,
        "purpose": purpose,
        "features": features,
        "typed": typed,
        "sources": [family_url],
        "videos": list(videos or []),
        "dead_search": dead_search,
    }


def _build_catalog() -> list[CatalogModel]:
    rows: list[CatalogModel] = []

    for model, values in ELFIN_BASE.items():
        typed = _arm_typed(values)
        rows.append(
            _row(
                model=model,
                family="Elfin",
                description=(
                    f"Huayan {model} is a six-axis Elfin collaborative robot for "
                    "flexible industrial automation and human-robot workspaces."
                ),
                purpose=(
                    "Assembly and precision handling\n"
                    "Machine tending and loading\n"
                    "Welding, grinding, spraying, and inspection"
                ),
                features=_arm_features(
                    model,
                    typed,
                    "The Elfin family supports integrated deployment for assembly, "
                    "picking, welding, grinding, spraying, medical procedures, and inspection.",
                ),
                typed=typed,
                dead_search="exact public release year and exact-model official video",
            )
        )

    for model in FAMILY_MODELS["Elfin-Pro"]:
        base = model.replace("L-Pro", "-L").replace("-Pro", "")
        typed = _arm_typed(ELFIN_BASE[base])
        rows.append(
            _row(
                model=model,
                family="Elfin-Pro",
                description=(
                    f"Huayan {model} is a six-axis Elfin-Pro collaborative robot "
                    "with integrated force-control and vision-oriented options."
                ),
                purpose=(
                    "Precision assembly and screwdriving\n"
                    "Welding, spraying, and polishing\n"
                    "Vision-guided pick-and-place"
                ),
                features=_arm_features(
                    model,
                    typed,
                    "Elfin-Pro adds internal wiring, force-control and vision solution "
                    "options, with IP66 configurations for demanding applications.",
                ),
                typed=typed,
                videos=[E10L_PRO_VIDEO] if model == "E10L-Pro" else [],
                dead_search=(
                    "exact public release year"
                    if model == "E10L-Pro"
                    else "exact public release year and exact-model official video"
                ),
            )
        )

    for model, values in ELFIN_EX.items():
        typed = _arm_typed(values)
        rows.append(
            _row(
                model=model,
                family="Elfin-Ex",
                description=(
                    f"Huayan {model} is an explosion-proof Elfin-Ex collaborative "
                    "robot for hazardous industrial environments."
                ),
                purpose=(
                    "Petrochemical material handling\n"
                    "Painting, coating, and refueling\n"
                    "Hazardous-area automation"
                ),
                features=_arm_features(
                    model,
                    typed,
                    "The IP66 arm is rated Ex pxb IIC T6 Gb and Ex pxb IIIC T80℃ Db "
                    "for petrochemical, coating, refueling, and hazardous-material work.",
                ),
                typed=typed,
                dead_search="exact public release year and exact-model official video",
            )
        )

    for model, values in S_SERIES.items():
        weight, payload, reach, dof, repeatability = values
        typed: dict[str, int | float | str] = {
            "weight_kg": weight,
            "weight": f"{weight} kg",
            "payload_kg": payload,
            "reach_mm": reach,
            "dof": dof,
            "repeatability_mm": repeatability,
        }
        rows.append(
            _row(
                model=model,
                family="S",
                description=(
                    f"Huayan {model} is an S-series heavy-payload collaborative "
                    "robot for high-load industrial handling."
                ),
                purpose=(
                    "Palletizing and heavy material handling\n"
                    "Machine tending and assembly\n"
                    "Agricultural and industrial automation"
                ),
                features=(
                    f"Current official Chinese specifications: {payload} kg payload, "
                    f"{reach} mm reach, {weight} kg robot weight, {dof} axes, and "
                    f"±{repeatability} mm repeatability. The S family targets palletizing, "
                    "machine tending, assembly, material handling, and agriculture."
                ),
                typed=typed,
                dead_search="exact public release year and exact-model official video",
            )
        )

    for model, values in SEVEN_AXIS.items():
        weight_limit, payload, reach, repeatability = values
        family = "Echo" if model.startswith("Echo") else "HY"
        typed = {
            "payload_kg": payload,
            "reach_mm": reach,
            "repeatability_mm": repeatability,
            "dof": 7,
        }
        rows.append(
            _row(
                model=model,
                family=family,
                description=(
                    f"Huayan {model} is a seven-axis torque-sensing humanoid-style "
                    "robotic arm for dexterous research and automation."
                ),
                purpose=(
                    "Dexterous manipulation and embodied-AI research\n"
                    "Human-like assembly and handling\n"
                    "Force-controlled robotic experimentation"
                ),
                features=(
                    f"Official specifications: {payload} kg payload, {reach} mm reach, "
                    f"under {weight_limit} kg arm weight, ±{repeatability} mm "
                    "repeatability, and seven axes. Includes joint torque sensors, "
                    "EtherCAT, 48 V DC, IP54 protection, and at least 2 m/s TCP speed."
                ),
                typed=typed,
                dead_search="exact weight, public release year, and exact-model official video",
            )
        )

    star_bases = {
        "STAR-S": "HR150 with E03 or E05 arm",
        "STAR-L": "HR300 with E03, E05, E05-L, or E10 arm",
        "STAR-M": "HR600 with E05-L, E10, E10-L, or E15 arm",
        "STAR-H": "HR1200 with E05-L, E10, E10-L, or E15 arm",
    }
    for model, values in STAR.items():
        speed_mps, runtime = values
        typed = {"speed": round(speed_mps * 3.6, 2), "runtime_minutes": runtime}
        rows.append(
            _row(
                model=model,
                family="STAR",
                description=(
                    f"Huayan {model} is a STAR autonomous mobile manipulator combining "
                    f"a collaborative arm with the {star_bases[model]} platform."
                ),
                purpose=(
                    "Mobile grasping and material handling\n"
                    "CNC machine tending and inspection\n"
                    "Mobile assembly, healthcare, and delivery"
                ),
                features=(
                    f"Official configuration: {star_bases[model]}; {speed_mps} m/s "
                    f"maximum base speed and more than {runtime // 60} hours runtime. "
                    "Supports laser SLAM, optional hybrid vision navigation, ±0.5 mm "
                    "vision positioning, and TCP/IP, HTTP, and SDK interfaces."
                ),
                typed=typed,
                dead_search=(
                    "configuration-specific payload, complete dimensions, exact weight, "
                    "public release year, and exact-model official video"
                ),
            )
        )

    for family in ("Elfin-Li", "S-Li"):
        for model in FAMILY_MODELS[family]:
            rows.append(
                _row(
                    model=model,
                    family=family,
                    description=(
                        f"Huayan {model} is a {family} collaborative robot configured "
                        "for lithium-battery and clean manufacturing processes."
                    ),
                    purpose=(
                        "Battery-cell screwdriving and stacking\n"
                        "Pre-weld cleaning and labeling\n"
                        "Precision dispensing in battery production"
                    ),
                    features=(
                        "The official series supports eight models across a 3–30 kg "
                        "payload range and 590–1800 mm reach range, with up to ±0.02 mm "
                        "repeatability, IP66 protection, ISO Class 5 cleanliness, and "
                        "1000 Hz control. Per-model numeric values are deliberately "
                        "omitted because the public page provides only series ranges."
                    ),
                    typed={},
                    dead_search=(
                        "per-model payload, reach, weight, dimensions, repeatability, "
                        "public release year, and exact-model official video"
                    ),
                )
            )

    return rows


CATALOG = _build_catalog()
CURRENT_MODEL_CODES = {normalize_model_code(row["model"]) for row in CATALOG}
