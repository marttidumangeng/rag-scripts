import re, os, csv

slugs = {}
for fn in os.listdir('/home/ubuntu/rai_registry/site_pages'):
    text = open(f'/home/ubuntu/rai_registry/site_pages/{fn}', encoding='utf-8').read()
    for m in re.finditer(r'robotaigeek\.com/browse/companies/([a-z0-9-]+)', text):
        slugs.setdefault(m.group(1), fn)
    # capture external "Visit Website" links near company names
print('unique company slugs captured:', len(slugs))
with open('/home/ubuntu/rai_registry/company_slugs.txt', 'w') as f:
    for s in sorted(slugs):
        f.write(s + '\n')
