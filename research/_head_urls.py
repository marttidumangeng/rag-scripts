import re, pathlib, urllib.request, urllib.parse
from collections import defaultdict

base = pathlib.Path(r"C:\Github_Personal\robot-ai-geek\scripts\research")
out_dir = base / "staging/reports/delta-heroes/drs40c4-candidates"
text_c4 = (base / "drs40c4.html").read_text(encoding="utf-8", errors="replace")
text_l3 = (base / "drs40l3ss2.html").read_text(encoding="utf-8", errors="replace")

def extract(text):
    urls = set(re.findall(r"https?://filecenter\.deltaww\.com[^\s\"\'<>\\)]+", text, re.I))
    urls |= {"https:" + u for u in re.findall(r"//filecenter\.deltaww\.com[^\s\"\'<>\\)]+", text, re.I)}
    out = set()
    for u in urls:
        u = u.replace("&amp;", "&").rstrip("\\")
        if u.endswith(".png") and "icon" in u.lower():
            continue
        out.add(u)
    return out

urls_c4 = extract(text_c4)
urls_l3 = extract(text_l3)
all_urls = sorted(urls_c4 | urls_l3)

# dedupe by path (ignore query)
by_path = defaultdict(list)
for u in all_urls:
    p = urllib.parse.urlparse(u)
    key = p.scheme + "://" + p.netloc + p.path
    by_path[key].append(u)

print("=== UNIQUE PATHS (product JPG candidates) ===")
paths = sorted(k for k in by_path if k.lower().endswith(('.jpg','.jpeg','.png')))
for key in paths:
    ls4 = " ** LS4 in path **" if "ls4" in key.lower() else ""
    print(key + ls4)

print("\n=== HEAD results (one URL per path, prefer largest w=) ===")
head_rows = []
for key in paths:
    variants = sorted(by_path[key], key=lambda u: int(re.search(r"w=(\d+)", u).group(1)) if re.search(r"w=(\d+)", u) else 9999, reverse=True)
    test_url = variants[0]
    req = urllib.request.Request(test_url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            ct = r.headers.get("Content-Type", "")
            cl = r.headers.get("Content-Length", "?")
            status = r.status
    except Exception as e:
        status, ct, cl = f"ERR:{e}", "", ""
    head_rows.append((key, test_url, status, ct, cl))
    print(f"{status}\t{cl}\t{ct}\t{key}")

# hero context snippets
for label, text in [("DRS40C4", text_c4), ("DRS40L3SS2", text_l3)]:
    for m in re.finditer(r".{0,80}(202310251554484629001|202310251556586785001|Products-202512181135401675|Products-202512181136212248).{0,80}", text, re.I|re.S):
        snippet = re.sub(r"\s+", " ", m.group(0))[:200]
        print(f"\n[{label} context] ...{snippet}...")
