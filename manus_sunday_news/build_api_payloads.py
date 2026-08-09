#!/usr/bin/env python3
"""Build JSON payloads for posting the 4 articles to the RobotAIGeek CMS API."""
import json
import os
import re

ARTICLE_DIR = "/home/ubuntu/sunday_run_20260802/articles"
PAYLOAD_DIR = "/home/ubuntu/sunday_run_20260802/api_payloads"
os.makedirs(PAYLOAD_DIR, exist_ok=True)

CDN_BASE = "https://cdn.robotaigeek.com/images/"

articles_meta = [
    {"file": "20260802_article_1_funding.md", "hero": "20260802_hero_funding.jpg"},
    {"file": "20260802_article_2_exhibitions.md", "hero": "20260802_hero_exhibitions.jpg"},
    {"file": "20260802_article_3_technology.md", "hero": "20260802_hero_technology.jpg"},
    {"file": "20260802_article_4_economics.md", "hero": "20260802_hero_economics.jpg"},
]

for article in articles_meta:
    filepath = os.path.join(ARTICLE_DIR, article["file"])
    with open(filepath, "r") as f:
        content = f.read()

    # Extract metadata
    meta_title = re.search(r'Meta Title:\s*(.+)', content).group(1).strip()
    meta_desc = re.search(r'Meta Description:\s*(.+)', content).group(1).strip()
    slug = re.search(r'Slug:\s*(.+)', content).group(1).strip()

    # Extract body between Executive Summary and Internal Evidence Note
    body = content.split("**Executive Summary**")[1].split("**Internal Evidence Note**")[0].strip()
    # Remove the verification sentence
    body = body.replace("This analysis synthesizes company statements and public market activity.", "").strip()
    # Remove markdown headers
    body = re.sub(r'^## .+$', '', body, flags=re.MULTILINE)
    # Remove bold markers
    body = body.replace("**", "")
    # Clean up multiple newlines
    body = re.sub(r'\n{3,}', '\n\n', body).strip()

    # Extract executive summary (first paragraph after the marker)
    summary_text = body.split('\n\n')[0].strip()

    # Calculate read time
    word_count = len(body.split())
    read_time = max(1, round(word_count / 120))

    thumbnail_url = CDN_BASE + article["hero"]

    payload = {
        "title": meta_title,
        "content": body,
        "summary": summary_text,
        "thumbnail_url": thumbnail_url,
        "read_time_minutes": read_time,
        "meta_title": meta_title,
        "meta_description": meta_desc,
        "slug": slug,
    }

    payload_file = article["file"].replace(".md", ".json")
    payload_path = os.path.join(PAYLOAD_DIR, payload_file)
    with open(payload_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Payload saved: {payload_file}")

print("\nAll payloads ready.")
