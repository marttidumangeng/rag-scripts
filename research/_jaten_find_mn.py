"""Find MN / piggyback / latent models in url-map that might help MN100."""
from __future__ import annotations

import json
from pathlib import Path

mapa = json.loads(Path("staging/reports/jaten-url-map.json").read_text(encoding="utf-8"))
for c in mapa["cards"]:
    n = c["name"].upper()
    if n.startswith("MN") or "MN100" in n or "PIGGY" in n or n.startswith("MN30") or n.startswith("MN50"):
        print(c["id"], c["name"], c.get("hero", "")[-70:], c.get("specs"))
