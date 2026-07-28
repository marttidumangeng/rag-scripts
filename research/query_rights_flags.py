"""
query_rights_flags.py
----------------------
Runs via: python manage.py shell < query_rights_flags.py
from the robotaigeek-server directory.

Queries RobotPhoto for rights_status='review_required' and groups by company.
"""
import json
from collections import defaultdict
from robots.models import RobotPhoto

flagged = RobotPhoto.objects.filter(
    rights_status='review_required',
    deleted=False,
).select_related('robot__company_ref').order_by('robot__company_ref__name', 'robot__name')

by_company = defaultdict(list)
for photo in flagged:
    robot = photo.robot
    company_name = robot.company_ref.name if robot.company_ref else 'Unknown'
    by_company[company_name].append({
        'robot_id': robot.id,
        'robot_name': robot.name,
        'photo_id': photo.id,
        'image_url': photo.url or '',
        'source_tier': photo.source_tier,
    })

print(f"\nTotal photos with rights_status=review_required: {flagged.count()}")
print(f"Unique robots: {flagged.values('robot').distinct().count()}")
print(f"Companies affected: {len(by_company)}\n")
print(f"{'Company':<50} {'Robots':>7}")
print('-' * 59)
for company, photos in sorted(by_company.items(), key=lambda x: -len(x[1])):
    unique_robots = len({p['robot_id'] for p in photos})
    print(f"{company:<50} {unique_robots:>7}")

print('\nFull breakdown:')
for company, photos in sorted(by_company.items(), key=lambda x: -len(x[1])):
    print(f'\n  {company}:')
    seen = set()
    for p in photos:
        if p['robot_id'] not in seen:
            seen.add(p['robot_id'])
            print(f"    - [{p['robot_id']}] {p['robot_name']}")
