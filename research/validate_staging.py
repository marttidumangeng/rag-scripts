"""Validate staging JSON before import."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from schema import StagedCompany, StagedRobot

_URL_RE = re.compile(r"^https?://", re.I)
_ERROR_TEXT_RE = re.compile(
    r"(?:4\d\d|5\d\d)\s*(?:bad\s+gateway|gateway|bad\s+request|error)|"
    r"bad\s+gateway|browser\s+working|host\s+error|wts\s+working|"
    r"captcha|cloudflare|page\s+not\s+found|service\s+unavailable",
    re.I,
)
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

_REQUIRED_TEXT_FIELDS = ("purpose", "features", "tags")


def _has_text(value: Any) -> bool:
    if isinstance(value, (list, tuple, set)):
        return any(str(item or "").strip() for item in value)
    return bool(str(value or "").strip())


def _contains_error_text(value: Any) -> bool:
    return bool(_ERROR_TEXT_RE.search(str(value or "")))


def _contains_unreviewed_cjk(robot: StagedRobot, value: Any) -> bool:
    # CJK is valid when the source is explicitly non-English; it is a contamination
    # warning when an English output record still contains source-language fragments.
    locale = (robot.source_locale or "").strip().lower()
    return locale in {"", "en", "en-us", "en-gb"} and bool(_CJK_RE.search(str(value or "")))

# `purpose` is a short task statement ("Hotel room-service delivery"); `description` is the
# prose overview. The auto-research pipeline used to set purpose = description.split(".")[0],
# which duplicated the description across the catalog (IIT 9/11, Kawasaki 56/56, Estun 92/264).
# Mirrors robots/quality.py::purpose_duplicates_description on the server — keep the two in
# sync; the server flags stored rows, this blocks new ones at staging time.
PURPOSE_DUP_MIN_CHARS = 25
PURPOSE_DUP_RATIO = 0.85


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower()).rstrip(". ")


def _first_sentence(value: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", (value or "").strip())
    return parts[0] if parts else (value or "")


def purpose_duplicates_description(purpose: str, description: str) -> str:
    """Return the duplication kind ("exact"/"first_sentence"/"substring"/"near"), else "".

    Short purposes are exempt from the substring/near rules — a real task phrase like
    "Welding" legitimately appears inside the description.
    """
    p, d = _normalize_text(purpose), _normalize_text(description)
    if not p or not d:
        return ""
    if p == d:
        return "exact"
    if p == _normalize_text(_first_sentence(description)):
        return "first_sentence"
    if len(p) >= PURPOSE_DUP_MIN_CHARS and p in d:
        return "substring"
    if len(p) >= PURPOSE_DUP_MIN_CHARS and difflib.SequenceMatcher(None, p, d).ratio() >= PURPOSE_DUP_RATIO:
        return "near"
    return ""


@dataclass
class ValidationIssue:
    level: str  # error | warning
    field: str
    message: str


@dataclass
class ValidationResult:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "error"]

    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "warning"]


def _is_url(value: str) -> bool:
    if not value:
        return False
    parsed = urlparse(value.strip())
    return bool(parsed.scheme in ("http", "https") and parsed.netloc)


def validate_robot(data: dict[str, Any] | StagedRobot) -> ValidationResult:
    robot = data if isinstance(data, StagedRobot) else StagedRobot.from_dict(data)
    issues: list[ValidationIssue] = []

    if not robot.name.strip():
        issues.append(ValidationIssue("error", "name", "Robot name is required."))

    if not robot.company_slug.strip() and not robot.company_name.strip():
        issues.append(ValidationIssue(
            "error", "company", "company_slug or company_name is required.",
        ))

    if not robot.description.strip() and not robot.purpose.strip():
        issues.append(ValidationIssue(
            "error", "description", "At least one of description or purpose is required.",
        ))

    # Mandatory first-pass content gates. These are low-hanging fields and must not
    # be silently left as unresolved warnings by the discovery importer.
    if not robot.purpose.strip():
        issues.append(ValidationIssue("error", "purpose", "Purpose is missing."))
    if not robot.features.strip():
        issues.append(ValidationIssue("error", "features", "Features are missing."))
    if not robot.tags.strip():
        issues.append(ValidationIssue("error", "tags", "Tags are missing."))
    if not (robot.industry_keys.strip() or robot.industries_other.strip()):
        issues.append(ValidationIssue("error", "industries", "Uses/industries are missing."))
    if not (robot.use_keys.strip() or robot.uses_other.strip()):
        issues.append(ValidationIssue("error", "uses", "Uses/industries are missing."))

    text_fields = {
        "name": robot.name,
        "description": robot.description,
        "purpose": robot.purpose,
        "features": robot.features,
        "strengths": robot.strengths,
        "weaknesses": robot.weaknesses,
        "notes": robot.notes,
    }
    for field_name, value in text_fields.items():
        if _contains_error_text(value):
            issues.append(ValidationIssue("error", field_name, "Error-page or gateway text detected."))
        if _contains_unreviewed_cjk(robot, value):
            issues.append(ValidationIssue("error", field_name, "Non-English source text remains in an English output record."))

    dup_kind = purpose_duplicates_description(robot.purpose, robot.description)
    if dup_kind:
        issues.append(ValidationIssue(
            "error", "purpose",
            f"purpose repeats description ({dup_kind}) — purpose must be a short task "
            f"statement (e.g. 'Hotel room-service delivery'), not a copy of the description. "
            f"Leave it blank rather than duplicating.",
        ))

    if not robot.sources:
        issues.append(ValidationIssue(
            "error", "sources", "At least one source URL is required.",
        ))
    else:
        for idx, src in enumerate(robot.sources):
            if not _is_url(src.url):
                issues.append(ValidationIssue(
                    "error", f"sources[{idx}].url", f"Invalid source URL: {src.url!r}",
                ))

    if robot.url and not _is_url(robot.url):
        issues.append(ValidationIssue("error", "url", f"Invalid product URL: {robot.url!r}"))

    if robot.image and not _is_url(robot.image):
        issues.append(ValidationIssue("warning", "image", f"Invalid image URL: {robot.image!r}"))

    if not robot.manufacturer_country_code.strip():
        issues.append(ValidationIssue("warning", "manufacturer_country_code", "Country code missing."))

    if not robot.image.strip():
        issues.append(ValidationIssue("warning", "image", "Image URL missing."))

    # These are two DIFFERENT models and only one of them clears the server's
    # `missing_category` flag: `category_slugs` populates the `categories` M2M
    # that `quality.py` counts, while `sub_category_slug` resolves to
    # `RobotSubCategory` ("Applications"). Treating a sub-category as a
    # substitute is what hid the gap — 317 pending robots had a sub-category
    # and no category on 2026-07-31. Warn on each independently.
    if not robot.category_slugs.strip():
        issues.append(ValidationIssue(
            "error", "category_slugs",
            "No category assigned — a sub-category does not clear the category gap.",
        ))
    if not robot.sub_category_slug.strip():
        issues.append(ValidationIssue("warning", "sub_category_slug", "No sub-category (Application) assigned."))

    # Numeric fields with low confidence should have research_notes
    for field_name, level in robot.confidence.items():
        if level == "low" and not robot.research_notes:
            issues.append(ValidationIssue(
                "warning", field_name,
                f"Field {field_name} marked low confidence but research_notes is empty.",
            ))

    numeric_fields = {
        "weight_kg": robot.weight_kg,
        "price_min": robot.price_min,
        "price_max": robot.price_max,
        "height_mm": robot.height_mm,
        "width_mm": robot.width_mm,
        "length_mm": robot.length_mm,
    }
    for fname, fval in numeric_fields.items():
        if fval is not None and not robot.research_notes and fname not in robot.confidence:
            issues.append(ValidationIssue(
                "warning", fname,
                f"Numeric field {fname} set without confidence or research_notes citation.",
            ))

    return ValidationResult(ok=not any(i.level == "error" for i in issues), issues=issues)


def validate_company(data: dict[str, Any] | StagedCompany) -> ValidationResult:
    company = data if isinstance(data, StagedCompany) else StagedCompany.from_dict(data)
    issues: list[ValidationIssue] = []

    if not company.name.strip():
        issues.append(ValidationIssue("error", "name", "Company name is required."))

    if not company.sources:
        issues.append(ValidationIssue(
            "error", "sources", "At least one source URL is required.",
        ))
    else:
        for idx, src in enumerate(company.sources):
            if not _is_url(src.url):
                issues.append(ValidationIssue(
                    "error", f"sources[{idx}].url", f"Invalid source URL: {src.url!r}",
                ))

    if company.website and not _is_url(company.website):
        issues.append(ValidationIssue("warning", "website", f"Invalid website URL: {company.website!r}"))

    has_patch_field = any([
        company.description,
        company.website,
        company.hq_address,
        company.country_code or company.country_id,
        company.contact_info,
        company.leaders_roles,
        company.employee_count,
        company.employee_min is not None,
        company.employee_max is not None,
    ])
    if not has_patch_field:
        issues.append(ValidationIssue(
            "warning", "fields", "No patch fields populated — nothing to update.",
        ))

    return ValidationResult(ok=not any(i.level == "error" for i in issues), issues=issues)


def validate_robot_batch(records: list[dict[str, Any]]) -> ValidationResult:
    """Validate a batch; reject duplicate (company_slug, name) pairs."""
    issues: list[ValidationIssue] = []
    seen: set[str] = set()
    any_error = False

    for idx, record in enumerate(records):
        result = validate_robot(record)
        for issue in result.issues:
            issues.append(ValidationIssue(issue.level, f"[{idx}] {issue.field}", issue.message))
        if not result.ok:
            any_error = True

        robot = StagedRobot.from_dict(record)
        try:
            from .map_to_bulk_import import canonical_robot_key
        except ImportError:
            from map_to_bulk_import import canonical_robot_key
        key = canonical_robot_key(robot.name, robot.company_slug or robot.company_name)
        if key in seen:
            issues.append(ValidationIssue(
                "error", f"[{idx}] duplicate", f"Duplicate robot in batch: {robot.name}",
            ))
            any_error = True
        seen.add(key)

    return ValidationResult(ok=not any_error, issues=issues)
