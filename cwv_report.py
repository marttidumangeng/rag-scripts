"""Read-only p75 Core Web Vitals report from CwvBeaconEvent (real-user beacons).

Run inside the Django shell on prod, e.g. from PowerShell:

  Get-Content -Raw scripts\\cwv_report.py | kubectl --context=gke_robotaigeek-core_asia-southeast1_rag-cluster-prod exec -i -n rag-server-prod <web-pod> -c django-app -- python manage.py shell

Prints, per metric and page group over the last DAYS days: sample count, p50,
p75, p95 and the share of samples in Google's "good" band. Writes nothing.
LCP/INP are milliseconds, CLS is unitless, LONG_TASK is the aggregate beacon.
"""
import re
from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from tools.models import CwvBeaconEvent

DAYS = 14
GOOD = {'LCP': 2500, 'INP': 200, 'CLS': 0.1}
POOR = {'LCP': 4000, 'INP': 500, 'CLS': 0.25}


def group(path):
    path = (path or '/').split('?')[0]
    for pattern, name in (
        (r'^/robot/[^/]+/?$', '/robot/<slug>'),
        (r'^/browse/robots/?$', '/browse/robots'),
        (r'^/browse/companies/[^/]+/?$', '/browse/companies/<slug>'),
        (r'^/browse/companies/?$', '/browse/companies'),
        (r'^/videos/[^/]+/?$', '/videos/<slug>'),
        (r'^/news/.+$', '/news/*'),
        (r'^/articles/.+$', '/articles/*'),
        (r'^/ai-robotics/.+$', '/ai-robotics/*'),
        (r'^/alternatives/.+$', '/alternatives/<slug>'),
        (r'^/compare', '/compare*'),
    ):
        if re.match(pattern, path):
            return name
    return path if len(path) < 40 else path[:40]


def pct(values, p):
    values = sorted(values)
    if not values:
        return None
    k = (len(values) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


since = timezone.now() - timedelta(days=DAYS)
rows = CwvBeaconEvent.objects.filter(received_at__gte=since).values_list('metric', 'path', 'value')
buckets = defaultdict(list)
total = 0
for metric, path, value in rows.iterator():
    buckets[(metric, group(path))].append(value)
    total += 1

print(f'CWV beacons, last {DAYS} days: {total} samples')
for metric in ('LCP', 'INP', 'CLS', 'LONG_TASK'):
    items = [(g, v) for (m, g), v in buckets.items() if m == metric]
    if not items:
        print(f'\n{metric}: no samples')
        continue
    allv = [x for _, v in items for x in v]
    print(f'\n{metric}  all pages: n={len(allv)} p75={pct(allv, .75):.3g} p95={pct(allv, .95):.3g}')
    for g, v in sorted(items, key=lambda kv: -len(kv[1]))[:12]:
        good = ''
        if metric in GOOD:
            share = sum(1 for x in v if x <= GOOD[metric]) / len(v)
            poor = sum(1 for x in v if x > POOR[metric]) / len(v)
            good = f' good={share:.0%} poor={poor:.0%}'
        print(f'  {g:<34} n={len(v):<5} p50={pct(v, .5):<8.3g} p75={pct(v, .75):<8.3g} p95={pct(v, .95):<8.3g}{good}')


# --- LCP element attribution (only beacons sent after the element-recording
# change in plugins/web-vitals.client.ts carry this metadata) -----------------
def element_key(meta):
    tag = meta.get('lcpTag') or '?'
    url = meta.get('lcpUrl') or ''
    if url:
        # cdn host + first two path segments, e.g. cdn.robotaigeek.com/robots/thumb
        parts = url.split('/')
        url = '/'.join(parts[2:5]) if len(parts) > 4 else url[:60]
    return f'{tag} {url}'.strip()


elem = defaultdict(list)
ttfb = defaultdict(list)
with_meta = 0
for path, value, meta in CwvBeaconEvent.objects.filter(
        metric='LCP', received_at__gte=since).values_list('path', 'value', 'metadata').iterator():
    if not isinstance(meta, dict) or 'lcpTag' not in meta:
        continue
    with_meta += 1
    elem[(group(path), element_key(meta))].append(value)
    if meta.get('ttfbMs') is not None:
        ttfb[group(path)].append(meta['ttfbMs'])

print(f'\nLCP beacons with element data: {with_meta}')
if with_meta:
    print('TTFB p75 by page (ms):')
    for g, v in sorted(ttfb.items(), key=lambda kv: -len(kv[1]))[:10]:
        print(f'  {g:<34} n={len(v):<5} ttfb p75={pct(v, .75):.0f}')
    print('LCP element by page (most common first):')
    for (g, k), v in sorted(elem.items(), key=lambda kv: -len(kv[1]))[:20]:
        print(f'  {g:<28} {k:<60} n={len(v):<4} p75={pct(v, .75):.0f}ms')
