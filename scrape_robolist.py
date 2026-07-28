#!/usr/bin/env python3
"""Export public robot data from Robolist.ai JSON-LD markup.

The category page provides the complete robot list in one response. Pass
``--details`` to visit each public robot page and extract its Product JSON-LD.
Detail requests honor the site's published five-second crawl delay by default.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.robolist.ai"
DEFAULT_CATEGORY = "humanoid"
DEFAULT_DELAY_SECONDS = 5.0
DEFAULT_RETRIES = 4
CONNECT_TIMEOUT_SECONDS = 10
READ_TIMEOUT_SECONDS = 20
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"
USER_AGENT = (
    "RobotAI-Geek-PublicDataExporter/1.0 "
    "(https://robot-ai-geek.com; public JSON-LD research)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a Robolist.ai category from its public JSON-LD."
    )
    parser.add_argument(
        "--category",
        default=DEFAULT_CATEGORY,
        help="Category slug to export (default: humanoid).",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Visit each robot page and export all public page data.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refetch detail pages even when a saved per-robot JSON file exists.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help="Seconds between detail requests (minimum/default: 5).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Only process the first N robots; useful for testing.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR}).",
    )
    return parser.parse_args()


def get_json_ld(response_text: str) -> Iterable[dict[str, Any]]:
    soup = BeautifulSoup(response_text, "html.parser")
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text()
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict):
            yield data
        elif isinstance(data, list):
            yield from (item for item in data if isinstance(item, dict))


def graph_nodes(document: dict[str, Any]) -> Iterable[dict[str, Any]]:
    graph = document.get("@graph")
    if isinstance(graph, list):
        yield from (node for node in graph if isinstance(node, dict))
    else:
        yield document


def fetch(
    session: requests.Session,
    url: str,
    retries: int = DEFAULT_RETRIES,
) -> str:
    """Fetch a page, retrying incomplete/stalled chunked responses."""
    last_error: requests.RequestException | None = None

    for attempt in range(1, retries + 1):
        try:
            with session.get(
                url,
                timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            ) as response:
                response.raise_for_status()
                return response.text
        except (
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.ConnectionError,
            requests.exceptions.ReadTimeout,
        ) as exc:
            last_error = exc
            if attempt == retries:
                break
            wait_seconds = min(2 ** (attempt - 1), 8)
            print(
                f"  Download interrupted; retrying in {wait_seconds}s "
                f"({attempt}/{retries})..."
            )
            time.sleep(wait_seconds)

    assert last_error is not None
    raise last_error


def read_category(
    session: requests.Session, category: str
) -> list[dict[str, Any]]:
    url = f"{BASE_URL}/categories/{category}"
    html = fetch(session, url)
    soup = BeautifulSoup(html, "html.parser")
    structured_items: dict[str, dict[str, Any]] = {}

    for document in get_json_ld(html):
        for node in graph_nodes(document):
            if node.get("@type") != "CollectionPage":
                continue
            main_entity = node.get("mainEntity", {})
            items = main_entity.get("itemListElement", [])
            for item in items:
                if not isinstance(item, dict) or not item.get("url"):
                    continue
                slug = urlparse(item["url"]).path.rstrip("/").split("/")[-1]
                structured_items[slug] = {
                    "rank": item.get("position"),
                    "name": item.get("name"),
                    "url": item.get("url"),
                    "slug": slug,
                    "category": category,
                }

    # Next.js streams an early 50-card version and later emits the complete
    # catalog. Select the section whose "N of N shown" marker has the largest
    # total instead of accidentally taking the first streamed section.
    section = None
    largest_total = 0
    for marker in soup.find_all(["p", "div", "span"]):
        marker_text = marker.get_text(" ", strip=True)
        match = re.search(
            r"([\d,]+)\s+of\s+([\d,]+)\s+shown",
            marker_text,
            re.I,
        )
        candidate = marker.find_parent("section")
        if not match or not candidate:
            continue
        total = int(match.group(2).replace(",", ""))
        if total > largest_total:
            largest_total = total
            section = candidate

    if not section:
        if structured_items:
            return list(structured_items.values())
        raise RuntimeError(f"No robot catalog found at {url}")

    robots: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor in section.select('a[href^="/robots/"]'):
        path = anchor.get("href", "").split("?", 1)[0].rstrip("/")
        if path.count("/") != 2:
            continue
        slug = path.rsplit("/", 1)[-1]
        if slug in seen:
            continue
        seen.add(slug)

        structured = structured_items.get(slug, {})
        robots.append(
            {
                "rank": structured.get("rank") or len(robots) + 1,
                "name": structured.get("name")
                or anchor.get_text(" ", strip=True)
                or slug,
                "url": structured.get("url") or f"{BASE_URL}{path}",
                "slug": slug,
                "category": category,
            }
        )

    if not robots:
        raise RuntimeError(f"No robot links found in the catalog at {url}")
    return robots


def organization_name(value: Any) -> Any:
    return value.get("name") if isinstance(value, dict) else value


def clean_text(value: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", value).strip()


def unique_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        marker = json.dumps(record, sort_keys=True, ensure_ascii=False)
        if marker not in seen:
            seen.add(marker)
            result.append(record)
    return result


def extract_robot_page(html: str, page_url: str) -> dict[str, Any]:
    """Capture structured and visible public data from a robot detail page."""
    soup = BeautifulSoup(html, "html.parser")
    product: dict[str, Any] = {}
    videos: list[dict[str, Any]] = []
    json_ld: list[dict[str, Any]] = []

    for document in get_json_ld(html):
        json_ld.append(document)
        for node in graph_nodes(document):
            if node.get("@type") == "Product":
                product = node
            elif node.get("@type") == "VideoObject":
                videos.append(node)

    specifications: dict[str, str] = {}
    for definition in soup.find_all("dt"):
        value = definition.find_next_sibling("dd")
        if value:
            label = clean_text(definition.get_text(" ", strip=True))
            specifications[label] = clean_text(value.get_text("\n", strip=True))

    sections: dict[str, str] = {}
    for heading in soup.find_all(["h2", "h3"]):
        title = clean_text(heading.get_text(" ", strip=True))
        container = heading.find_parent("section")
        if not title or not container:
            continue
        text = clean_text(container.get_text("\n", strip=True))
        if text.casefold().startswith(title.casefold()):
            text = text[len(title) :].strip()
        if text and title not in sections:
            sections[title] = text

    metadata: dict[str, str] = {}
    for meta in soup.find_all("meta"):
        key = meta.get("property") or meta.get("name")
        content = meta.get("content")
        if key and content:
            metadata[str(key)] = str(content)

    links = unique_records(
        {
            "text": clean_text(anchor.get_text(" ", strip=True)),
            "url": urljoin(page_url, anchor["href"]),
        }
        for anchor in soup.find_all("a", href=True)
        if not str(anchor["href"]).startswith(("#", "javascript:"))
    )
    images = unique_records(
        {
            "alt": clean_text(image.get("alt", "")),
            "url": urljoin(page_url, image.get("src") or image.get("data-src")),
        }
        for image in soup.find_all("img")
        if image.get("src") or image.get("data-src")
    )

    offers = product.get("offers")
    offer = offers[0] if isinstance(offers, list) and offers else offers
    offer = offer if isinstance(offer, dict) else {}
    image = product.get("image")
    primary_image = image[0] if isinstance(image, list) and image else image

    summary = {
        "manufacturer": organization_name(
            product.get("manufacturer") or product.get("brand")
        ),
        "description": product.get("description"),
        "image": primary_image,
        "release_date": product.get("releaseDate"),
        "date_modified": product.get("dateModified"),
        "country": organization_name(product.get("countryOfOrigin")),
        "price": offer.get("price"),
        "price_currency": offer.get("priceCurrency"),
        "availability": offer.get("availability"),
    }

    return {
        **summary,
        "page_title": clean_text(soup.title.get_text(" ", strip=True))
        if soup.title
        else None,
        "specifications": specifications,
        "sections": sections,
        "videos": videos,
        "images": images,
        "links": links,
        "metadata": metadata,
        "product_json_ld": product,
        "all_json_ld": json_ld,
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def enrich_robots(
    session: requests.Session,
    robots: list[dict[str, Any]],
    delay: float,
    output_dir: Path,
    refresh: bool,
) -> None:
    details_dir = output_dir / "details" / robots[0]["category"]
    details_dir.mkdir(parents=True, exist_ok=True)
    legacy_details_dir = output_dir / "details"
    total = len(robots)
    for index, robot in enumerate(robots, start=1):
        detail_path = details_dir / f"{robot['slug']}.json"
        legacy_detail_path = legacy_details_dir / f"{robot['slug']}.json"
        if not detail_path.exists() and legacy_detail_path.exists() and not refresh:
            try:
                legacy_record = json.loads(
                    legacy_detail_path.read_text(encoding="utf-8")
                )
                if legacy_record.get("url") == robot["url"]:
                    detail_path.write_text(
                        json.dumps(legacy_record, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
            except (json.JSONDecodeError, OSError):
                pass

        if detail_path.exists() and not refresh:
            try:
                robot.update(json.loads(detail_path.read_text(encoding="utf-8")))
                print(f"[{index}/{total}] {robot['name']} (saved)")
                continue
            except (json.JSONDecodeError, OSError):
                pass

        print(f"[{index}/{total}] {robot['name']} (fetching)")
        try:
            robot.update(extract_robot_page(fetch(session, robot["url"]), robot["url"]))
            robot["error"] = None
        except (requests.RequestException, ValueError) as exc:
            robot["error"] = str(exc)
            print(f"  Request failed: {exc}")

        detail_path.write_text(
            json.dumps(robot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # Keep the consolidated files usable if a long crawl is interrupted.
        write_outputs(robots[:index], output_dir, robot["category"])

        if index < total:
            time.sleep(delay)


def write_outputs(
    robots: list[dict[str, Any]], output_dir: Path, category: str
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"robolist_{category}.json"
    csv_path = output_dir / f"robolist_{category}.csv"

    json_path.write_text(
        json.dumps(robots, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    fieldnames: list[str] = []
    for robot in robots:
        for key in robot:
            if key not in fieldnames:
                fieldnames.append(key)

    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        flat_robots: list[dict[str, Any]] = []
        for robot in robots:
            flat = {
                key: (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                )
                for key, value in robot.items()
                if key not in {"specifications"}
            }
            for label, value in robot.get("specifications", {}).items():
                flat[f"spec_{label}"] = value
            flat_robots.append(flat)

        fieldnames = []
        for robot in flat_robots:
            for key in robot:
                if key not in fieldnames:
                    fieldnames.append(key)

        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_robots)

    return json_path, csv_path


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    if args.details and args.delay < DEFAULT_DELAY_SECONDS:
        raise SystemExit("--delay cannot be below the site's 5-second crawl delay")

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            # Avoid occasional stalled Brotli/chunked responses from the CDN.
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
    )

    print(f"Fetching public {args.category!r} robot list...")
    try:
        robots = read_category(session, args.category)
    except requests.RequestException as exc:
        raise SystemExit(
            f"Could not download the category page after "
            f"{DEFAULT_RETRIES} attempts: {exc}"
        ) from exc
    if args.limit:
        robots = robots[: args.limit]
    print(f"Found {len(robots)} robots.")

    if args.details:
        enrich_robots(
            session,
            robots,
            args.delay,
            args.output_dir,
            args.refresh,
        )

    json_path, csv_path = write_outputs(robots, args.output_dir, args.category)
    print(f"Saved JSON: {json_path}")
    print(f"Saved CSV:  {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
