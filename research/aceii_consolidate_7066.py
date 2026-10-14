"""Consolidate company 1325 (Aceii) onto robot 7066 without touching its
DATA_VERIFICATION_CORE_FIELDS (so maker_confirmed_at survives).

Dry-run by default; APPLY=1 in the environment (read from the first stdin
line marker below) performs the writes. Every step asserts the expected row
count before mutating, and prints a full before-snapshot as JSON.
"""
import json, os, sys
from django.utils import timezone
from django.db import transaction
from robots.models import Robot, RobotPhoto, RobotVideo, RobotInformationSource, RobotStatus
from videos.models import Video
from django.contrib.auth import get_user_model

APPLY = os.environ.get('ACEII_APPLY') == '1'
KEEP, DUPE, ACC = 7066, 620, 1483
COMPANY = 1325
PRODUCT_PAGE = 'https://aceiilab.com/pages/aceiilab_a1'

keep = Robot.objects.get(pk=KEEP); dupe = Robot.objects.get(pk=DUPE); acc = Robot.objects.get(pk=ACC)
# --- scope gates: every row belongs to the named company and is what we think it is
for r, nm in ((keep, 'AceiiLab'), (dupe, 'ACEiiLab A1 AI Tennis Robot'), (acc, 'Portable Battery')):
    assert r.company_ref_id == COMPANY, (r.pk, r.company_ref_id)
    assert r.name == nm, (r.pk, r.name)
assert keep.maker_confirmed_at is not None, 'keep row is not maker-confirmed?!'
assert keep.status == RobotStatus.PUBLISHED and dupe.status == RobotStatus.PUBLISHED and acc.status == RobotStatus.PUBLISHED

def snap_robot(r):
    return {k: (str(getattr(r, k)) if getattr(r, k) is not None else None) for k in
            ('id', 'name', 'status', 'image', 'url', 'maker_confirmed_at', 'rejection_reason',
             'rejection_categories', 'auto_fix_status', 'reviewed_at', 'reviewed_by_id', 'quality_flags')}

photos = list(RobotPhoto.objects.filter(robot_id__in=[DUPE, ACC], deleted=False).order_by('robot_id', 'order', 'id'))
videos = list(RobotVideo.objects.filter(robot_id__in=[DUPE, ACC], deleted=False).order_by('robot_id', 'order', 'id'))
lib_videos = list(Video.objects.filter(robot_id__in=[DUPE, ACC]).order_by('id'))
mention_videos = list(Video.objects.filter(mentioned_robots__in=[DUPE, ACC]).distinct().order_by('id'))
keep_photos = RobotPhoto.objects.filter(robot_id=KEEP, deleted=False).count()
keep_videos = RobotVideo.objects.filter(robot_id=KEEP, deleted=False).count()
keep_sources = list(RobotInformationSource.objects.filter(robot_id=KEEP, deleted=False).values('id', 'url'))

snapshot = {
    'robots': [snap_robot(keep), snap_robot(dupe), snap_robot(acc)],
    'photos': [{'id': p.id, 'robot_id': p.robot_id, 'url': p.url, 's3_image': str(p.s3_image), 'is_primary': p.is_primary,
                'order': p.order, 'status': p.status} for p in photos],
    'videos': [{'id': v.id, 'robot_id': v.robot_id, 'url': v.url, 'title': v.title, 'is_primary': v.is_primary, 'order': v.order} for v in videos],
    'library_videos': [{'id': v.id, 'robot_id': v.robot_id, 'title': v.title} for v in lib_videos],
    'mention_videos': [{'id': v.id, 'mentioned': list(v.mentioned_robots.values_list('id', flat=True))} for v in mention_videos],
    'keep_counts_before': {'photos': keep_photos, 'videos': keep_videos, 'sources': keep_sources},
}
print('SNAPSHOT_JSON ' + json.dumps(snapshot, ensure_ascii=False, default=str))

# --- expected-count gates (from the API reads on 2026-08-23)
by_robot = lambda rows, rid: [x for x in rows if x.robot_id == rid]
assert len(by_robot(photos, DUPE)) == 6, len(by_robot(photos, DUPE))
assert len(by_robot(photos, ACC)) == 9, len(by_robot(photos, ACC))
assert len(by_robot(videos, DUPE)) == 2, len(by_robot(videos, DUPE))
assert len(by_robot(videos, ACC)) == 4, len(by_robot(videos, ACC))
assert sorted(v.id for v in lib_videos) == [826, 827, 828, 829, 929, 930, 6355], [v.id for v in lib_videos]
assert keep_photos == 0 and keep_videos == 0 and keep_sources == [], (keep_photos, keep_videos, keep_sources)
assert not RobotVideo.objects.filter(robot_id=KEEP, url__in=[v.url for v in videos]).exists()
print(f'GATES OK — will move {len(photos)} photos, {len(videos)} videos, {len(lib_videos)} library videos, '
      f'{len(mention_videos)} mention links; add 1 source; reject {DUPE} + {ACC}')

if not APPLY:
    print('DRY RUN — nothing written'); sys.exit(0)

martti = get_user_model().objects.get(pk=1)
now = timezone.now()
with transaction.atomic():
    # 1. product page as information source (not a core field -> maker stamp survives)
    src = RobotInformationSource.objects.create(robot_id=KEEP, url=PRODUCT_PAGE, source_type='website',
                                                title='AceiiLab A1 product page', order=0)
    # 2. photos -> 7066; none primary (7066 keeps its own hero in Robot.image); sequential order
    for i, p in enumerate(photos):
        RobotPhoto.objects.filter(pk=p.pk).update(robot_id=KEEP, is_primary=False, order=i)
    # 3. videos -> 7066; 3732 stays the single primary
    for i, v in enumerate(videos):
        RobotVideo.objects.filter(pk=v.pk).update(robot_id=KEEP, is_primary=(v.pk == 3732), order=i)
    # 4. video library rows + mention M2M
    Video.objects.filter(pk__in=[v.pk for v in lib_videos]).update(robot_id=KEEP)
    for v in mention_videos:
        v.mentioned_robots.remove(DUPE, ACC); v.mentioned_robots.add(KEEP)
    # 5. reject the duplicate and the accessory; escalated = human decision, fix loop must not touch
    for r, reason, cats in (
        (dupe, f'Duplicate of robot {KEEP} (AceiiLab A1); photos and videos moved to {KEEP} on 2026-08-23.', ['duplicate']),
        (acc, f'Accessory (removable battery pack for the AceiiLab A1), not a robot; its A1 photos/videos moved to {KEEP} on 2026-08-23.', ['other', 'wrong_image']),
    ):
        r.status = RobotStatus.REJECTED; r.reviewed_by = martti; r.reviewed_at = now
        r.rejection_reason = reason; r.rejection_categories = cats; r.auto_fix_status = 'escalated'
        r.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason', 'rejection_categories', 'auto_fix_status'])

# --- post-write verification, read back fresh
keep.refresh_from_db(); dupe.refresh_from_db(); acc.refresh_from_db()
print('AFTER', json.dumps({
    'keep': {'status': keep.status, 'maker_confirmed_at': str(keep.maker_confirmed_at), 'verification_status': keep.data_verification_status,
             'photos': RobotPhoto.objects.filter(robot_id=KEEP, deleted=False).count(),
             'videos': RobotVideo.objects.filter(robot_id=KEEP, deleted=False).count(),
             'primary_videos': list(RobotVideo.objects.filter(robot_id=KEEP, is_primary=True).values_list('id', flat=True)),
             'sources': list(RobotInformationSource.objects.filter(robot_id=KEEP, deleted=False).values_list('url', flat=True)),
             'library_videos': list(Video.objects.filter(robot_id=KEEP).values_list('id', flat=True)),
             'image': keep.image},
    'dupe': {'status': dupe.status, 'auto_fix': dupe.auto_fix_status, 'photos_left': RobotPhoto.objects.filter(robot_id=DUPE, deleted=False).count()},
    'acc': {'status': acc.status, 'auto_fix': acc.auto_fix_status, 'photos_left': RobotPhoto.objects.filter(robot_id=ACC, deleted=False).count()},
}, default=str))
