import requests, re
from web_extract import _resp_text
from scrape_trossen_heroes import extract_og_image, wix_media_id

robots = [
    (5266, 'aloha-solo'),
    (5267, 'aloha-stationary'),
    (5268, 'mobile-ai'),
    (5269, 'pincherx100'),
    (5270, 'viperx-300'),
    (5271, 'viperx-aloha'),
    (5272, 'widowx-250'),
    (5273, 'widowx-ai'),
    (5274, 'widowx-aloha-set'),
]
for rid, slug in robots:
    url = f'https://www.trossenrobotics.com/{slug}'
    r = requests.get(url, headers={'User-Agent': 'RobotAIGeek-ResearchAgent/1.0'}, timeout=30)
    html = _resp_text(r)
    og = extract_og_image(html)
    print(rid, slug, wix_media_id(og or ''))
