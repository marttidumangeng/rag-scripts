import csv

path = '/home/ubuntu/rai_registry/regions/International_sources_csv.csv'
with open(path, newline='', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    fields = [fn for fn in reader.fieldnames if fn]
    rows = []
    for row in reader:
        row.pop(None, None)
        rows.append({k: (row.get(k) or '') for k in fields})

FIXES = {
    'Hannover Messe': ('https://www.hannovermesse.de/en/press/press-releases/hannover-messe/press-releases', ''),
    'World Bank': ('https://www.worldbank.org/en/news', ''),
}
changed = 0
for row in rows:
    for key, (url, note) in FIXES.items():
        if key.lower() in row['source_name'].lower() and row['url_news'] != url:
            row['url_news'] = url
            changed += 1

with open(path, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
print('rows:', len(rows), 'changed:', changed)
