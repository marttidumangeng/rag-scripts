import csv, os

FIXES = {
    'Peking University': ('https://www.ai.pku.edu.cn/', 'PKU Institute for AI homepage lists dated news items (Chinese); no stable subpage'),
    'Bristol Robotics Laboratory': ('https://www.bristolroboticslab.com/about-us', 'BRL site has no dedicated news page; monitor UWE/Bristol Uni news + BRL LinkedIn for announcements'),
    'EPFL Robotics': ('https://actu.epfl.ch/', 'Filter robotics topic on EPFL news portal; search route: actu.epfl.ch + robotics keyword'),
    'ETH Zurich Robotic Systems Lab (RSL)': ('https://rsl.ethz.ch/', 'RSL homepage carries dated news items; also ethz.ch/en/news-and-events'),
}

for fn in sorted(os.listdir('/home/ubuntu/rai_registry/regions')):
    if not fn.endswith('.csv'):
        continue
    path = f'/home/ubuntu/rai_registry/regions/{fn}'
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = []
        for row in reader:
            row.pop(None, None)
            rows.append({k: v for k, v in row.items() if k in fields})
    changed = 0
    for row in rows:
        name = (row.get('source_name') or '').strip()
        for key, (url, note) in FIXES.items():
            if key in name and row.get('url_news') != url:
                row['url_news'] = url
                if note:
                    row['notes'] = ((row.get('notes') or '').rstrip('. ') + '. ' + note).strip('. ') + '.'
                changed += 1
                break
    if changed:
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(fn, 'fixed', changed)
print('done')
