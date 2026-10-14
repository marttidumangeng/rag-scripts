"""Reconcile the two taxonomy vocabularies that disagree.

`robots/industries/` and `robots/uses/` serve the DB rows (what robots are
actually tagged with, and what the admin UI offers). `bulk_import` instead
resolves through robots/taxonomy_standard.py's CANONICAL_*_KEYS + synonym maps,
and anything it cannot resolve is DROPPED with only a warning in the response —
"ignored industry X — not in the RAG Standard vocabulary".

Hit three times in one day: `facilities` (Tengda), `mining` and `data-collection`
(Eddyfi). This measures the whole gap and, for each orphan, how many robots are
ALREADY tagged with it — usage is what decides the direction of the fix:
  used  -> the importer's canon is too narrow, promote the key
  unused-> a stray row, fold it into a synonym or retire it
"""
import sys
import time
from collections import Counter

from api_client import ResearchApiClient

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]
                       / "robotaigeek-server"))


def canon():
    """Read the canonical sets straight out of the server module, without Django."""
    import re
    src = open(__import__("pathlib").Path(__file__).resolve().parents[2]
               / "robotaigeek-server" / "robots" / "taxonomy_standard.py",
               encoding="utf-8").read()
    out = {}
    for name in ("CANONICAL_INDUSTRY_KEYS", "CANONICAL_USE_KEYS", "CANONICAL_MOVEMENT_KEYS"):
        m = re.search(rf"{name}\s*=\s*\((.*?)\)\n", src, re.S)
        out[name] = set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()
    for name in ("INDUSTRY_KEY_SYNONYMS", "USE_KEY_SYNONYMS"):
        m = re.search(rf"{name}[^=]*=\s*\{{(.*?)\n\}}", src, re.S)
        out[name] = dict(re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', m.group(1))) if m else {}
    return out


def main() -> int:
    c = ResearchApiClient()

    def get(p, params=None):
        for a in range(8):
            try:
                return c._get(p, params=params)
            except Exception:
                time.sleep(3 * (a + 1))
        raise RuntimeError(p)

    C = canon()
    report = {}
    for kind, ep, ckey, skey in (
            ("industry", "robots/industries/", "CANONICAL_INDUSTRY_KEYS", "INDUSTRY_KEY_SYNONYMS"),
            ("use", "robots/uses/", "CANONICAL_USE_KEYS", "USE_KEY_SYNONYMS")):
        d = get(ep, {"page_size": 200})
        rows = d if isinstance(d, list) else d.get("results", [])
        db = {r["key"]: r for r in rows}
        canonical, syn = C[ckey], C[skey]
        # a DB key is importable if it IS canonical or maps through a synonym
        orphans = [k for k in db if k not in canonical and k not in syn]
        missing_rows = sorted(canonical - set(db))
        report[kind] = {"db": db, "orphans": sorted(orphans), "missing_rows": missing_rows,
                        "canonical": canonical, "syn": syn}
        print(f"== {kind}: {len(db)} DB rows, {len(canonical)} canonical, "
              f"{len(orphans)} DB keys the importer DROPS, "
              f"{len(missing_rows)} canonical keys with no DB row")

    # usage: how many robots already carry each orphan?
    print("\nMeasuring current usage across the catalogue (this decides the fix)...")
    counts = {"industry": Counter(), "use": Counter()}
    page, seen = 1, 0
    while True:
        d = get("robots/robots/", {"page": page, "page_size": 100,
                                   "fields": "id,industries,uses"})
        rows = d.get("results", [])
        if not rows:
            break
        for r in rows:
            seen += 1
            for i in (r.get("industries") or []):
                counts["industry"][i["key"] if isinstance(i, dict) else i] += 1
            for u in (r.get("uses") or []):
                counts["use"][u["key"] if isinstance(u, dict) else u] += 1
        if not d.get("next"):
            break
        page += 1
        if page > 70:
            break
    print(f"  scanned {seen} robots\n")

    for kind in ("industry", "use"):
        rep = report[kind]
        print("=" * 78)
        print(f"{kind.upper()} — DB keys the importer silently DROPS:")
        used, unused = [], []
        for k in rep["orphans"]:
            n = counts[kind][k]
            (used if n else unused).append((k, n))
        used.sort(key=lambda x: -x[1])
        print(f"  IN USE ({len(used)}) — importer canon is too narrow, promote these:")
        for k, n in used:
            print(f"     {k:24s} {n:5d} robots")
        print(f"  UNUSED ({len(unused)}) — stray rows, fold or retire:")
        print("     " + ", ".join(k for k, _ in unused))
        if rep["missing_rows"]:
            print(f"  canonical keys with NO DB row ({len(rep['missing_rows'])}): "
                  f"{', '.join(rep['missing_rows'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
