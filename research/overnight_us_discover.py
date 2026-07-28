"""Overnight US content-queue drain: soft-enrich + OEM catalog discover.

Priority: companies with country=US only (skip null-country China fleets).
For each company:
  1. Dump pending robots (full fields)
  2. Fetch company website; extract product/robot candidate URLs
  3. Soft-patch pending: family_key, availability, EN features/purpose when
     OEM page text is available; country US; uses if missing
  4. Append session log to morning report

Does NOT auto-publish. Leaves pending_review.

Usage:
  python -u overnight_us_discover.py
  python -u overnight_us_discover.py --max-companies 20
  python -u overnight_us_discover.py --company-id 328
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

QUEUE = _RESEARCH / "staging" / "reports" / "us-overnight-queue.json"
PROGRESS = _RESEARCH / "staging" / "reports" / "us-overnight-progress.json"
REPORT = _RESEARCH / "docs" / "reports" / "us-overnight-morning-report.md"
SESSION = _RESEARCH / "staging" / "reports" / "us-overnight-session.jsonl"

US_ID = 20
AVAILABLE = 11
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

# Known non-US to skip even if flagged US wrongly
SKIP_IDS = {
    375,  # Brightpick — Czechia
}

# Prefer small fleets first for overnight depth
SKIP_NAME_RE = re.compile(r"unknown|various manufacturers", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_session(obj: dict[str, Any]) -> None:
    SESSION.parent.mkdir(parents=True, exist_ok=True)
    with SESSION.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def append_report(lines: list[str]) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if REPORT.is_file():
        text = REPORT.read_text(encoding="utf-8")
    else:
        text = ""
    marker = "## Overnight session log"
    block = "\n".join(lines) + "\n"
    if marker in text:
        # insert after marker section header
        parts = text.split(marker, 1)
        rest = parts[1]
        # skip existing placeholder line
        text = parts[0] + marker + "\n\n" + block + rest.lstrip("\n")
        # Avoid duplicating forever — append at end of file under session log instead
        text = parts[0] + marker + "\n\n"
        # Keep prior session entries if any after marker until Related
        after = parts[1]
        if "## Related" in after:
            prior, related = after.split("## Related", 1)
            prior = prior.replace("_(appended as companies are enriched)_", "").strip()
            text = (
                parts[0]
                + marker
                + "\n\n"
                + (prior + "\n\n" if prior else "")
                + block
                + "\n## Related"
                + related
            )
        else:
            text = parts[0] + marker + "\n\n" + after.strip() + "\n\n" + block
    else:
        text += "\n" + marker + "\n\n" + block
    REPORT.write_text(text, encoding="utf-8")


def company_slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:40] or "oem"


def extract_links(html: str, base: str) -> list[dict[str, str]]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, re.I)
    texts = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S)
    by_url: dict[str, str] = {}
    for href, inner in texts:
        t = re.sub(r"<[^>]+>", " ", inner)
        t = re.sub(r"\s+", " ", t).strip()
        by_url[href] = t[:120]
    out = []
    seen = set()
    keywords = (
        "product",
        "robot",
        "uuv",
        "auv",
        "drone",
        "vehicle",
        "platform",
        "solution",
        "system",
        "surgical",
        "arm",
        "cobot",
        "amr",
        "agv",
        "exoskeleton",
    )
    for href in hrefs:
        full = urljoin(base, href)
        if full in seen:
            continue
        low = full.lower()
        if any(x in low for x in ("#", "javascript:", "mailto:", "tel:", ".pdf", ".jpg", ".png")):
            continue
        parsed = urlparse(full)
        base_host = urlparse(base).netloc.lower().replace("www.", "")
        host = parsed.netloc.lower().replace("www.", "")
        if base_host and host and base_host not in host and host not in base_host:
            continue
        path = parsed.path.lower()
        if any(k in path or k in (by_url.get(href) or "").lower() for k in keywords):
            seen.add(full)
            out.append({"url": full, "anchor": by_url.get(href) or ""})
    return out[:80]


def fetch(url: str) -> tuple[int, str]:
    try:
        r = requests.get(url, headers=UA, timeout=45)
        return r.status_code, r.text or ""
    except requests.RequestException as e:
        return 0, str(e)


def list_pending(client: ResearchApiClient, cid: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        data = client._get(
            "robots/robots/",
            params={
                "company_ref": cid,
                "status": "pending_review",
                "page": page,
                "page_size": 50,
            },
        )
        batch = data.get("results") or []
        if not batch:
            break
        for r in batch:
            rows.append(client._get(f"robots/robots/{r['id']}/"))
        if not data.get("next"):
            break
        page += 1
    return rows


def soft_patch_robot(
    client: ResearchApiClient,
    robot: dict[str, Any],
    *,
    co_name: str,
    co_slug: str,
    oem_links: list[dict[str, str]],
) -> dict[str, Any]:
    rid = int(robot["id"])
    name = robot.get("name") or f"Robot-{rid}"
    result: dict[str, Any] = {"id": rid, "name": name, "actions": []}
    body: dict[str, Any] = {
        "manufacturer_countries": [US_ID],
        "manufacturer_country_ref": US_ID,
    }
    avail = robot.get("availability_status")
    avail_key = avail.get("key") if isinstance(avail, dict) else avail
    if not avail_key or avail_key in ("released", "Released"):
        body["availability_status"] = AVAILABLE
        result["actions"].append("set_available")

    fam = robot.get("family_key") or ""
    if not fam:
        # derive from name token
        token = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32] or str(rid)
        body["family_key"] = f"{co_slug}:{token}"
        body["family_name"] = name
        body["family_url"] = robot.get("url") or (oem_links[0]["url"] if oem_links else "")
        body["product_url_scope"] = "exact_variant" if robot.get("url") else "family"
        result["actions"].append("set_family")

    feats = (robot.get("features") or "").strip()
    desc = (robot.get("description") or "").strip()
    purpose = (robot.get("purpose") or "").strip()
    url = (robot.get("url") or "").strip()

    # Match OEM link by name tokens
    matched = None
    name_toks = [t for t in re.split(r"[^a-z0-9]+", name.lower()) if len(t) > 2]
    for link in oem_links:
        blob = (link["url"] + " " + link.get("anchor", "")).lower()
        if name_toks and sum(1 for t in name_toks if t in blob) >= max(1, len(name_toks) // 2):
            matched = link
            break

    page_text = ""
    if matched and (not feats or len(feats) < 40 or not purpose):
        code, html = fetch(matched["url"])
        if code == 200 and len(html) > 500:
            page_text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
            page_text = re.sub(r"<style[\s\S]*?</style>", " ", page_text, flags=re.I)
            page_text = re.sub(r"<[^>]+>", " ", page_text)
            page_text = re.sub(r"\s+", " ", page_text).strip()
            if not url:
                body["url"] = matched["url"]
                result["actions"].append("set_url")
            info = robot.get("information_sources") or []
            if not info:
                body["information_source_urls"] = [matched["url"]]
                result["actions"].append("set_sources")

    if len(feats) < 40 and page_text:
        # Take a citeable snippet — first ~400 chars of prose near product words
        snippet = page_text[:900]
        body["features"] = (
            f"OEM {urlparse(matched['url']).netloc if matched else co_slug}: "
            f"{snippet[:420].strip()} Soft: auto overnight extract; verify before Approve."
        )
        result["actions"].append("set_features")

    if (not purpose or purpose == desc or (desc and purpose in desc[:200])) and page_text:
        # Short task lines from keywords
        tasks = []
        low = page_text.lower()
        for label, keys in [
            ("Surgical assistance", ("surgical", "surgery", "laparoscop")),
            ("Inspection and survey", ("inspect", "survey", "mapping")),
            ("Security patrol", ("security", "patrol", "surveillance")),
            ("Material handling", ("warehouse", "logistics", "material handling")),
            ("Research platform", ("research", "oceanograph", "science")),
        ]:
            if any(k in low for k in keys):
                tasks.append(label)
        if not tasks:
            tasks = ["OEM application per product page"]
        body["purpose"] = "\n".join(tasks[:3])
        result["actions"].append("set_purpose")

    uses = robot.get("uses") or []
    if not uses:
        # minimal uses by heuristics
        tax_uses = {r["key"]: r["id"] for r in client._get("robots/uses/") if r.get("key")}
        pick = []
        blob = ((name or "") + " " + (desc or "") + " " + page_text[:500]).lower()
        for key in ("inspection", "monitoring", "research", "security", "patrol", "surgery", "helping"):
            # surgery may not exist
            if key in tax_uses and any(
                w in blob for w in (key, "surgical", "medical", "ocean", "drone", "uuv")
            ):
                pick.append(tax_uses[key])
        if not pick and "research" in tax_uses:
            pick = [tax_uses["research"], tax_uses.get("inspection") or tax_uses["research"]]
            pick = [x for x in pick if x]
        if pick:
            body["uses"] = list(dict.fromkeys(pick))[:4]
            result["actions"].append("set_uses")

    notes = (
        f"[AI Research] Overnight US soft enrich {_now()[:10]}: "
        f"family/availability/country; OEM scrape when available."
    )
    body["notes"] = notes

    if len(body) <= 3 and "notes" in body and "manufacturer_countries" in body:
        # still patch country
        pass

    try:
        client._patch(f"robots/robots/{rid}/", body)
        result["ok"] = True
    except Exception as e:
        result["ok"] = False
        result["error"] = str(e)[:200]
        # retry without uses/tags
        slim = {k: v for k, v in body.items() if k not in ("uses", "tags")}
        try:
            client._patch(f"robots/robots/{rid}/", slim)
            result["ok"] = True
            result["actions"].append("slim_ok")
        except Exception as e2:
            result["error"] = str(e2)[:200]

    return result


def process_company(client: ResearchApiClient, entry: dict[str, Any]) -> dict[str, Any]:
    cid = int(entry["company_id"])
    name = entry.get("name") or f"Company-{cid}"
    website = (entry.get("website") or "").strip()
    print(f"\n=== {cid} {name} pending={entry.get('pending')} web={website}")
    summary: dict[str, Any] = {
        "company_id": cid,
        "name": name,
        "website": website,
        "started_at": _now(),
        "oem_product_links": [],
        "robots": [],
        "discovered_catalog": [],
    }
    slug = company_slug(name)

    oem_links: list[dict[str, str]] = []
    if website:
        code, html = fetch(website)
        summary["website_status"] = code
        if code == 200:
            oem_links = extract_links(html, website)
            summary["oem_product_links"] = oem_links
            summary["discovered_catalog"] = [
                {"url": x["url"], "anchor": x.get("anchor") or ""} for x in oem_links[:40]
            ]

    pending = list_pending(client, cid)
    summary["pending_count"] = len(pending)
    for robot in pending:
        res = soft_patch_robot(
            client, robot, co_name=name, co_slug=slug, oem_links=oem_links
        )
        summary["robots"].append(
            {
                **res,
                "url": robot.get("url"),
                "image": bool(robot.get("image") or robot.get("s3_image")),
                "feats_before": len(robot.get("features") or ""),
            }
        )
        print(f"  {res['id']} {res['name'][:40]} actions={res.get('actions')} ok={res.get('ok')}")
        time.sleep(0.3)

    summary["finished_at"] = _now()
    append_session(summary)

    # Report section
    lines = [
        f"### {name} ({cid}) — {_now()[:16]}Z",
        "",
        f"- Website: {website or '—'}",
        f"- Website HTTP: {summary.get('website_status', '—')}",
        f"- Pending processed: {len(pending)}",
        f"- OEM product-like links found: {len(oem_links)}",
        "",
        "**Queue robots:**",
        "",
    ]
    for r in summary["robots"]:
        lines.append(
            f"- `{r['id']}` {r['name']} — actions: {', '.join(r.get('actions') or []) or 'none'}; "
            f"ok={r.get('ok')}; url={r.get('url') or '—'}"
        )
    if oem_links:
        lines.append("")
        lines.append("**OEM catalog candidates (from website crawl):**")
        lines.append("")
        for link in oem_links[:25]:
            label = link.get("anchor") or "(no anchor)"
            lines.append(f"- {label} — {link['url']}")
    lines.append("")
    append_report(lines)
    return summary


def us_entries(max_companies: int | None, only_id: int | None) -> list[dict[str, Any]]:
    data = json.loads(QUEUE.read_text(encoding="utf-8"))
    companies = data.get("companies") or []
    # Prefer explicit US
    us = [c for c in companies if (c.get("country") or "").upper() == "US"]
    us = [c for c in us if c["company_id"] not in SKIP_IDS]
    us = [c for c in us if not SKIP_NAME_RE.search(c.get("name") or "")]
    # Small fleets first
    us.sort(key=lambda c: (c.get("pending") or 0, c.get("name") or ""))
    if only_id:
        us = [c for c in us if c["company_id"] == only_id]
    if max_companies:
        us = us[:max_companies]
    return us


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-companies", type=int, default=0)
    ap.add_argument("--company-id", type=int, default=0)
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()

    if not QUEUE.is_file():
        print("missing queue; run _build_us_overnight_queue.py first")
        return 1

    entries = us_entries(args.max_companies or None, args.company_id or None)
    print(f"US companies to process: {len(entries)}")
    for e in entries:
        print(f"  {e['pending']:3d}  {e['company_id']:5d}  {e['name']}")

    client = ResearchApiClient()
    progress = {"started_at": _now(), "companies": []}
    append_report(
        [
            f"## Overnight run started {_now()}",
            "",
            f"Processing **{len(entries)}** US companies (explicit country=US).",
            "",
        ]
    )

    for entry in entries:
        try:
            summary = process_company(client, entry)
            progress["companies"].append(
                {
                    "company_id": summary["company_id"],
                    "name": summary["name"],
                    "pending": summary.get("pending_count"),
                    "oem_links": len(summary.get("oem_product_links") or []),
                    "ok_robots": sum(1 for r in summary.get("robots") or [] if r.get("ok")),
                }
            )
        except Exception as e:
            print(f"FAIL {entry.get('company_id')}: {e}")
            append_session(
                {
                    "company_id": entry.get("company_id"),
                    "error": str(e),
                    "at": _now(),
                }
            )
            append_report(
                [
                    f"### {entry.get('name')} ({entry.get('company_id')}) — FAILED",
                    "",
                    f"- Error: `{e}`",
                    "",
                ]
            )
        PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")

    progress["finished_at"] = _now()
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")
    append_report(
        [
            f"## Overnight run finished {_now()}",
            "",
            f"- Companies attempted: {len(progress['companies'])}",
            f"- Progress file: `staging/reports/us-overnight-progress.json`",
            f"- Session JSONL: `staging/reports/us-overnight-session.jsonl`",
            "",
        ]
    )
    print("DONE", progress.get("finished_at"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
