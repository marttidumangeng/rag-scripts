"""Find prod companies with 0 robots, ranked has-website first."""
import json, time
from api_client import ResearchApiClient

c = ResearchApiClient()

# 1. All companies (light-ish)
companies = {}
page = 1
while True:
    data = c._get('companies/', params={'page': page, 'page_size': 100, 'ordering': 'name'})
    for co in data.get('results', []):
        companies[co['id']] = {
            'id': co['id'],
            'name': co['name'],
            'slug': co['slug'],
            'website': (co.get('website') or '').strip(),
            'country': (co.get('country') or {}).get('name') if co.get('country') else None,
            'source_locale': co.get('source_locale'),
        }
    if not data.get('next'):
        break
    page += 1
print(f"companies total: {len(companies)}")

# 2. Company ids that HAVE robots (page robots endpoint at modest size w/ retry)
have = {}
page = 1
while True:
    for attempt in range(5):
        try:
            data = c._get('robots/robots/', params={'page': page, 'page_size': 50})
            break
        except Exception as e:
            print(f"  page {page} attempt {attempt} err {e}")
            time.sleep(2 ** attempt)
    else:
        raise SystemExit(f"failed page {page}")
    for r in data.get('results', []):
        cid = None
        cr = r.get('company_ref')
        if isinstance(cr, dict):
            cid = cr.get('id')
        if cid is None:
            comp = r.get('company')
            # company may be name only; try match later
        if cid is not None:
            have[cid] = have.get(cid, 0) + 1
    if page % 10 == 0:
        print(f"  robots page {page}, distinct companies-with-robots so far: {len(have)}")
    if not data.get('next'):
        break
    page += 1
print(f"companies WITH robots: {len(have)}")

# 3. Zero-robot companies
zero = [co for cid, co in companies.items() if have.get(cid, 0) == 0]
zero_web = [co for co in zero if co['website']]
zero_noweb = [co for co in zero if not co['website']]
print(f"ZERO-robot companies: {len(zero)}  (with website: {len(zero_web)}, no website: {len(zero_noweb)})")

out = {
    'have_counts': have,
    'zero_with_website': sorted(zero_web, key=lambda x: x['name'].lower()),
    'zero_no_website': sorted(zero_noweb, key=lambda x: x['name'].lower()),
}
with open('zero_robot_report.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print("wrote zero_robot_report.json")
print("\n--- ZERO-robot WITH website ---")
for co in out['zero_with_website']:
    print(f"  {co['id']:>5}  {co['name'][:45]:<45}  {co['website'][:50]}")
