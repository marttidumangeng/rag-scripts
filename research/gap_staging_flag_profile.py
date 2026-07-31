#!/usr/bin/env python3
"""Profile the gap-discovery staging set against production quality flags.

Answers one question before anything is imported: if we pushed the staged
companies and robots to prod today, what would the content queue look like?

The flag vocabulary mirrors the names used by the server-side quality audit and
the remedy registry (missing_specs, missing_image, missing_category, ...), so
the counts here are directly comparable to what reviewers see in the queue.

No production access required — this reads the staging file only.

Usage:
  python gap_staging_flag_profile.py
  python gap_staging_flag_profile.py --include-imported     # don't skip the ledger
  python gap_staging_flag_profile.py --top-companies 25
  python gap_staging_flag_profile.py --json out/profile.json
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

# Windows consoles default to cp1252, which cannot encode the em dashes in this
# output or the 50+ non-ASCII company names in the staging set. Force UTF-8 so
# the script works without PYTHONIOENCODING being set by the caller.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):  # non-reconfigurable stream (pipe, IDE)
        pass

DEFAULT_STAGING = (
    pathlib.Path(__file__).parent / 'staging' / 'gap_discovery' / 'staged_import.json'
)

# Any one of these present means the robot has at least one real spec value.
SPEC_FIELDS = (
    'payload_kg', 'reach_mm', 'weight_kg', 'dof', 'speed_ms', 'runtime_minutes',
    'battery_wh', 'repeatability_mm', 'height_mm', 'width_mm', 'length_mm',
    'joint_torque_nm', 'charging_time_minutes', 'ip_rating', 'voltage',
)


def blank(value) -> bool:
    """Staged records use '', None, [] and {} interchangeably for 'absent'."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def robot_flags(robot: dict) -> list[str]:
    flags = []

    if blank(robot.get('image')) and blank(robot.get('images')):
        flags.append('missing_image')
    if all(blank(robot.get(f)) for f in SPEC_FIELDS):
        flags.append('missing_specs')
    if blank(robot.get('description')):
        flags.append('missing_description')
    if blank(robot.get('category_slugs')) and blank(robot.get('sub_category_slug')):
        flags.append('missing_category')
    if blank(robot.get('purpose')):
        flags.append('missing_purpose')
    if blank(robot.get('features')):
        flags.append('missing_features')
    if blank(robot.get('tags')):
        flags.append('missing_tags')
    if blank(robot.get('price_min')) and blank(robot.get('price_max')) and blank(robot.get('price_range')):
        flags.append('missing_price')
    if blank(robot.get('release_year')):
        flags.append('missing_release_year')
    if blank(robot.get('sources')) and blank(robot.get('url')):
        flags.append('missing_source_url')
    if blank(robot.get('manufacturer_country_code')) and blank(robot.get('manufacturer_country_codes')):
        flags.append('missing_manufacturer_country')
    if blank(robot.get('video_urls')):
        flags.append('missing_video')
    if blank(robot.get('family_key')):
        flags.append('missing_family')
    if blank(robot.get('movement_type_keys')):
        flags.append('missing_taxonomy')
    if blank(robot.get('industry_keys')) and blank(robot.get('use_keys')):
        flags.append('missing_industry_use')

    return flags


def company_flags(company: dict) -> list[str]:
    flags = []
    if blank(company.get('website')):
        flags.append('missing_website')
    if blank(company.get('country_code')) and blank(company.get('country_id')):
        flags.append('missing_country')
    if blank(company.get('description')):
        flags.append('missing_company_description')
    if blank(company.get('primary_focus')) and blank(company.get('product_type')):
        flags.append('missing_focus')
    return flags


def bar(n: int, total: int, width: int = 28) -> str:
    if not total:
        return ''
    filled = round(width * n / total)
    return '#' * filled + '.' * (width - filled)


def section(title: str) -> None:
    print()
    print(title)
    print('-' * len(title))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--staging', type=pathlib.Path, default=DEFAULT_STAGING)
    ap.add_argument('--include-imported', action='store_true',
                    help='Include companies already listed in the import ledger.')
    ap.add_argument('--top-companies', type=int, default=15,
                    help='How many worst-offending companies to list (default 15).')
    ap.add_argument('--json', type=pathlib.Path, help='Also write the profile as JSON.')
    args = ap.parse_args()

    if not args.staging.exists():
        print(f'staging file not found: {args.staging}', file=sys.stderr)
        return 1

    data = json.loads(args.staging.read_text(encoding='utf8'))
    companies = data.get('companies', [])
    robots = data.get('robots', [])

    ledger = data.get('import_ledger', {}) or {}
    imported_slugs = {
        entry.get('slug') for entry in ledger.get('imported', []) if entry.get('slug')
    }
    if imported_slugs and not args.include_imported:
        companies = [c for c in companies if c.get('slug') not in imported_slugs]
        robots = [r for r in robots if r.get('company_slug') not in imported_slugs]

    print('Gap staging flag profile')
    print('=' * 24)
    print(f'staging file      : {args.staging}')
    print(f'generated at      : {data.get("generated_at", "?")}')
    print(f'prod baseline at  : {data.get("baseline_generated_at", "?")}')
    if imported_slugs:
        state = 'included' if args.include_imported else f'excluded ({len(imported_slugs)} companies)'
        print(f'already imported  : {state}')
    print(f'companies in scope: {len(companies)}')
    print(f'robots in scope   : {len(robots)}')
    print(f'low-signal held   : {len(data.get("low_signal_companies", []))}')
    dropped = data.get('qa_dropped', {}) or {}
    if dropped:
        # values are a mix of counts and lists of dropped entries
        n_dropped = sum(len(v) if isinstance(v, (list, tuple, dict)) else int(v)
                        for v in dropped.values())
        print(f'dropped by QA     : {n_dropped} across {len(dropped)} passes')

    # ---------------- robots ----------------
    robot_counter: collections.Counter[str] = collections.Counter()
    per_robot: list[int] = []
    by_company: collections.Counter[str] = collections.Counter()
    clean = 0

    for r in robots:
        flags = robot_flags(r)
        robot_counter.update(flags)
        per_robot.append(len(flags))
        if not flags:
            clean += 1
        else:
            by_company[r.get('company_name') or r.get('company_slug') or '?'] += len(flags)

    if robots:
        section(f'Robot flags — {len(robots)} staged records')
        for flag, n in robot_counter.most_common():
            pct = 100.0 * n / len(robots)
            print(f'  {flag:<30} {n:>5}  {pct:5.1f}%  {bar(n, len(robots))}')

        avg = sum(per_robot) / len(per_robot)
        section('Flags per robot')
        print(f'  arriving with zero flags     : {clean} ({100.0 * clean / len(robots):.1f}%)')
        print(f'  average flags per robot      : {avg:.1f}')
        dist = collections.Counter(per_robot)
        for count in sorted(dist):
            print(f'  {count:>2} flag(s){"":<10} {dist[count]:>5}  {bar(dist[count], len(robots))}')

    # ---------------- companies ----------------
    company_counter: collections.Counter[str] = collections.Counter()
    company_clean = 0
    for c in companies:
        flags = company_flags(c)
        company_counter.update(flags)
        if not flags:
            company_clean += 1

    if companies:
        section(f'Company flags — {len(companies)} staged records')
        for flag, n in company_counter.most_common():
            pct = 100.0 * n / len(companies)
            print(f'  {flag:<30} {n:>5}  {pct:5.1f}%  {bar(n, len(companies))}')
        print(f'  {"arriving with zero flags":<30} {company_clean:>5}  '
              f'{100.0 * company_clean / len(companies):5.1f}%')

    # ---------------- worst offenders ----------------
    if by_company and args.top_companies:
        section(f'Companies carrying the most robot flags (top {args.top_companies})')
        for name, total in by_company.most_common(args.top_companies):
            n_robots = sum(1 for r in robots
                           if (r.get('company_name') or r.get('company_slug')) == name)
            print(f'  {total:>5} flags across {n_robots:>3} robots   {name[:52]}')

    # ---------------- the headline ----------------
    section('What this means for the queue')
    if robots:
        would_flag = len(robots) - clean
        print(f'  Importing today puts {would_flag} robots into the review queue carrying')
        print(f'  {sum(per_robot)} flags between them, at an average of {sum(per_robot)/len(robots):.1f} each.')
        top = robot_counter.most_common(3)
        if top:
            names = ', '.join(f'{f} ({100.0*n/len(robots):.0f}%)' for f, n in top)
            print(f'  Most common: {names}.')
        print()
        print('  NOTE: this is the staged state on disk, BEFORE the light-enrich step')
        print('  inside bulk_import_remaining_gaps.py, which fills og:description,')
        print('  og:image and a purpose fallback at import time. Expect missing_image,')
        print('  missing_description and missing_purpose to clear substantially on')
        print('  arrival; the flags at 100% here are the ones light-enrich does not')
        print('  touch, and those are the real queue burden until the prod enrichment')
        print('  pass runs against the pending_review records.')

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({
            'staging_file': str(args.staging),
            'generated_at': data.get('generated_at'),
            'scope': {'companies': len(companies), 'robots': len(robots)},
            'robot_flags': dict(robot_counter),
            'company_flags': dict(company_counter),
            'robots_with_zero_flags': clean,
            'companies_with_zero_flags': company_clean,
            'total_robot_flags': sum(per_robot),
            'worst_companies': by_company.most_common(50),
        }, indent=2), encoding='utf8')
        print(f'\nwrote {args.json}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
