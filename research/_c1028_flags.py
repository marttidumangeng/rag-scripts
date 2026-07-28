import sys
from robots.models import Robot
from robots.quality import robot_quality_flags
from django.db.models import Count
qs = Robot.objects.filter(company_id=1028, status='pending_review').annotate(
    n_categories=Count('categories',distinct=True), n_uses=Count('uses',distinct=True),
    n_tags=Count('tags',distinct=True), n_industries=Count('industries',distinct=True),
    n_movement_types=Count('movement_types',distinct=True)).order_by('id')
from collections import Counter
allflags=Counter()
web='https://www.noblelift.com'
for r in qs:
    fl=[f['flag'] for f in robot_quality_flags(r, company_website=web, active_photo_count=r.photos.count(), active_video_count=r.videos.count())]
    for f in fl: allflags[f]+=1
    extra=[f for f in fl if f not in ('missing_price','missing_release_year')]
    if extra:
        print(r.id, r.name[:34].ljust(35), extra)
print('\nFLAG TOTALS across', qs.count(), 'robots:')
for f,n in allflags.most_common():
    print(' ', f, n)
