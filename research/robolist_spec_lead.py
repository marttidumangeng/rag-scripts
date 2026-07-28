"""Robolist spec-lead extractor — LAST-RESORT fallback for hard-to-find specs.

Robolist.ai is a direct competitor. This helper is **not** a data source: it is a
*lead finder* used only after a documented dead primary-source search leaves a spec
blank. It reads one robolist robot page and returns two things:

  1. The external **source URLs** robolist has on record for that robot, classified
     into reject / aggregator / OEM-candidate. You chase an OEM-candidate to the
     manufacturer, confirm it names the model + spec, and cite *that* page.
  2. A **quarantine note** holding robolist's displayed spec values, clearly marked
     unverified and not-to-be-typed. It exists so a human can eyeball for a
     discrepancy — it is never written to a typed column.

Guardrails (enforced here so discipline lives in code, not just the skill doc):
  - robolist.ai (and its own subpaths) is NEVER a citable source — dropped.
  - Social hosts (x/twitter, linkedin, facebook, youtube, reddit) are dropped.
  - Known aggregators (humanoid.press, ifactoryapp, robotsguide, …) are flagged
    "must still reach OEM" and are NOT citable on their own.
  - The script writes nothing to the DB and emits no fill-ready value. Its only
    outputs are the note text, the classified leads, and a usage-log line.

Usage:
    cd scripts/research
    export PYTHONIOENCODING=utf-8
    # by explicit URL (most reliable):
    python robolist_spec_lead.py --url https://www.robolist.ai/robots/optimus-gen-3 \
        --robot-id 2502 --missing payload_kg,reach_mm
    # or resolve a candidate slug from the display name:
    python robolist_spec_lead.py --name "Optimus Gen 3" --robot-id 2502

Output: prints the classified leads + the quarantine note to stdout; pass
``--out FILE`` to also write the note block to a file for pasting into Robot.notes.
Every run appends one JSON line to state/robolist_leads_log.jsonl.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
import time
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

_HERE = Path(__file__).resolve().parent
_CACHE_DIR = _HERE / "state" / "robolist_cache"
_LOG_PATH = _HERE / "state" / "robolist_leads_log.jsonl"

ROBOLIST_HOST_RE = re.compile(r"(^|\.)robolist\.ai$", re.IGNORECASE)

# Never citable on their own — social / self.
DROP_HOSTS = {
    "x.com", "twitter.com", "www.twitter.com", "linkedin.com", "www.linkedin.com",
    "facebook.com", "www.facebook.com", "youtube.com", "www.youtube.com",
    "youtu.be", "reddit.com", "www.reddit.com", "t.me", "instagram.com",
    "www.instagram.com",
}

# Static assets / CDNs — never a source link. Matched as a substring of the host,
# plus a file-extension check on the path (thumbnails, fonts, bundles, blobs).
ASSET_HOST_MARKERS = ("ytimg", "vercel-storage", "gstatic", "googleapis",
                      "fbcdn", "cloudfront", "fonts.")
ASSET_EXT_RE = re.compile(r"\.(jpe?g|png|webp|gif|svg|ico|css|js|woff2?|ttf|mp4|avif)(\?|#|$)", re.I)

# Secondary aggregators — a lead only, must still be traced to the OEM before citing.
AGGREGATOR_HOSTS = {
    "humanoid.press", "ifactoryapp.com", "robotsguide.com", "www.robotsguide.com",
    "roboticsbiz.com", "therobotreport.com", "www.therobotreport.com",
    "en.wikipedia.org", "wikipedia.org", "spectrum.ieee.org", "robots.ieee.org",
    "a3.org", "www.a3.org",
}

# Spec labels we try to lift from the visible text for the quarantine note. Kept
# broad on purpose — precision does not matter because these values are never used
# to fill a column, only to preserve what robolist displayed for eyeballing.
SPEC_LABELS = [
    "Height", "Weight", "Form factor", "Walking speed", "Speed", "Mobility type",
    "Terrain capability", "Total DOF", "DOF per arm", "DOF per hand",
    "Total actuators", "Payload", "Lifting capacity", "Reach", "Repeatability",
    "Battery", "Battery type", "Runtime", "Onboard compute", "Sensors", "LiDAR",
    "Programming", "Price", "Maturity", "Degrees of freedom",
]
# Bare "DOF" is dropped from extraction — it duplicates "Total DOF" — but stays a boundary.


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    return s.strip("-")


def _fetch(url: str, *, refresh: bool = False) -> str | None:
    """Single, cached, polite GET of a robolist page. Returns HTML or None."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = _CACHE_DIR / ((_slugify(urlparse(url).path) or "index") + ".html")
    if cache.is_file() and not refresh:
        return cache.read_text(encoding="utf-8", errors="replace")

    headers = {
        "Referer": "https://www.google.com/",
        "Accept-Language": "en-US,en;q=0.9",
    }
    html = None
    try:  # prefer curl_cffi (used elsewhere in the repo) for TLS fingerprinting
        from curl_cffi import requests as cffi

        time.sleep(1.0)
        r = cffi.get(url, impersonate="chrome124", headers=headers, timeout=20)
        if r.status_code == 200 and len(r.text) > 2000:
            html = r.text
    except Exception:
        html = None
    if html is None:
        try:
            import requests

            r = requests.get(url, headers={**headers, "User-Agent": "Mozilla/5.0"}, timeout=20)
            if r.status_code == 200 and len(r.text) > 2000:
                html = r.text
        except Exception:
            html = None
    if html:
        cache.write_text(html, encoding="utf-8", errors="replace")
    return html


def _visible_text(html: str) -> str:
    txt = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    txt = re.sub(r"(?s)<[^>]+>", " ", txt)
    return re.sub(r"[ \t]+", " ", unescape(txt))


def classify_source(url: str) -> str:
    """Return one of: 'reject', 'aggregator', 'candidate'."""
    host = (urlparse(url).hostname or "").lower()
    if not host or ROBOLIST_HOST_RE.search(host) or host in DROP_HOSTS:
        return "reject"
    if ASSET_EXT_RE.search(url) or any(m in host for m in ASSET_HOST_MARKERS):
        return "reject"
    if host in AGGREGATOR_HOSTS:
        return "aggregator"
    return "candidate"


def extract_sources(html: str) -> list[dict]:
    hrefs = re.findall(r'href="([^"]+)"', html) + re.findall(r"href='([^']+)'", html)
    seen: dict[str, dict] = {}
    for href in hrefs:
        href = unescape(href)
        if not href.lower().startswith("http"):
            continue
        cls = classify_source(href)
        if cls == "reject":
            continue
        host = (urlparse(href).hostname or "").lower()
        seen.setdefault(href, {"url": href, "host": host, "class": cls})
    # candidates first (the ones worth chasing), then aggregators
    return sorted(seen.values(), key=lambda d: (d["class"] != "candidate", d["host"]))


# Extra labels used only as value *boundaries* (not themselves extracted), to stop a
# cell's value bleeding into the next spec in the flattened text.
_BOUNDARY_ONLY = [
    "Mobility type", "F/T sensors", "VLM on-board", "Imitation learning", "ROS 1/2",
    "ROS 1", "ROS 2", "API / SDK", "API/SDK", "Battery type", "Environments",
    "Locomotion", "Materials", "Certifications", "Country", "Mobility", "DOF",
]
# Longest-first so "Total DOF" / "DOF per arm" win over bare "DOF" as a boundary.
_STOP_RE = re.compile(
    r"\b(" + "|".join(re.escape(l) for l in sorted(set(SPEC_LABELS) | set(_BOUNDARY_ONLY), key=len, reverse=True)) + r")\b"
)


def extract_specs(html: str) -> dict[str, str]:
    """Best-effort label->value scrape for the quarantine note. Never authoritative.

    Reduce the page to visible text (the tooltip SVGs carry no text), then for each
    capitalized grid label take the run up to the next label. Case-sensitive so the
    lowercase intro sentence ("height 173 cm") never masks the grid cell."""
    vt = _visible_text(html)
    specs: dict[str, str] = {}
    for label in SPEC_LABELS:
        if label in specs:
            continue
        m = re.search(rf"\b{re.escape(label)}\b", vt)   # case-sensitive on purpose
        if not m:
            continue
        tail = vt[m.end():m.end() + 80].strip(" :·-|")
        stop = _STOP_RE.search(tail)
        val = (tail[:stop.start()] if stop else tail[:40]).strip(" :·-|")
        if (val and re.search(r"[A-Za-z0-9]", val)
                and not val.lower().startswith(("view", "source", "verified", "unverified", "what is"))):
            specs[label] = val[:60]
    return specs


def build_note(*, url: str, robot_name: str, missing: list[str],
               specs: dict[str, str], sources: list[dict], today: str) -> str:
    lines = [
        "[ROBOLIST SPEC LEAD — quarantined competitor data, DO NOT type into columns]",
        f"Pulled {today} from {url} as a fallback after a documented dead primary-source search.",
        "robolist.ai is a competitor; these are its DISPLAYED values — unverified by us,",
        "NOT citable, and NOT to be written to any typed column. Kept only for eyeballing.",
    ]
    if missing:
        lines.append("Spec(s) we were hunting: " + ", ".join(missing))
    lines.append("")
    if specs:
        lines.append("Values as displayed by robolist (verify independently at the OEM or discard):")
        for k, v in specs.items():
            lines.append(f"  {k}: {v}")
    else:
        lines.append("(Could not parse spec values automatically — read the page manually.)")
    lines.append("")
    cands = [s for s in sources if s["class"] == "candidate"]
    aggs = [s for s in sources if s["class"] == "aggregator"]
    lines.append("Source links on record at robolist (chase to the OEM; none of these is a citation by itself):")
    if cands:
        for s in cands:
            lines.append(f"  [OEM-CANDIDATE — confirm it is the manufacturer] {s['url']}")
    if aggs:
        for s in aggs:
            lines.append(f"  [AGGREGATOR — must still reach the OEM] {s['url']}")
    if not sources:
        lines.append("  (robolist listed no external source — do not fill; leave the spec blank.)")
    lines.append("")
    lines.append("ACTION: open an OEM-CANDIDATE link, confirm it names the model + the spec, then")
    lines.append("PATCH the typed column citing the OEM page. If no link reaches a primary OEM")
    lines.append("source, leave the spec blank — never fill from robolist's value above.")
    lines.append("---")
    return "\n".join(lines)


def _log(entry: dict) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def resolve_url(args) -> str | None:
    if args.url:
        return args.url
    if args.slug:
        return f"https://www.robolist.ai/robots/{args.slug}"
    if args.name:
        return f"https://www.robolist.ai/robots/{_slugify(args.name)}"
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="Full robolist robot URL (most reliable)")
    src.add_argument("--slug", help="robolist robot slug (…/robots/<slug>)")
    src.add_argument("--name", help="Display name; a candidate slug is derived and verified")
    ap.add_argument("--robot-id", default="", help="Our Robot.id, for the log + note context")
    ap.add_argument("--missing", default="", help="Comma-sep spec fields we failed to source (context only)")
    ap.add_argument("--refresh", action="store_true", help="Bypass the page cache")
    ap.add_argument("--out", help="Also write the quarantine note block to this file")
    args = ap.parse_args(argv)

    url = resolve_url(args)
    html = _fetch(url, refresh=args.refresh)
    if not html:
        print(f"NO PAGE: could not fetch {url} (404 / bot-wall / offline). Do not fill any spec.",
              file=sys.stderr)
        _log({"ts": _dt.datetime.now().isoformat(timespec="seconds"), "robot_id": args.robot_id,
              "url": url, "ok": False, "reason": "fetch_failed"})
        return 2

    text = _visible_text(html)
    # Confirm the page really is this robot when we guessed the slug from a name.
    if args.name:
        toks = [t for t in re.split(r"\W+", args.name.lower()) if len(t) > 2]
        if toks and sum(t in text.lower() for t in toks) < max(1, len(toks) // 2):
            print(f"MISMATCH: {url} does not look like '{args.name}'. Pass --url explicitly.",
                  file=sys.stderr)
            return 3

    missing = [m.strip() for m in args.missing.split(",") if m.strip()]
    sources = extract_sources(html)
    specs = extract_specs(html)
    today = _dt.date.today().isoformat()
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    robot_name = unescape(m.group(1)).split("—")[0].strip() if m else (args.name or url)

    note = build_note(url=url, robot_name=robot_name, missing=missing,
                      specs=specs, sources=sources, today=today)

    n_cand = sum(s["class"] == "candidate" for s in sources)
    n_agg = sum(s["class"] == "aggregator" for s in sources)
    print(f"# robolist lead for {robot_name}")
    print(f"# {n_cand} OEM-candidate link(s), {n_agg} aggregator link(s), {len(specs)} value(s) parsed\n")
    print(note)

    if args.out:
        Path(args.out).write_text(note + "\n", encoding="utf-8")
        print(f"\n(note written to {args.out})", file=sys.stderr)

    _log({"ts": _dt.datetime.now().isoformat(timespec="seconds"), "robot_id": args.robot_id,
          "url": url, "ok": True, "missing": missing, "n_candidates": n_cand,
          "n_aggregators": n_agg, "n_specs_parsed": len(specs)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
