"""Authoritative Motoman Spec Finder catalog (from industrial page 2026-07-20)."""
from __future__ import annotations

import json
from pathlib import Path

# (payload_kg, vert_reach_mm, hor_reach_mm) — Motoman Spec Finder
MODELS = {
    # GP
    "GP4": (4, 1008, 550),
    "GP7": (7, 1693, 927),
    "GP8": (8, 1312, 727),
    "GP8L": (8, 2894, 1636),
    "GP12": (12, 2511, 1440),
    "GP20HL": (20, 5622, 3124),
    "GP25": (25, 3089, 1730),
    "GP25-12": (12, 3649, 2010),
    "GP35L": (35, 4449, 2538),
    "GP50": (50, 3578, 2061),
    "GP70L": (70, 4715, 2732),
    "GP88": (88, 3751, 2236),
    "GP110": (110, 3751, 2236),
    "GP110B": (110, 3792, 2236),
    "GP165R": (165, 4782, 3140),
    "GP180": (180, 3393, 2702),
    "GP180-120": (120, 4105, 3058),
    "GP200R": (200, 4782, 3140),
    "GP200S": (200, 2295, 1886),
    "GP215": (215, 3894, 2912),
    "GP225": (225, 3393, 2702),
    "GP250": (250, 3490, 2710),
    "GP280": (280, 2962, 2446),
    "GP280L": (280, 3552, 3114),
    "GP400": (400, 2898, 2942),
    "GP400R": (400, 4908, 3518),
    "GP600": (600, 2898, 2942),
    # HC
    "HC10DTP": (10, 2400, 1200),
    "HC20DTP": (20, 3400, 1700),
    "HC30PL": (30, 3400, 1700),
    # NEX
    "NEX7": (7, 1693, 927),
    "NEX10": (10, 2027, 1101),
    "NEX20": (20, 2699, 1552),
    "NEX35": (35, 3715, 2063),
    # PL
    "PL80": (80, 3291, 2061),
    "PL190": (190, 3024, 3159),
    "PL320": (320, 3024, 3159),
    "PL500": (500, 3024, 3159),
    "PL800": (800, 3024, 3159),
    # MPP
    "MPP3H": (3, 600, 1300),
    "MPP3S": (3, 300, 800),
    # SG
    "SG400": (3, 200, 400),
    "SG650": (6, 210, 650),
    # MotoMini
    "MotoMini": (0.5, 495, 350),
    # MH / PH
    "MH900": (900, 6209, 4683),
    "PH130RF": (130, 4151, 3474),
    # MYS
    "MYS450F": (6, 180, 450),
    "MYS650LF": (6, 330, 650),
    "MYS850LF": (10, 420, 850),
    # AR
    "AR700": (8, 1312, 727),
    "AR900": (7, 1693, 927),
    "AR1440": (12, 2511, 1440),
    "AR1440E": (6, 2487, 1440),
    "AR1730": (25, 3089, 1730),
    "AR2010": (12, 3649, 2010),
    "AR3120": (20, 5622, 3124),
    # GA
    "GA50": (50, 3161, 2038),
    # SP
    "SP80": (80, 3751, 2236),
    "SP100": (100, 3751, 2236),
    "SP100B": (100, 3792, 2236),
    "SP110H": (110, 3367, 2044),
    "SP150R": (150, 4782, 3140),
    "SP165": (165, 3393, 2702),
    "SP165-105": (105, 4105, 3058),
    "SP180H": (180, 3393, 2702),
    "SP180H-110": (110, 3393, 2702),
    "SP185R": (185, 4782, 3140),
    "SP210": (210, 3393, 2702),
    "SP225H": (225, 3393, 2702),
    "SP235": (235, 3490, 2710),
    # MPX
    "MPX1150": (5, 1290, 727),
    "MPX1400": (5, 1852, 1256),
    "MPX1950": (7, 2730, 1450),
    "MPX2600": (15, 3643, 2000),
    "MPX3500": (15, 5095, 2700),
}

models = {}
for name, (p, v, h) in MODELS.items():
    models[name] = {
        "name": name,
        "payload_kg": float(p),
        "vert_reach_mm": float(v),
        "hor_reach_mm": float(h),
        "reach_mm": float(h),
    }

out = Path("staging/reports/yaskawa-motoman-catalog.json")
out.write_text(
    json.dumps(
        {
            "url": "https://www.motoman.com/en-us/products/robots/industrial",
            "count": len(models),
            "models": models,
            "source": "Motoman Spec Finder hardcoded 2026-07-20",
        },
        indent=2,
    ),
    encoding="utf-8",
)
print("wrote", len(models), out)
print("GP8", models["GP8"])
print("GP25", models["GP25"])
print("GP25-12", models["GP25-12"])
