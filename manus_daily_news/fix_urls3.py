import csv, os

FIXES = {
    # China
    'CAA': ('http://www.caa.org.cn/index.php?me_id=2', 'HTTP-only site; intermittent from overseas; use CN proxy or cached scrape'),
    'National Local Joint Humanoid Robot Innovation Center': ('https://mp.weixin.qq.com/ (search 国地共建人形机器人创新中心)', 'Primary channel is official WeChat account 国地共建人形机器人创新中心 (OpenLoong); website unstable overseas. Also openloong.org.cn for open-source releases'),
    'Peking University': ('https://www.ai.pku.edu.cn/xwdt/xwjrd.htm', 'PKU Institute for AI news list (Chinese)'),
    # Europe
    '1X Technologies': ('https://www.1x.tech/discover', '1X posts news under Discover'),
    'ABB Robotics': ('https://new.abb.com/news', 'Filter robotics tag; global ABB press hub'),
    'Bristol Robotics Laboratory': ('https://www.bristolroboticslab.com/whats-happening', ''),
    'EPFL Robotics': ('https://news.epfl.ch/search/?q=robotics', 'EPFL news search route'),
    'ETH Zurich Robotic Systems Lab (RSL)': ('https://rsl.ethz.ch/news.html', 'Also ethz.ch/en/news-and-events for university-wide robotics news'),
    'TU Delft Robotics Institute': ('https://www.tudelft.nl/en/stories', 'Institute page reorganized; use TU Delft stories/news and 3mE dept news; filter robotics'),
    'TU Munich MIRMI': ('https://www.mirmi.tum.de/en/mirmi/news/', ''),
    'UK AISI (AI Safety Institute)': ('https://www.aisi.gov.uk/blog', 'AISI publishes via blog and research pages'),
    'UKRI EPSRC': ('https://www.ukri.org/news/?filter_council%5B%5D=814&filter_order=publication_date-desc', 'EPSRC-filtered UKRI news'),
    # HK
    'XPeng Investor Relations': ('https://ir.xiaopeng.com/news-releases', 'JS-heavy IR site; blocks HEAD/bots; works in browser. Alternative: HKEXnews filings for 9868.HK'),
    # US
    'Intuitive Surgical IR': ('https://isrg.intuitive.com/news-releases', 'Q4/notified IR platform sometimes blocks bots; works in browser'),
    'Serve Robotics IR': ('https://investors.serverobotics.com/news', 'IR platform blocks bots; works in browser'),
    'Symbotic IR': ('https://ir.symbotic.com/news-releases', 'IR platform blocks bots; works in browser'),
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
            match = (name == key) or (key in name and len(key) > 4)
            if key == 'CAA':
                match = name == 'CAA'
            if match and row.get('url_news') != url:
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
