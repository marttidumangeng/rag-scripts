r"""Fill description + pinned card image for the /browse/types cards that have neither.

2026-09-07: trimmed from 8 slugs to 4 — the 2026-08-26 taxonomy dedupe (47 -> 29
facets) removed logistics-robots, underwater-robot, home-robots and exoskeletons
as robot categories. The survivors still missing both description and image are
exactly: robotic-arms, cleaning-robots, educational-robots, military.

Run from Git Bash against a prod app pod:

    sed '1s/^\xEF\xBB\xBF//' scripts/fix_category_cards.py \
      | kubectl exec -i <pod> -n <ns> -- \
        python manage.py shell -c 'import sys; exec(sys.stdin.buffer.read().decode("utf-8"))'

Three things in that line are load-bearing, all learned the hard way:
  * sed strips the BOM PowerShell adds; manage.py shell chokes on it.
  * `shell -c 'exec(...)'` rather than a bare `shell`: piping into the bare shell
    runs the REPL, which treats the blank line inside every function and
    for-block as end-of-block and dies with IndentationError.
  * .buffer.read().decode("utf-8") rather than sys.stdin.read(): on Windows the
    text-mode pipe mangles the zh-CN/zh-TW strings into surrogates and raises
    UnicodeEncodeError before a single row is touched.

Dry run by default - it prints exactly what it would change and touches nothing.
Re-run with CATEGORY_FIX_APPLY=1 in the pod's env to write.

Convention comes from the 2026-07-19 / 2026-07-30 passes:
  Category.image = 'categories/<slug>.jpg', sourced by reading an existing robot
  photo straight out of default_storage (same bucket, no download), compositing
  alpha onto white, cropping to a landscape card framing, and saving JPEG q85 at
  <= 1280 px wide. Never upscale: several sources are smaller than 1280 and a
  blown-up JPEG looks worse on the card than a sharp 730 px one.

Each source photo below was opened and looked at before being chosen. Do not
swap one out for "the newest robot's photo" without looking at it first — that
fallback is how banner art and staff headshots got onto cards before.
"""
import io
import os

from django.core.files.storage import default_storage
from PIL import Image

from interactions.models import Category, CategoryTranslation
from interactions.cache_utils import bust_category_list_cache

APPLY = os.environ.get('CATEGORY_FIX_APPLY') == '1'

MAX_WIDTH = 1280
JPEG_QUALITY = 85

# slug -> everything needed to build the card.
#   source: storage key of a robot photo (verified to exist + eyeballed)
#   robot:  which robot it came from, for the audit trail
#   crop:   (left, top, right, bottom) as fractions of the source, or None for full frame
FIXES = {
    'robotic-arms': {
        'robot': '7134 Flexiv Enlight L',
        'source': 'research-staging/flexiv/7134-enlight-l-hero.jpg',
        'crop': (0.35, 0.25, 1.00, 0.60),  # arm sits top-right of a tall studio frame
        'en': 'Articulated multi-axis manipulators, from benchtop units to long-reach industrial arms.',
        'zh-CN': '多轴关节机械臂，涵盖桌面型到长臂工业机型。',
        'zh-TW': '多軸關節機械臂，涵蓋桌面型到長臂工業機型。',
    },
    'cleaning-robots': {
        'robot': '2679 Avidbots Neo 2W',
        'source': 'research-staging/avidbots/neo-2w-studio-hero.jpg',
        'crop': None,
        'en': 'Floor scrubbers, sweepers, and disinfection robots that keep floors and surfaces clean.',
        'zh-CN': '洗地机、扫地机和消毒机器人，负责地面与表面清洁。',
        'zh-TW': '洗地機、掃地機和消毒機器人，負責地面與表面清潔。',
    },
    'educational-robots': {
        'robot': '5322 Makeblock mBot Ranger',
        'source': 'robots/original/robot-5322-mbot-ranger-v1784209001.webp',
        'crop': (0.04, 0.02, 0.96, 0.58),  # keep the top build; drop the 2-up row beneath
        'en': 'Programmable STEM kits and classroom robots for teaching coding and robotics.',
        'zh-CN': '可编程 STEM 套件与课堂机器人，用于教授编程和机器人技术。',
        'zh-TW': '可程式化 STEM 套件與課堂機器人，用於教授程式設計和機器人技術。',
    },
    'military': {
        'robot': '6548 Shark Robotics Atrax',
        'source': 'robots/original/robot-6548-atrax-demining-robot-v1785468054.webp',
        'crop': None,
        'en': 'Uncrewed ground and air systems for reconnaissance, demining, and ordnance disposal.',
        'zh-CN': '用于侦察、排雷和爆炸物处理的无人地面与空中系统。',
        'zh-TW': '用於偵察、排雷和爆裂物處理的無人地面與空中系統。',
    },
}


def build_card_jpeg(source_key, crop):
    """Read a robot photo out of storage and return (jpeg_bytes, (w, h))."""
    with default_storage.open(source_key, 'rb') as fh:
        img = Image.open(fh)
        img.load()

    # Composite alpha onto white — several sources are cut-outs and would
    # otherwise flatten to black.
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGBA')
        canvas = Image.new('RGB', img.size, (255, 255, 255))
        canvas.paste(img, mask=img.split()[-1])
        img = canvas
    else:
        img = img.convert('RGB')

    if crop:
        w, h = img.size
        left, top, right, bottom = crop
        img = img.crop((int(w * left), int(h * top), int(w * right), int(h * bottom)))

    if img.width > MAX_WIDTH:  # downscale only
        img = img.resize((MAX_WIDTH, round(img.height * MAX_WIDTH / img.width)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=JPEG_QUALITY, optimize=True)
    return buf.getvalue(), img.size


slugs = sorted(FIXES)
cats = {c.slug: c for c in Category.objects.filter(slug__in=slugs, content_type='robot')}

# --- guards -----------------------------------------------------------------
missing = [s for s in slugs if s not in cats]
assert not missing, f'categories not found: {missing}'
assert len(cats) == len(FIXES), f'expected {len(FIXES)} categories, matched {len(cats)}'

# Refuse to clobber anything that has since been filled in by hand.
occupied = [c.slug for c in cats.values() if (c.description or '').strip() or c.image]
assert not occupied, (
    f'these already have a description or image, refusing to overwrite: {occupied}. '
    'Drop them from FIXES and re-run if that is expected.'
)

for slug, spec in FIXES.items():
    assert default_storage.exists(spec['source']), f'{slug}: missing source photo {spec["source"]}'

# --- snapshot before mutating -----------------------------------------------
print('=== BEFORE ===')
for slug in slugs:
    c = cats[slug]
    print(f'  {c.id:>4}  {slug:<20} desc={(c.description or "")!r:<4} image={c.image.name or None!r}')
print()

# --- apply ------------------------------------------------------------------
print('=== %s ===' % ('APPLYING' if APPLY else 'DRY RUN (set CATEGORY_FIX_APPLY=1 to write)'))
for slug in slugs:
    cat = cats[slug]
    spec = FIXES[slug]
    jpeg, size = build_card_jpeg(spec['source'], spec['crop'])
    key = f'categories/{slug}.jpg'

    print(f'  {slug:<20} <- {spec["robot"]:<32} {size[0]}x{size[1]}  {len(jpeg) // 1024} KB  -> {key}')
    print(f'  {"":<20}    "{spec["en"]}"')

    if not APPLY:
        continue

    if default_storage.exists(key):
        default_storage.delete(key)
    default_storage.save(key, io.BytesIO(jpeg))

    cat.description = spec['en']
    cat.image.name = key
    cat.save(update_fields=['description', 'image', 'updated_at'])

    for locale in ('zh-CN', 'zh-TW'):
        CategoryTranslation.objects.update_or_create(
            category=cat,
            locale=locale,
            defaults={
                'name': cat.name,
                'description': spec[locale],
                'translation_status': 'completed',
            },
        )

if APPLY:
    bust_category_list_cache()
    print('\ncache busted; browsers still hold max-age=300 for up to 5 min')
    print('\n=== AFTER ===')
    for cat in Category.objects.filter(slug__in=slugs).order_by('slug'):
        locales = sorted(cat.translations.values_list('locale', flat=True))
        print(f'  {cat.id:>4}  {cat.slug:<20} image={cat.image.name}  locales={locales}')
        print(f'  {"":<4}  {"":<20} {cat.description}')
else:
    print('\nnothing written')
