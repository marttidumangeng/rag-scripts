#!/usr/bin/env python3
"""
Report zh-CN robots and classify them as duplicates or unique.

A zh-CN robot is considered a DUPLICATE if there exists another robot
in the same company with a similar name (after stripping non-alphanumeric chars).

Usage:
  python validate_zh_duplicates.py              # report only
  python validate_zh_duplicates.py --delete     # delete confirmed duplicates (requires --apply)
  python validate_zh_duplicates.py --delete --apply

Output columns:
  DUPLICATE  — zh-CN robot that has a matching English robot in the same company
  UNIQUE     — zh-CN robot with no English counterpart (Chinese-only manufacturer?)
  NO_COMPANY — zh-CN robot with no company assigned
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env
import sys as _sys; load_research_env(local="--local" in _sys.argv)

from api_client import ResearchApiClient


def _normalize(name: str) -> str:
    """Strip non-alphanumeric chars and lowercase for fuzzy matching."""
    return re.sub(r'[^a-z0-9]', '', name.lower())


def fetch_zh_robots(client: ResearchApiClient) -> list[dict]:
    """Fetch all zh-CN robots via paginated API."""
    results = []
    page = 1
    while True:
        data = client._get('robots/robots/', params={
            'source_locale': 'zh-CN',
            'page': page,
            'page_size': 100,
        })
        batch = data.get('results', [])
        results.extend(batch)
        print(f'  Fetched page {page}: {len(batch)} zh-CN robots (total so far: {len(results)})', flush=True)
        if not data.get('next'):
            break
        page += 1
    return results


def fetch_en_robots_for_company(client: ResearchApiClient, company_id: int) -> list[dict]:
    """Fetch English robots for a specific company."""
    results = []
    page = 1
    while True:
        data = client._get('robots/robots/', params={
            'company_ref': company_id,
            'source_locale': 'en',
            'page': page,
            'page_size': 100,
        })
        batch = data.get('results', [])
        results.extend(batch)
        if not data.get('next'):
            break
        page += 1
    return results


def run(args: argparse.Namespace) -> int:
    client = ResearchApiClient()

    print('Fetching zh-CN robots from prod...')
    zh_robots = fetch_zh_robots(client)
    print(f'Total zh-CN robots: {len(zh_robots)}\n')

    if not zh_robots:
        print('No zh-CN robots found.')
        return 0

    # Group zh-CN robots by company
    by_company: dict[int | None, list[dict]] = {}
    for r in zh_robots:
        cref = r.get('company_ref')
        cid = cref.get('id') if isinstance(cref, dict) else cref
        by_company.setdefault(cid, []).append(r)

    duplicates = []
    unique = []
    no_company = []

    en_cache: dict[int, list[dict]] = {}

    for cid, zh_list in by_company.items():
        if cid is None:
            no_company.extend(zh_list)
            continue

        if cid not in en_cache:
            en_cache[cid] = fetch_en_robots_for_company(client, cid)

        en_robots = en_cache[cid]
        en_normalized = {_normalize(r['name']): r for r in en_robots}

        for zh_r in zh_list:
            zh_norm = _normalize(zh_r['name'])
            # Check for exact normalized match OR substring match
            match = en_normalized.get(zh_norm)
            if not match:
                # Try substring: English name words appear in zh normalized name or vice versa
                for en_norm, en_r in en_normalized.items():
                    if en_norm and (en_norm in zh_norm or zh_norm in en_norm):
                        match = en_r
                        break

            if match:
                duplicates.append((zh_r, match))
            else:
                unique.append(zh_r)

    # --- Report ---
    print('=' * 72)
    print(f'zh-CN DUPLICATE ROBOTS (have English counterpart): {len(duplicates)}')
    print('=' * 72)
    for zh_r, en_r in duplicates[:50]:
        cref = zh_r.get('company_ref') or {}
        cname = cref.get('name', '') if isinstance(cref, dict) else ''
        print(f"  zh id={zh_r['id']:5}  '{zh_r['name'][:35]}'")
        print(f"  en id={en_r['id']:5}  '{en_r['name'][:35]}'  company={cname}")
        print()
    if len(duplicates) > 50:
        print(f'  ... and {len(duplicates) - 50} more duplicates')

    print()
    print('=' * 72)
    print(f'zh-CN UNIQUE ROBOTS (no English counterpart): {len(unique)}')
    print('=' * 72)
    for r in unique[:50]:
        cref = r.get('company_ref') or {}
        cname = cref.get('name', '') if isinstance(cref, dict) else ''
        print(f"  id={r['id']:5}  '{r['name'][:50]}'  company={cname}")
    if len(unique) > 50:
        print(f'  ... and {len(unique) - 50} more unique zh-CN robots')

    print()
    print('=' * 72)
    print(f'zh-CN robots with NO COMPANY: {len(no_company)}')
    print('=' * 72)
    for r in no_company[:20]:
        print(f"  id={r['id']:5}  '{r['name'][:50]}'")

    print()
    print(f'SUMMARY: {len(duplicates)} duplicates | {len(unique)} unique | {len(no_company)} no-company')

    if args.delete:
        if not duplicates:
            print('\nNo duplicates to delete.')
            return 0
        ids_to_delete = [zh_r['id'] for zh_r, _ in duplicates]
        print(f'\n{"DRY RUN — " if not args.apply else ""}Deleting {len(ids_to_delete)} duplicate zh-CN robots...')
        if args.apply:
            deleted = 0
            errors = 0
            for rid in ids_to_delete:
                try:
                    client._session.delete(client._url(f'robots/robots/{rid}/'))
                    deleted += 1
                    print(f'  Deleted id={rid}', flush=True)
                except Exception as exc:
                    print(f'  ERROR deleting id={rid}: {exc}', flush=True)
                    errors += 1
            print(f'\nDeleted {deleted}, errors {errors}')
        else:
            print('IDs that would be deleted:')
            print(', '.join(str(i) for i in ids_to_delete))
            print('\nRerun with --apply to actually delete.')

    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Validate and optionally delete zh-CN duplicate robots')
    p.add_argument('--delete', action='store_true', help='Delete confirmed duplicates')
    p.add_argument('--apply', action='store_true', help='Actually delete (default: dry-run)')
    p.add_argument('--local', action='store_true', help='Use *_LOCAL env vars to target local dev server')
    return p


if __name__ == '__main__':
    raise SystemExit(run(build_parser().parse_args()))
