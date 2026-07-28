"""Find prod companies with 0 robots, resilient to prod 500/502s.

Pages the robots endpoint at a larger page_size, SKIPS failed pages instead of
aborting (a skipped page can only cause a false 'zero' for a company whose
robots all sit on that page — candidates get re-checked individually before use),
and writes an incremental report.
"""
import json
import time

from api_client import ResearchApiClient

c = ResearchApiClient()

# 1. All companies
companies = {}
page = 1
while True:
    for attempt in range(5):
        try:
            data = c._get('companies/', params={'page': page, 'page_size': 100, 'ordering': 'name'})
            break
        except Exception as e:
            print(f"  companies page {page} attempt {attempt} err {e}", flush=True)
            time.sleep(2 ** attempt)
    else:
        print(f"  companies page {page} permanently failed, stopping company scan", flush=True)
        break
    for co in data.get('results', []):
        companies[co['id']] = {
            'id': co['id'], 'name': co['name'], 'slug': co['slug'],
            'website': (co.get('website') or '').strip(),
            'country': (co.get('country') or {}).get('name') if co.get('country') else None,
            'source_locale': co.get('source_locale'),
        }
    if not data.get('next'):
        break
    page += 1
print(f"companies total: {len(companies)}", flush=True)

# 2. Company ids that HAVE robots — skip failed pages, don't abort
have = {}
skipped_pages = []
page = 1
PAGE_SIZE = 100
while True:
    ok = False
    data = None
    for attempt in range(6):
        try:
            data = c._get('robots/robots/', params={'page': page, 'page_size': PAGE_SIZE})
            ok = True
            break
        except Exception as e:
            time.sleep(1.5 * (attempt + 1))
    if not ok:
        skipped_pages.append(page)
        print(f"  robots page {page} SKIPPED after retries", flush=True)
        # We can't know 'next' for a skipped page; assume more remain up to a cap.
        page += 1
        if page > 120:
            break
        continue
    for r in data.get('results', []):
        cr = r.get('company_ref')
        cid = cr.get('id') if isinstance(cr, dict) else None
        if cid is not None:
            have[cid] = have.get(cid, 0) + 1
    if page % 10 == 0:
        print(f"  robots page {page}, companies-with-robots so far: {len(have)}", flush=True)
    if not data.get('next'):
        break
    page += 1
    time.sleep(0.2)  # be gentle on prod
print(f"companies WITH robots: {len(have)} | skipped pages: {skipped_pages}", flush=True)

# 3. Zero-robot companies
zero = [co for cid, co in companies.items() if have.get(cid, 0) == 0]
zero_web = sorted([co for co in zero if co['website']], key=lambda x: x['name'].lower())
zero_noweb = sorted([co for co in zero if not co['website']], key=lambda x: x['name'].lower())
print(f"ZERO-robot companies: {len(zero)}  (with website: {len(zero_web)}, no website: {len(zero_noweb)})", flush=True)

with open('zero_robot_report.json', 'w', encoding='utf-8') as f:
    json.dump({'have_counts': have, 'skipped_pages': skipped_pages,
               'zero_with_website': zero_web, 'zero_no_website': zero_noweb}, f, indent=2, ensure_ascii=False)
print("wrote zero_robot_report.json", flush=True)
print("\n--- ZERO-robot WITH website (en locale first) ---", flush=True)
for co in sorted(zero_web, key=lambda x: (x.get('source_locale') != 'en', x['name'].lower())):
    print(f"  {co['id']:>5}  loc={str(co.get('source_locale')):<5} {co['name'][:42]:<42}  {co['website'][:48]}", flush=True)
