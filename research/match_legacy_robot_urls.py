"""Propose RobotSlugAlias rows for old robot URLs (read-only against prod).

Input: old robot URLs or slugs, one per line (a Search Console export works:
any column holding /robot/<slug> is picked up). For each slug:

  resolves   the prod detail endpoint already finds it (no alias needed)
  candidate  it 404s; the best current robot and a confidence
  none       it 404s and nothing plausible matched (leave it as a 404)

Confidence:
  high    the old slug is the current name with a company prefix added or
          removed ("dobot_m1_pro" -> "M1 Pro" by Dobot), or it matches the
          current name exactly once punctuation is ignored
  medium  one name starts with the other ("ur7e" -> "UR7e Collaborative
          Robot"): usually the same machine, needs a human look
  low     only a search hit; do not alias without checking

Output: a CSV for review. Approved rows go to
  manage.py robot_slug_aliases --csv approved.csv   (dry run, then --apply)

Usage:
  PYTHONIOENCODING=utf-8 python match_legacy_robot_urls.py old_urls.txt review.csv
"""

from __future__ import annotations

import csv
import re
import sys
import time

import requests

API = 'https://ragadmin.robotaigeek.com/api/v1'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36'}
SLUG_RE = re.compile(r'/robot/([^/?#\s",]+)')


def key(value) -> str:
    return re.sub(r'[^a-z0-9]', '', str(value or '').lower())


def read_slugs(path):
    slugs = []
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            match = SLUG_RE.search(line)
            slug = match.group(1) if match else line.strip()
            if slug and slug.lower() != 'url' and slug not in slugs:
                slugs.append(slug)
    return slugs


def get(url, **params):
    for attempt in range(3):
        resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
        if resp.status_code != 429:
            return resp
        time.sleep(5 * (attempt + 1))
    return resp


def company_name(row):
    ref = row.get('company_ref')
    if isinstance(ref, dict):
        return ref.get('name') or ''
    return row.get('company') or ''


def score(slug, row):
    """(confidence, reason) for one search hit."""
    old, name, company = key(slug), key(row.get('name')), key(company_name(row))
    if not old or not name:
        return None
    if old == name:
        return 'high', 'same name'
    company_words = [key(w) for w in re.split(r'[\s\-_]+', company_name(row)) if key(w)]
    prefixes = {company} | ({company_words[0]} if company_words else set())
    for prefix in prefixes:
        if prefix and (old == prefix + name or name == prefix + old):
            return 'high', f'company prefix "{prefix}" added/removed'
    if name.startswith(old) or old.startswith(name):
        return 'medium', 'one name starts with the other'
    for prefix in prefixes:
        stripped = old[len(prefix):] if prefix and old.startswith(prefix) else old
        if stripped and (name.startswith(stripped) or stripped.startswith(name)):
            return 'medium', f'starts-with after dropping "{prefix}"'
    return 'low', 'search hit only'


def search_terms(slug):
    words = [w for w in re.split(r'[\-_]+', slug) if w]
    terms = [' '.join(words)]
    for drop in range(1, min(3, len(words))):  # company prefixes are 1-2 words
        terms.append(' '.join(words[drop:]))
    return terms


def best_candidate(slug):
    ranked = {'high': 0, 'medium': 1, 'low': 2}
    best = None
    for term in search_terms(slug):
        resp = get(f'{API}/robots/robots/', lite=1, status='published', sc=term, page_size=10)
        if resp.status_code != 200:
            continue
        for row in resp.json().get('results', []):
            result = score(slug, row)
            if result and (best is None or ranked[result[0]] < ranked[best[0]]):
                best = (result[0], result[1], row)
        if best and best[0] == 'high':
            break
    return best


def main(in_path, out_path):
    slugs = read_slugs(in_path)
    rows = []
    for index, slug in enumerate(slugs, 1):
        resp = get(f'{API}/robots/robots/{slug}/')
        if resp.status_code == 200:
            data = resp.json()
            rows.append([slug, 'resolves', data.get('id'), data.get('name'), company_name(data), '', 'current name already matches'])
        else:
            found = best_candidate(slug)
            if found:
                confidence, reason, row = found
                rows.append([slug, 'candidate', row.get('id'), row.get('name'), company_name(row), confidence, reason])
            else:
                rows.append([slug, 'none', '', '', '', '', 'no plausible match; leave as 404'])
        print(f'[{index}/{len(slugs)}] {slug}: {rows[-1][1]} {rows[-1][5]} {rows[-1][3] or ""}', flush=True)
    with open(out_path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['old_slug', 'status', 'robot_id', 'robot_name', 'company', 'confidence', 'reason'])
        writer.writerows(rows)
    counts = {}
    for row in rows:
        label = row[1] + (f'/{row[5]}' if row[5] else '')
        counts[label] = counts.get(label, 0) + 1
    print('summary:', counts)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
