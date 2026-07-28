import re, pathlib, urllib.request, urllib.parse

base = pathlib.Path(r"C:\Github_Personal\robot-ai-geek\scripts\research")
out_dir = base / "staging/reports/delta-heroes/drs40c4-candidates"
combined = (out_dir / "candidate-urls.txt").read_text(encoding="utf-8").strip().splitlines()

lines = ["# HEAD results for all extracted candidate URLs", ""]
for u in combined:
    req = urllib.request.Request(u, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status = r.status
            ct = r.headers.get("Content-Type", "")
            cl = r.headers.get("Content-Length", "?")
    except Exception as e:
        status, ct, cl = "ERR", "", str(e)
    ls4 = " LS4_IN_FILENAME" if "ls4" in u.lower() else ""
    lines.append(f"{status}\t{cl}\t{u}{ls4}")

(out_dir / "head-results.tsv").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines[:5]))
print(f"... ({len(combined)} URLs total, written to head-results.tsv)")

downloads = [
    ("01-drs40c4-page-hero-w756.jpg", "https://filecenter.deltaww.com/products/images/2310/202310251554484629001.JPG?w=756"),
    ("02-drs40c4-applications-photo.jpg", "https://filecenter.deltaww.com/Products/images/06/0606/Products-202512181135401675.jpg"),
    ("03-drs40c4-related-carousel-202202101723027788-w342.jpg", "https://filecenter.deltaww.com/products/Images/2202/202202101723027788001.JPG?w=342"),
]
# bonus: L3SS2 page hero for comparison
downloads.append(("04-drs40l3ss2-page-hero-w756-for-compare.jpg", "https://filecenter.deltaww.com/products/images/2310/202310251556586785001.JPG?w=756"))

for fname, url in downloads:
    dest = out_dir / fname
    urllib.request.urlretrieve(url, dest)
    print(f"DOWNLOADED {dest.name}\t{dest.stat().st_size}\t{url}")
