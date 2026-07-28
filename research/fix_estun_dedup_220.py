"""Estun (company 220) full dedup — the catalog is triplicated: most real models
exist as plain / 'Estun '-prefixed / 'iER'-prefixed copies (+ wrong-reach variants).

Per prefix-normalized model name, keep ONE best copy and reject the duplicates.
Best = has typed specs > owned hero > published > clean (unprefixed) name > richer features.
If the keeper is not published but a published duplicate is being rejected, the keeper
is published (a swap) so the model stays live. Purely mechanical prefix-dedup — does
NOT touch singletons (a lone record is not a duplicate).

    cd scripts/research && export PYTHONIOENCODING=utf-8
    python fix_estun_dedup_220.py            # dry-run (prints every group's keep/reject)
    python fix_estun_dedup_220.py --apply
"""
from __future__ import annotations
import argparse, re, time
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient  # noqa: E402


def norm(name: str) -> str:
    n = name.strip().lower()
    n = re.sub(r"^estun\s+", "", n)
    n = re.sub(r"^i(er|uno|s)\b", r"\1", n)   # iER500 -> er500, iUNO.. -> uno..
    n = re.sub(r"^i(er|uno|s)", r"\1", n)     # iER500-... with no word boundary
    return re.sub(r"\s+", "", n)


def score(r: dict) -> tuple:
    hero = str(r.get("s3_image") or r.get("image") or "")
    return (
        1 if (r.get("payload_kg") or r.get("reach_mm")) else 0,   # correct specs first
        1 if not re.match(r"^(estun|i[eus])", r["name"].strip().lower()) else 0,  # clean (unprefixed) name
        2 if "cdn.robotaigeek" in hero else (1 if hero else 0),   # owned hero
        1 if r.get("status") == "published" else 0,               # already live
        min(len(r.get("features") or "") // 80, 4),               # feature richness
    )


def _bo(fn):
    for a in range(7):
        try:
            return fn()
        except Exception as e:
            if any(c in str(e) for c in ("429", "502", "503")):
                time.sleep(4 * (a + 1)); continue
            raise
    raise SystemExit("gave up")


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    c = ResearchApiClient()
    robots = [r for r in _bo(lambda: c.list_robots_for_company(220)) if r.get("status") != "rejected"]

    groups: dict[str, list] = {}
    for r in robots:
        groups.setdefault(norm(r["name"]), []).append(r)

    n_reject = n_publish = n_groups = 0
    for key, recs in sorted(groups.items()):
        if len(recs) < 2:
            continue
        n_groups += 1
        recs.sort(key=score, reverse=True)
        keeper, dups = recs[0], recs[1:]
        had_published = any(r.get("status") == "published" for r in recs)
        need_publish = had_published and keeper.get("status") != "published"
        print(f"[{key}] keep {keeper['id']} '{keeper['name']}' ({keeper.get('status')}, "
              f"pay={keeper.get('payload_kg')} reach={keeper.get('reach_mm')})"
              + ("  +PUBLISH" if need_publish else ""))
        for d in dups:
            print(f"    reject {d['id']} '{d['name']}' ({d.get('status')})")
        if not args.apply:
            n_reject += len(dups); n_publish += 1 if need_publish else 0
            continue
        if need_publish:
            _bo(lambda: c._patch(f"robots/robots/{keeper['id']}/",
                                 {"status": "published", "notes": "[DEDUP 2026-07-26] promoted as canonical over prefix/spec duplicates"}))
            n_publish += 1
        for d in dups:
            reason = f"duplicate: prefix/variant duplicate of canonical {keeper['name']} (id {keeper['id']})."
            _bo(lambda d=d: c._patch(f"robots/robots/{d['id']}/",
                                     {"status": "rejected", "rejection_reason": reason[:500],
                                      "notes": "[DEDUP 2026-07-26] " + reason}))
            n_reject += 1

    print(f"\n{'APPLIED' if args.apply else 'DRY-RUN'}: {n_groups} duplicate groups | "
          f"reject {n_reject} dups | publish {n_publish} canonical")


if __name__ == "__main__":
    main()
