import re, pathlib, json
base = pathlib.Path(r"C:\Github_Personal\robot-ai-geek\scripts\research")
pat = re.compile(r"https?://filecenter\.deltaww\.com[^\s\"\'<>\\)]+", re.I)
pat2 = re.compile(r"//filecenter\.deltaww\.com[^\s\"\'<>\\)]+", re.I)
all_urls = {}
for name in ["drs40c4.html", "drs40l3ss2.html"]:
    text = (base / name).read_text(encoding="utf-8", errors="replace")
    urls = set(pat.findall(text))
    urls |= {"https:" + u for u in pat2.findall(text)}
    # decode common html entities in urls
    cleaned = set()
    for u in urls:
        u = u.replace("&amp;", "&").rstrip("\\")
        cleaned.add(u)
    all_urls[name] = sorted(cleaned)
    print(f"=== {name} ({len(cleaned)} URLs) ===")
    for u in cleaned:
        ls4 = " [LS4 in URL]" if "ls4" in u.lower() else ""
        print(u + ls4)
combined = sorted(set(u for lst in all_urls.values() for u in lst))
(base / "staging/reports/delta-heroes/drs40c4-candidates/candidate-urls.txt").write_text("\n".join(combined), encoding="utf-8")
print(f"\nTOTAL UNIQUE: {len(combined)}")
