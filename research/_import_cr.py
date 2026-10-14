"""Import the reviewed Innok staging batch. DRY RUN unless APPLY=1.

`discover_robots.py --apply` re-crawls and imports only what THAT run staged, so
it cannot be used here: the batch was patched after discovery (RAINOS had a
mangled contact-form url, and four INDUROS variants had lost their images to the
site-wide-asset guard). This drives import_staging directly over the reviewed
files instead.

block_skeletons stays ON. These rows carry description, features, payload and at
least one image each, so they should pass it; if any row is a skeleton the guard
is right and it should not be imported.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_client import ResearchApiClient  # noqa: E402
from import_staging import import_staging, resolve_created_by_id  # noqa: E402

APPLY = os.environ.get("APPLY") == "1"
STAGE = Path(__file__).parent / "staging" / "robots" / "construction-robotics"

paths = sorted(STAGE.glob("*.json"))
print(f"staged files: {len(paths)}")
for p in paths:
    print(f"  {p.name}")

created_by = resolve_created_by_id(None)
print(f"\ncreated_by_id: {created_by}")

client = ResearchApiClient()
res = import_staging(
    paths,
    client=client,
    patch=True,
    status="pending_review",
    dry_run=not APPLY,
    created_by_id=created_by,
    block_skeletons=True,
)
print(f"\nresult: {res}")
