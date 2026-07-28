"""One-off aerobot.cc fetch."""
import re
import requests

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
for url in [
    "https://www.aerobot.cc",
    "https://www.aerobot.cc/en",
    "https://www.aerobot.cc/en/products",
    "https://www.aerobot.cc/products",
]:
    try:
        r = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        print("URL:", url, "->", r.status_code, "final:", r.url, "len:", len(r.text))
        if r.status_code == 200:
            m = re.search(r"<title[^>]*>([^<]+)</title>", r.text, re.I)
            print("  title:", (m.group(1) if m else "none")[:120])
            links = set(re.findall(r'href=["\']([^"\']+)["\']', r.text, re.I))
            prod = sorted(l for l in links if any(x in l.lower() for x in ("product", "air", "robot", "scara", "delta")))
            print("  links:", prod[:20])
            imgs = re.findall(r'(?:src|data-src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', r.text, re.I)
            print("  imgs:", imgs[:8])
    except Exception as e:
        print("URL:", url, "ERROR", e)
