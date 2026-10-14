"""Identify what the short all-caps tag codes actually mean.

Tags like AR (290 robots), ACY (231), PL (106), UT (97), SP (85) and HC (41) sit
alongside spelled-out tags on the same robots - e.g. Tecan 6387 carries
['AR', 'Handling', 'HC', 'Healthcare', 'Laboratory', 'PL', 'Research', 'UT'].
They are used far too widely to be one-off junk, so they need identifying before
anything is deleted.

The API gives no exact tag filter: `?search=` runs a SUBSTRING match over the
legacy `tags` text column (searching "AR" returns 3,753 rows because it matches
Arm, Research, Warehouse), and there is no `tags/<id>/` detail route. So this
scans the catalogue and records, for every robot carrying one of the codes, its
company and its OTHER tags - the co-occurrence pattern is what reveals the
meaning.

`fields=` is ignored by the endpoint (full rows come back regardless), so a page
costs ~36s. Run in the background.
"""
import collections
import json
import sys
import time

from api_client import ResearchApiClient

TARGET = {"AR", "HC", "PL", "UT", "SP", "ACY", "GP", "GA", "PH", "NEX", "MYS",
          "MPX", "MPP", "MH", "SG", "SCI", "CAS", "CCA", "TKA", "116", "52",
          "AV", "Hip", "R&D", "USA"}
OUT = "_tag_codes.json"


def main() -> int:
    c = ResearchApiClient()
    hits = collections.defaultdict(list)
    cooccur = collections.defaultdict(collections.Counter)
    companies = collections.defaultdict(collections.Counter)
    page, seen = 1, 0
    while page <= 70:
        d = None
        for a in range(5):
            try:
                d = c._get("robots/robots/", {"page": page, "page_size": 100})
                break
            except Exception:
                time.sleep(3 * (a + 1))
        if d is None:
            break
        rows = d.get("results", [])
        if not rows:
            break
        for r in rows:
            seen += 1
            tg = [t if isinstance(t, str) else (t or {}).get("name")
                  for t in (r.get("tags") or [])]
            tg = [t for t in tg if t]
            co = r.get("company")
            co = co if isinstance(co, str) else (co or {}).get("name", "")
            for t in tg:
                if t in TARGET:
                    hits[t].append({"id": r.get("id"), "name": (r.get("name") or "")[:60],
                                    "company": co, "others": [x for x in tg if x not in TARGET]})
                    companies[t][co] += 1
                    for x in tg:
                        if x != t and x not in TARGET:
                            cooccur[t][x] += 1
        print("  page %d done (%d robots scanned)" % (page, seen), flush=True)
        if not d.get("next"):
            break
        page += 1

    json.dump({"scanned": seen,
               "hits": {k: v for k, v in hits.items()},
               "cooccur": {k: dict(v.most_common(15)) for k, v in cooccur.items()},
               "companies": {k: dict(v.most_common(10)) for k, v in companies.items()}},
              open(OUT, "w"), indent=1)

    print("\nscanned %d robots\n" % seen)
    for t in sorted(hits, key=lambda x: -len(hits[x])):
        print("=== %s  (%d robots)" % (t, len(hits[t])))
        print("    top co-occurring tags: %s" % dict(cooccur[t].most_common(8)))
        print("    top companies       : %s" % dict(companies[t].most_common(5)))
        for h in hits[t][:5]:
            print("      %5s %-46s | %s" % (h["id"], h["name"][:46], h["company"][:24]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
