"""Phase 0 of local-document intake: inventory a folder of vendor documents.

Context: scripts/research/docs/pdf_intake_plan.md. The input is a folder of
event-collected vendor files (PDF brochures/datasheets, PPTX decks, photos,
videos) rather than URLs, so nothing in the discovery pipeline applies yet.
Before any extraction happens we need to know, deterministically: what files
exist (minus duplicate copies), which company each one belongs to, what kind
of document it is, and whether its text is machine-readable or will need the
vision path.

This script is deliberately LLM-free. Company attribution uses a curated
hint table for files whose vendor is unambiguous from the name, plus signals
(page-1 text, domains, emails) recorded for a human/agent to resolve the
rest — a wrong guess here poisons every later phase, so anything not covered
by a hint stays `needs_review` instead of being fuzzily matched.

Investor material is excluded at this gate (`excluded` + reason) so no later
phase has to remember to skip it. Photos and videos are routed to `media`:
they are candidates for robot galleries, not data sources.

Read-only against prod (--prod-check does GET-only company/robot lookups so
the manifest records what already exists). Writes staging/intake/manifest.json
and prints a summary; imports nothing.

Usage (from scripts/research, PYTHONIOENCODING=utf-8):
    python intake_local_files.py                      # inventory only
    python intake_local_files.py --prod-check         # + prod existence check
    python intake_local_files.py --dir "D:\\other"    # different folder
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

DEFAULT_DIR = Path(
    r"C:\Users\tramk\Downloads\Robots and Companies"
    r"\Robots & Companies record - July 27 to July 28"
)
OUT_DIR = _HERE / "staging" / "intake"

# Filename → company, confident matches only. Patterns are matched against the
# filename (case-insensitive). Anything not matched here must be resolved from
# the recorded page-1 signals by a reviewer — do NOT add speculative entries;
# a file attributed to the wrong company survives every later validation step,
# because every later step trusts this one.
COMPANY_HINTS: list[tuple[str, str]] = [
    (r"flexiv|rizon|enlight|mobile robot platform fmr", "Flexiv"),
    (r"kepler", "Kepler Robotics"),
    (r"agibot|智元", "AGIBOT"),
    (r"fourier", "Fourier"),
    (r"galbot", "Galbot"),
    (r"geek\+|geek\+? company", "Geek+"),
    (r"deep robotics", "DEEP Robotics"),
    (r"elite-robots", "Elite Robots"),
    (r"spirit ai|千寻智能", "Spirit AI"),
    (r"x-humanoid|tien kung|tien yi", "X-Humanoid"),
    (r"limx", "LimX Dynamics"),
    (r"uls robotics", "ULS Robotics"),
    (r"astrall|hypertron", "Astrall Dynamics"),
    (r"genisom|智身科技", "Genisom"),
    (r"knowin|诺因智能", "Knowin"),
    (r"钛虎|ti5robot", "Ti5 Robot"),
    (r"魔法原子", "MagicLab"),
    (r"乐聚", "Leju Robotics"),
    (r"亿嘉和", "YIJIAHE"),
    (r"数字华夏|夏澜", "Digital Huaxia"),
    (r"跨维智能", "DexForce"),
    (r"星动纪元", "Robot Era"),
    (r"matrix_robotics|matrix robotics", "MATRIX Robotics"),
    (r"micbot", "MICBOT"),
    (r"tlibot", "TLIBOT"),
    (r"unixai", "UniX AI"),
    (r"bxi robotics", "BXI Robotics"),
    (r"daimon robotics", "Daimon Robotics"),
    (r"ai2_robotics", "AI2 Robotics"),
    (r"choho", "CHOHO"),
    (r"linkerbot", "Linkerbot"),
    (r"adam-u|en_adam", "PNDbotics"),
    (r"li-gong", "Li-Gong"),
    (r"hhs company", "HHS"),
    (r"动易科技|phybot", "PHYBOT (动易科技)"),
    (r"知行机器人", "知行机器人 (Zhixing)"),
    (r"悟时创新", "悟时创新 (Wushi)"),
    (r"云幕智造", "云幕智造 (Yunmu)"),
    (r"极佳", "极佳视界 (GigaAI)"),
    (r"智澄", "智澄 (Zhicheng)"),
    (r"天机智能", "天机智能 (Tianji)"),
    (r"启智", "启智 (Qizhi)"),
    (r"小月", "小月 (Xiaoyue)"),
    (r"bumi", "Bumi"),
    # Resolved from page-1 text during the 2026-08-12 inventory run:
    (r"2026 catalog en-ok", "MYACTUATOR"),          # p1: "Myactuator (Headquaters)"
    # tianjizn.com == prod company 931 "Tianji Gento"; MARVIN and Gento are two
    # product lines of the same vendor (confirmed via company 931's website).
    (r"marvin|天机智能", "Tianji Gento"),
    (r"^dax\.pdf", "Dax Robotics"),                  # p1: "Dax Robotics (Beijing)"
    (r"en_company_mp", "Keenon Robotics"),           # p1: "Keenon ... Investor Presentation"
    (r"en_双足版|en_宣传手册", "PNDbotics"),          # p1: pndbotics.com / Adam biped specs
    (r"k1 education", "Booster Robotics"),           # p1: sales@booster.tech
    (r"one-pager_sudo", "sudo (苏度)"),              # p1: sudo.ai
    (r"压缩 机器人宣传册", "HENGYUAN Embodied Intelligence"),  # p1: company name explicit
    (r"宣传单 - 英文", "QiO Robotics (Beijing Qiwu)"),  # p1: company overview names it
    # Resolved by rendering page 1 / slide 1 (image-only files), 2026-08-12:
    (r"20260304产品合集英文", "HighTorque Robotics"),   # 高擎, Pi Series/Mini Pi bipeds
    (r"gento", "Tianji Gento"),   # GENTO brand belongs to Tianji (prod company 931)
    (r"^product catalog - en", "Keenon Robotics"),      # product catalogue — usable
    (r"画册 英文版", "ZERITH"),                          # 零次方, zerith.ai, Hefei/Shenzhen
    (r"英文企业单页|英文数采单页|英文整机产品单页", "PsiBot"),  # 灵初智能, ψ-SynRobot
    (r"company and product overview", "Hangzhou Microrobot"),  # microrobotech.cn
    (r"公司介绍26版本", "Noetix Robotics"),              # 松延动力, noetixrobotics.com
]

# Known traps: vendors here that are component makers, not robot makers — the
# company gets flagged so review starts from the right posture (see the
# component-vendors incident: URL taxonomy catches it, AI score never does).
COMPONENT_VENDOR_SUSPECTS = {
    "CHOHO",       # 链条/chain drive manufacturer
    "MYACTUATOR",  # actuator maker (catalog p1 lists distributors, not robots)
}

EXCLUDE_HINTS: list[tuple[str, str]] = [
    # Business-plan / investor decks: not public marketing collateral. Never
    # extracted from, never uploaded anywhere public.
    (r"bp\s*1025|business plan", "investor material"),
    # Keenon file is literally titled "Investor Presentation" on page 1.
    (r"en_company_mp", "investor material"),
    # Event-wide brochure, not a vendor document.
    (r"^waic product brochure", "event brochure, not vendor material"),
    # Third-party industry report.
    (r"smart_robotics_report", "industry report, not vendor material"),
]

DOC_TYPE_HINTS: list[tuple[str, str]] = [
    (r"datasheet|spec sheet|specs", "datasheet"),
    (r"manual|产品手册|产品合集", "product_manual"),
    (r"catalog|catalogue", "catalogue"),
    (r"company (intro|introduction|profile)|公司介绍|公司简介|简介|企业介绍|企业单页", "company_profile"),
    (r"tri-?fold|三折页|折页|trifolder", "trifold_brochure"),
    (r"one-pager|单页", "one_pager"),
    (r"brochure|宣传册|宣传手册|宣传页|宣传单|画册", "brochure"),
    (r"solution|solutions", "solutions_deck"),
    (r"presentation|deck", "presentation"),
]

MEDIA_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov", ".avi"}
DOC_EXTS = {".pdf", ".pptx", ".ppt", ".docx"}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_DOMAIN_RE = re.compile(
    r"(?:https?://|www\.)([a-z0-9.-]+\.[a-z]{2,})|"
    r"\b([a-z0-9-]+\.(?:com|cn|ai|io|net|tech|robotics))\b",
    re.I,
)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@([\w-]+\.[\w.-]+)\b")
# Generic hosts that identify nobody.
_DOMAIN_NOISE = {"gmail.com", "qq.com", "163.com", "outlook.com", "wechat.com"}


@dataclass
class FileRecord:
    filename: str
    md5: str
    size_bytes: int
    kind: str                    # document | media | other
    ext: str = ""
    duplicate_of: str = ""       # canonical filename when this is a byte-copy
    company: str = ""            # from COMPANY_HINTS only
    company_source: str = ""     # "filename_hint" | ""
    needs_review: bool = False
    doc_type: str = ""
    language: str = ""           # en | zh | mixed
    excluded: bool = False
    excluded_reason: str = ""
    pdf_pages: int | None = None
    pdf_has_text_layer: bool | None = None
    pdf_page1_snippet: str = ""
    signals: dict = field(default_factory=dict)  # domains/emails from page 1
    probe_error: str = ""
    prod: dict = field(default_factory=dict)     # filled by --prod-check


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cjk_share(text: str) -> float:
    if not text:
        return 0.0
    letters = [c for c in text if c.isalpha() or _CJK_RE.match(c)]
    if not letters:
        return 0.0
    return sum(1 for c in letters if _CJK_RE.match(c)) / len(letters)


def language_of(name: str, page1: str) -> str:
    share = cjk_share(page1 or name)
    if share > 0.5:
        return "zh"
    if share > 0.05:
        return "mixed"
    return "en"


def probe_pdf(path: Path, rec: FileRecord) -> None:
    """Page count, text-layer presence, and page-1 identity signals.

    A brochure whose pages carry no text layer can only go down the vision
    path in Phase 2; knowing that now lets the extraction run be budgeted
    before it starts instead of discovered call-by-call.
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        rec.pdf_pages = len(reader.pages)
        sample = reader.pages[: min(3, len(reader.pages))]
        texts = []
        for page in sample:
            try:
                texts.append(page.extract_text() or "")
            except Exception:  # single bad page must not kill the probe
                texts.append("")
        avg_chars = sum(len(t) for t in texts) / max(1, len(texts))
        rec.pdf_has_text_layer = avg_chars > 200
        page1 = texts[0] if texts else ""
        rec.pdf_page1_snippet = re.sub(r"\s+", " ", page1).strip()[:600]
        domains = set()
        for m in _DOMAIN_RE.finditer(page1):
            d = (m.group(1) or m.group(2) or "").lower().lstrip("www.")
            if d and d not in _DOMAIN_NOISE:
                domains.add(d)
        emails = {m.group(1).lower() for m in _EMAIL_RE.finditer(page1)}
        if domains:
            rec.signals["domains"] = sorted(domains)
        if emails - _DOMAIN_NOISE:
            rec.signals["email_domains"] = sorted(emails - _DOMAIN_NOISE)
    except Exception as exc:  # noqa: BLE001 - record, don't crash the sweep
        rec.probe_error = f"{type(exc).__name__}: {exc}"


def classify(path: Path) -> FileRecord:
    name = path.name
    lower = name.lower()
    ext = path.suffix.lower()
    kind = "document" if ext in DOC_EXTS else "media" if ext in MEDIA_EXTS else "other"
    rec = FileRecord(
        filename=name,
        md5=md5_of(path),
        size_bytes=path.stat().st_size,
        kind=kind,
        ext=ext,
    )

    for pattern, reason in EXCLUDE_HINTS:
        if re.search(pattern, lower):
            rec.excluded = True
            rec.excluded_reason = reason
            break

    for pattern, company in COMPANY_HINTS:
        if re.search(pattern, lower):
            rec.company = company
            rec.company_source = "filename_hint"
            break

    for pattern, doc_type in DOC_TYPE_HINTS:
        if re.search(pattern, lower):
            rec.doc_type = doc_type
            break

    if kind == "document" and ext == ".pdf" and not rec.excluded:
        probe_pdf(path, rec)

    rec.language = language_of(name, rec.pdf_page1_snippet)
    rec.needs_review = kind == "document" and not rec.excluded and not rec.company
    return rec


def dedupe(records: list[FileRecord]) -> None:
    """Mark byte-identical copies; canonical = shortest filename (the one
    without the browser's ' (1)' suffix)."""
    by_hash: dict[str, list[FileRecord]] = {}
    for rec in records:
        by_hash.setdefault(rec.md5, []).append(rec)
    for group in by_hash.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: (len(r.filename), r.filename))
        canonical = group[0]
        for extra in group[1:]:
            extra.duplicate_of = canonical.filename


def prod_check(records: list[FileRecord]) -> None:
    """GET-only: for each hinted company, does it exist on prod and which
    robot names are already there (feeds the new-robots-only diff later)."""
    from api_client import ResearchApiClient

    client = ResearchApiClient()
    cache: dict[str, dict] = {}
    companies = sorted({r.company for r in records if r.company and not r.excluded})
    for name in companies:
        # Search on the latin part of the name; the API's search is latin-indexed.
        query = re.sub(r"[（(].*?[)）]", "", name).strip() or name
        try:
            matches = client.search_companies(query, page_size=5)
        except Exception as exc:  # noqa: BLE001
            cache[name] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        # The search endpoint returns an unrelated fallback list when nothing
        # matches (observed: 'ULS Robotics' -> Matex/Menlo/Aceii). Keep only
        # candidates sharing a real token with the query, else it's a no-match.
        # Generic words must not count as a shared token, or 'X Robotics'
        # matches every company named '<anything> Robotics'.
        generic = {"robotics", "robot", "robots", "technology", "tech",
                   "intelligence", "intelligent", "embodied", "dynamics",
                   "beijing", "shanghai", "shenzhen", "hangzhou", "co", "ltd"}
        q_tokens = {t for t in re.findall(r"[a-z0-9]{3,}", query.lower())} - generic
        matches = [
            m for m in matches
            if not q_tokens  # all-generic query: keep whatever came back
            or q_tokens & (set(re.findall(r"[a-z0-9]{3,}", (m.get("name") or "").lower())) - generic)
        ]
        entry: dict = {"matches": [
            {"id": m.get("id"), "name": m.get("name"), "slug": m.get("slug")}
            for m in matches[:5]
        ]}
        exact = [m for m in matches if (m.get("name") or "").strip().lower() == query.lower()]
        pick = exact[0] if exact else (matches[0] if len(matches) == 1 else None)
        if pick:
            entry["company_id"] = pick.get("id")
            try:
                robots = client.list_robots_for_company(pick["id"], page_size=200)
                entry["robot_names"] = sorted(
                    (r.get("name") or "") for r in robots if r.get("name")
                )
            except Exception as exc:  # noqa: BLE001
                entry["robots_error"] = f"{type(exc).__name__}: {exc}"
        cache[name] = entry
        print(f"  prod: {name}: "
              + (f"company_id={entry.get('company_id')}, "
                 f"{len(entry.get('robot_names', []))} robots"
                 if entry.get("company_id")
                 else f"{len(entry['matches'])} candidate matches"))
    for rec in records:
        if rec.company in cache:
            rec.prod = cache[rec.company]


def summarize(records: list[FileRecord]) -> str:
    docs = [r for r in records if r.kind == "document"]
    uniq_docs = [r for r in docs if not r.duplicate_of]
    lines = [
        f"files scanned:        {len(records)}",
        f"documents:            {len(docs)} ({len(uniq_docs)} unique, "
        f"{len(docs) - len(uniq_docs)} duplicate copies)",
        f"media files:          {sum(1 for r in records if r.kind == 'media')}",
        f"excluded:             {sum(1 for r in uniq_docs if r.excluded)}",
        f"company attributed:   {sum(1 for r in uniq_docs if r.company and not r.excluded)}",
        f"needs company review: {sum(1 for r in uniq_docs if r.needs_review)}",
        f"pdf image-only:       "
        f"{sum(1 for r in uniq_docs if r.pdf_has_text_layer is False)}"
        f" (vision-path in Phase 2)",
        f"probe errors:         {sum(1 for r in uniq_docs if r.probe_error)}",
    ]
    companies = sorted({r.company for r in uniq_docs if r.company and not r.excluded})
    lines.append(f"companies (hinted):   {len(companies)}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--prod-check", action="store_true")
    args = ap.parse_args()

    if not args.dir.is_dir():
        sys.exit(f"not a directory: {args.dir}")

    records = [classify(p) for p in sorted(args.dir.iterdir()) if p.is_file()]
    dedupe(records)
    if args.prod_check:
        print("checking prod for hinted companies ...")
        prod_check(records)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "manifest.json"
    out.write_text(
        json.dumps(
            {
                "source_dir": str(args.dir),
                "files": [asdict(r) for r in records],
                "component_vendor_suspects": sorted(COMPONENT_VENDOR_SUSPECTS),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(summarize(records))
    print(f"\nmanifest: {out}")
    for rec in records:
        if rec.needs_review:
            hint = ", ".join(rec.signals.get("domains", [])
                             + rec.signals.get("email_domains", []))
            print(f"  REVIEW: {rec.filename}" + (f"  [{hint}]" if hint else ""))


if __name__ == "__main__":
    main()
