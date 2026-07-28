import re
import time

import requests

from youtube_metadata import fetch_youtube_metadata

for q in (
    "Universal Robots UR18",
    "UR18 cobot Universal Robots",
    "Meet the UR18 Universal Robots",
):
    print("Q", q)
    r = requests.get(
        "https://www.youtube.com/results",
        params={"search_query": q},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', r.text)
    seen = []
    for i in ids:
        if i not in seen:
            seen.append(i)
    for i in seen[:8]:
        u = f"https://www.youtube.com/watch?v={i}"
        m = fetch_youtube_metadata(u)
        print(" ", repr((m.get("title") or "")[:90]), u)
        time.sleep(0.1)
