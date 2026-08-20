from __future__ import annotations
from pathlib import Path

path = Path(r"C:\Github_Personal\robot-ai-geek\scripts\research\overnight_queue_enrich.py")
source = path.read_text(encoding="utf-8")

helper = r'''

# Quality gates added after the 2026-08 enrichment audit. These are intentionally
# conservative: reject known error-page text and non-primary-eligible media, but
# never invent replacement facts or overwrite a good existing field.
_QUALITY_BAD_TEXT_PATTERNS = (
    r"502\\s+Bad\\s+Gateway", r"Bad\\s+Gateway", r"Browser\\s+Working",
    r"Host\\s+Error", r"发生什么事了", r"网站服务无法请求", r"WTS\\s+Working",
    r"Error\\s*\\d{3}", r"404\\s+Not\\s+Found", r"Internal\\s+Server\\s+Error",
    r"Access\\s+Denied", r"Just\\s+a\\s+moment", r"captcha", r"cloudflare",
)
_QUALITY_BAD_MEDIA_CLASSES = {"technical_drawing", "cad_screenshot", "diagram", "logo_or_chrome", "wrong_model", "unknown"}


def _quality_gate_staged(staged, base):
    import re as _quality_re
    for _field in ("description", "purpose", "features", "notes", "strengths", "weaknesses"):
        _value = getattr(staged, _field, "") or ""
        if any(_quality_re.search(_pattern, str(_value), flags=_quality_re.I) for _pattern in _QUALITY_BAD_TEXT_PATTERNS):
            _fallback = getattr(base, _field, "") or ""
            if not any(_quality_re.search(_pattern, str(_fallback), flags=_quality_re.I) for _pattern in _QUALITY_BAD_TEXT_PATTERNS):
                setattr(staged, _field, _fallback)
            else:
                setattr(staged, _field, "")
    _images = getattr(staged, "images", None)
    if isinstance(_images, list):
        _valid = []
        for _candidate in _images:
            if not isinstance(_candidate, dict):
                continue
            _media_class = str(_candidate.get("media_class") or "unknown").strip().lower()
            _eligible = _candidate.get("is_primary_eligible")
            _score = _candidate.get("confidence_score")
            try:
                _score_ok = _score is not None and float(_score) >= 70
            except (TypeError, ValueError):
                _score_ok = False
            if _media_class in _QUALITY_BAD_MEDIA_CLASSES or _eligible is False or (_score is not None and not _score_ok):
                continue
            _valid.append(_candidate)
        setattr(staged, "images", _valid)
        if not _valid:
            _fallback_image = getattr(base, "image", "") or ""
            setattr(staged, "image", _fallback_image)
        else:
            _first_url = str(_valid[0].get("url") or _valid[0].get("image") or "").strip()
            if _first_url:
                setattr(staged, "image", _first_url)
    return staged
'''

if "_QUALITY_BAD_TEXT_PATTERNS" not in source:
    marker = "def enrich_company("
    if marker not in source:
        raise SystemExit("Could not locate enrich_company marker")
    source = source.replace(marker, helper + "\n\n" + marker, 1)

needle = "            validation = validate_robot(merged)\n"
replacement = "            merged = _quality_gate_staged(merged, base)\n            validation = validate_robot(merged)\n"
if needle not in source:
    raise SystemExit("Could not locate validation call")
if replacement not in source:
    source = source.replace(needle, replacement, 1)

path.write_text(source, encoding="utf-8")
print("patched", path)
