"""Immutable evidence store for discovery/enrichment runs.

Saves page text and/or HTML, plus Gemini request/response payloads, alongside a
run so a batch can be re-validated or re-mapped without re-fetching OEM pages.

Layout:
  staging/evidence/{company_slug}/{run_id}/
    manifest.json
    pages/{host}_{sha12}.{html|txt}
    extract/{host}_{sha12}.json          # Gemini / extractor payloads
    meta.json                       # run metadata

Discovery (default): prefers raw HTML when available.
Enrichment (lean=True): saves parsed text by default; HTML only for audit cases
(target_not_found, low verify / grounded score).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_RESEARCH_DIR = Path(__file__).resolve().parent
EVIDENCE_ROOT = _RESEARCH_DIR / "staging" / "evidence"

# Defaults for retention sweep (override via env or kwargs).
DEFAULT_KEEP_RUNS = int(os.environ.get("EVIDENCE_KEEP_RUNS", "5"))
DEFAULT_MAX_BYTES = int(os.environ.get("EVIDENCE_MAX_BYTES_PER_COMPANY", str(200 * 1024 * 1024)))

# Grounded / verify scores below this trigger HTML retention on enrich.
LOW_VERIFY_SCORE = 50


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha12(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:12]


def _safe_host(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return re.sub(r"[^a-z0-9.-]+", "-", host) or "unknown"


def _attach_robot_id(entry: dict[str, Any], robot_id: int | str | None) -> dict[str, Any]:
    if robot_id is not None and str(robot_id).strip() != "":
        entry["robot_id"] = int(robot_id) if str(robot_id).isdigit() else robot_id
    return entry


class EvidenceStore:
    """Per-run evidence directory. Create once at start of discover/enrich."""

    def __init__(
        self,
        company_slug: str,
        *,
        run_id: str | None = None,
        pipeline: str = "discover",
    ) -> None:
        slug = re.sub(r"[^a-z0-9-]+", "-", (company_slug or "unknown").lower()).strip("-") or "unknown"
        self.company_slug = slug
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.pipeline = pipeline
        self.root = EVIDENCE_ROOT / slug / self.run_id
        self.pages_dir = self.root / "pages"
        self.extract_dir = self.root / "extract"
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.extract_dir.mkdir(parents=True, exist_ok=True)
        self._entries: list[dict[str, Any]] = []
        self._meta: dict[str, Any] = {
            "company_slug": slug,
            "run_id": self.run_id,
            "pipeline": pipeline,
            "started_at": _now_iso(),
            "finished_at": None,
        }
        self._write_meta()

    def _write_meta(self) -> None:
        (self.root / "meta.json").write_text(
            json.dumps(self._meta, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _write_manifest(self) -> None:
        payload = {
            "company_slug": self.company_slug,
            "run_id": self.run_id,
            "pipeline": self.pipeline,
            "started_at": self._meta.get("started_at"),
            "finished_at": self._meta.get("finished_at"),
            "entries": self._entries,
        }
        (self.root / "manifest.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def save_page(
        self,
        url: str,
        *,
        html: str = "",
        text: str = "",
        title: str = "",
        source: str = "fetch",
        robot_id: int | str | None = None,
        lean: bool = False,
        force_html: bool = False,
    ) -> dict[str, Any]:
        """Persist page body.

        lean=True (enrich default): store parsed text as .txt unless force_html.
        lean=False (discover default): prefer HTML when present, else text.
        """
        html_body = (html or "").strip()
        text_body = (text or "").strip()
        if lean and not force_html:
            body = text_body or html_body
            ext = "txt"
            content_type = "text/plain"
        elif force_html or html_body:
            body = html_body or text_body
            ext = "html" if html_body else "txt"
            content_type = "text/html" if ext == "html" else "text/plain"
        else:
            body = text_body
            ext = "txt"
            content_type = "text/plain"

        digest = _sha12(f"{url}\n{body[:2000]}")
        host = _safe_host(url)
        filename = f"{host}_{digest}.{ext}"
        path = self.pages_dir / filename
        if not path.exists():
            path.write_text(body, encoding="utf-8", errors="replace")
        entry = _attach_robot_id(
            {
                "kind": "page",
                "url": url,
                "title": title or "",
                "source": source,
                "path": str(path.relative_to(self.root)).replace("\\", "/"),
                "sha12": digest,
                "bytes": path.stat().st_size,
                "content_type": content_type,
                "lean": bool(lean and not force_html),
                "saved_at": _now_iso(),
            },
            robot_id,
        )
        self._entries.append(entry)
        self._write_manifest()
        return entry

    def save_extract(
        self,
        url: str,
        payload: Any,
        *,
        extractor: str = "gemini",
        robot_id: int | str | None = None,
    ) -> dict[str, Any]:
        """Persist extractor output (Gemini JSON request/response, etc.) for replay."""
        blob = json.dumps(payload, ensure_ascii=False, indent=2)
        digest = _sha12(f"{url}\n{extractor}\n{blob[:2000]}")
        host = _safe_host(url)
        filename = f"{host}_{digest}.json"
        path = self.extract_dir / filename
        if not path.exists():
            path.write_text(blob + "\n", encoding="utf-8")
        entry = _attach_robot_id(
            {
                "kind": "extract",
                "url": url,
                "extractor": extractor,
                "path": str(path.relative_to(self.root)).replace("\\", "/"),
                "sha12": digest,
                "bytes": path.stat().st_size,
                "saved_at": _now_iso(),
            },
            robot_id,
        )
        self._entries.append(entry)
        self._write_manifest()
        return entry

    def save_pdf(
        self,
        url: str,
        data: bytes,
        *,
        source: str = "fetch",
        robot_id: int | str | None = None,
    ) -> dict[str, Any]:
        """Persist a raw PDF (datasheet) alongside HTML evidence for replay."""
        digest = hashlib.sha1(data[:8192] if data else b"").hexdigest()[:12]
        if not data:
            digest = _sha12(url)
        host = _safe_host(url)
        filename = f"{host}_{digest}.pdf"
        path = self.pages_dir / filename
        if not path.exists():
            path.write_bytes(data or b"")
        entry = _attach_robot_id(
            {
                "kind": "page",
                "url": url,
                "title": "",
                "source": source,
                "path": str(path.relative_to(self.root)).replace("\\", "/"),
                "sha12": digest,
                "bytes": path.stat().st_size,
                "content_type": "application/pdf",
                "saved_at": _now_iso(),
            },
            robot_id,
        )
        self._entries.append(entry)
        self._write_manifest()
        return entry

    def link_robot(
        self,
        page_url: str,
        robot_name: str,
        staging_file: str = "",
        *,
        robot_id: int | str | None = None,
    ) -> None:
        """Record which staged robot was produced from which page evidence."""
        self._entries.append(
            _attach_robot_id(
                {
                    "kind": "robot_link",
                    "url": page_url,
                    "robot_name": robot_name,
                    "staging_file": staging_file,
                    "saved_at": _now_iso(),
                },
                robot_id,
            )
        )
        self._write_manifest()

    def note_target_not_found(
        self,
        page_url: str,
        robot_name: str,
        detail: str = "",
        *,
        robot_id: int | str | None = None,
        page_paths: list[str] | None = None,
    ) -> None:
        entry = _attach_robot_id(
            {
                "kind": "target_not_found",
                "url": page_url,
                "robot_name": robot_name,
                "detail": detail,
                "saved_at": _now_iso(),
            },
            robot_id,
        )
        if page_paths:
            entry["page_paths"] = list(page_paths)
        self._entries.append(entry)
        self._write_manifest()

    def finish(self, **extra: Any) -> Path:
        self._meta["finished_at"] = _now_iso()
        self._meta.update(extra)
        self._write_meta()
        self._write_manifest()
        return self.root

    @property
    def relative_root(self) -> str:
        try:
            return str(self.root.relative_to(_RESEARCH_DIR)).replace("\\", "/")
        except ValueError:
            return str(self.root)


def load_manifest(company_slug: str, run_id: str) -> dict[str, Any]:
    path = EVIDENCE_ROOT / company_slug / run_id / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def list_runs(company_slug: str) -> list[str]:
    root = EVIDENCE_ROOT / company_slug
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def read_evidence_file(company_slug: str, run_id: str, relative_path: str) -> str:
    path = EVIDENCE_ROOT / company_slug / run_id / relative_path
    return path.read_text(encoding="utf-8", errors="replace")


def company_evidence_bytes(company_slug: str) -> int:
    root = EVIDENCE_ROOT / company_slug
    if not root.is_dir():
        return 0
    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def sweep_company_evidence(
    company_slug: str,
    *,
    keep_runs: int = DEFAULT_KEEP_RUNS,
    max_total_bytes: int | None = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    """Delete older evidence runs for a company beyond keep_runs and/or size cap.

    Runs are ordered by directory name (ISO-like run_id timestamps sort well).
    Always keeps the newest `keep_runs`. If still over max_total_bytes, deletes
    oldest remaining runs until under the cap (never deletes the newest run).
    """
    slug = re.sub(r"[^a-z0-9-]+", "-", (company_slug or "unknown").lower()).strip("-") or "unknown"
    root = EVIDENCE_ROOT / slug
    deleted: list[str] = []
    if not root.is_dir():
        return {"company_slug": slug, "deleted": deleted, "kept": [], "bytes": 0}

    runs = sorted(
        [p for p in root.iterdir() if p.is_dir()],
        key=lambda p: p.name,
    )
    while keep_runs >= 0 and len(runs) > keep_runs:
        victim = runs.pop(0)
        shutil.rmtree(victim, ignore_errors=True)
        deleted.append(victim.name)

    if max_total_bytes is not None and max_total_bytes > 0:
        while len(runs) > 1 and company_evidence_bytes(slug) > max_total_bytes:
            victim = runs.pop(0)
            shutil.rmtree(victim, ignore_errors=True)
            deleted.append(victim.name)

    kept = [p.name for p in runs if p.exists()]
    return {
        "company_slug": slug,
        "deleted": deleted,
        "kept": kept,
        "bytes": company_evidence_bytes(slug),
    }


def sweep_all_evidence(
    *,
    keep_runs: int = DEFAULT_KEEP_RUNS,
    max_total_bytes: int | None = DEFAULT_MAX_BYTES,
) -> list[dict[str, Any]]:
    if not EVIDENCE_ROOT.is_dir():
        return []
    return [
        sweep_company_evidence(p.name, keep_runs=keep_runs, max_total_bytes=max_total_bytes)
        for p in sorted(EVIDENCE_ROOT.iterdir())
        if p.is_dir()
    ]
