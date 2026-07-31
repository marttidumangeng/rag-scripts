"""Derive `category_slugs` for a staged robot from signals the pipeline already has.

WHY THIS EXISTS
---------------
`missing_category` ("No category") sat on 317 of 1596 pending robots on
2026-07-31 because **nothing in the research pipeline ever wrote a category**.
The Gemini classifier in `robot_auto_research._classify_robot` produces
`movement_types`, `sub_category`, `uses` and `industries` — and `sub_category`
resolves to `RobotSubCategory` ("Applications"), which is a DIFFERENT model from
the `Category` M2M that `quality.missing_category` counts (`n_categories == 0`).
So every robot the pipeline touched came out of enrichment with zero categories
and the flag never cleared, no matter how many times it was re-enriched.

`remedy_missing_category` was registered for the flag but forced
`{"sub_category", "movement_type_keys"}` — neither of which can change
`n_categories` — so it reported FIXED while the flag stayed up, and the ledger
then blocked the retry. This module is the missing mapping.

CONTROLLED VOCABULARY, ON PURPOSE
---------------------------------
The server's bulk import resolves `category_slugs` with `get_or_create`, so any
free text becomes a new Category row. That is how prod ended up with 191
categories of which 135 are unused, including LLM sentence fragments like
"and grasp quality." and near-duplicates ("Ground / Ground Robot", "Grounded",
"Ground Robot"). Every slug below is one that ALREADY EXISTS on prod, and where
prod holds duplicates for one concept the highest-used row wins (counts measured
2026-07-31):

    aerial (50)          over  drone (18), uav (2)
    marine (22)          over  underwater-robot (21), underwater (5)
    exosuit (72)         over  exoskeleton-robots (6)
    mobile-robots (674)  over  autonomous-mobile-robots (18), amr (23, ct=all)
    medical-robots (22)  over  healthcare (15)

`ground` (224) is deliberately NOT emitted: it is the locomotion catch-all that
already absorbs ~60% of the ground-based catalog, so adding to it buys the robot
a chip but tells a browsing user nothing.
"""

from __future__ import annotations

import re

# Canonical slugs this module is allowed to emit. Anything not in here must never
# reach the importer, because the importer would CREATE it.
CANONICAL_CATEGORY_SLUGS: frozenset[str] = frozenset({
    "industrial-robot", "collaborative-robot", "scara-robot", "delta-robot",
    "robotic-arms", "end-effectors",
    "mobile-robots", "warehouse-robots", "logistics-robots", "delivery-robots",
    "humanoid", "legged-robots", "quadruped",
    "aerial", "marine",
    "service-robots", "consumer-robot", "home-robots", "food-service-robots",
    "cleaning-robots", "security", "military",
    "medical-robots", "exosuit",
    "agricultural-robots", "educational-robots", "research-robots",
    "computing-platform",
    "other",
})

MAX_CATEGORIES = 3
"""Cap per robot. Three is enough to say form + domain; more is noise that makes
every browse facet match everything."""

TEXT_MATCH_WINDOW = 600
"""How much of `text` the keyword rules may read. Callers pass whole product
pages, and an OEM nav/footer listing every product line the company sells would
otherwise tag every model with every form factor."""

# --- signal 1: movement_types (Gemini, high recall) -------------------------
_BY_MOVEMENT: dict[str, str] = {
    "wheeled": "mobile-robots",
    "tracked": "mobile-robots",
    "mobile": "mobile-robots",
    "legged": "legged-robots",
    "aerial": "aerial",
    "flying": "aerial",
    "swimming": "marine",
    "stationary": "industrial-robot",
}

# --- signal 2: sub_category (Gemini "Application" taxonomy) -----------------
_BY_SUB_CATEGORY: dict[str, str] = {
    "manufacturing-industrial": "industrial-robot",
    "logistics-warehouse": "warehouse-robots",
    "service-hospitality": "service-robots",
    "retail-customer-engagement": "service-robots",
    "healthcare": "medical-robots",
    "security": "security",
    "military": "military",
    "cleaning-facilities": "cleaning-robots",
    "agriculture": "agricultural-robots",
    "learning": "educational-robots",
    "personal-assistants": "consumer-robot",
    "companionship": "consumer-robot",
    "personal-mobility": "consumer-robot",
}

# --- signal 3: industry keys (weaker than sub_category, same idea) ----------
_BY_INDUSTRY: dict[str, str] = {
    "manufacturing": "industrial-robot",
    "logistics": "logistics-robots",
    "agriculture": "agricultural-robots",
    "healthcare": "medical-robots",
    "education": "educational-robots",
    "cleaning": "cleaning-robots",
    "security": "security",
    "defence": "military",
    "research": "research-robots",
    "space": "research-robots",
    "homes": "home-robots",
    "restaurants": "food-service-robots",
    "hotels": "service-robots",
    "retail": "service-robots",
}

# --- signal 4: use keys -----------------------------------------------------
_BY_USE: dict[str, str] = {
    "delivery": "delivery-robots",
    "palletizing": "industrial-robot",
    "assembly": "industrial-robot",
    "pick-and-place": "industrial-robot",
    "cleaning": "cleaning-robots",
    "sanitizing": "cleaning-robots",
    "surgery": "medical-robots",
    "patrol": "security",
    "monitoring": "security",
    "education": "educational-robots",
    "research": "research-robots",
    "inventory": "warehouse-robots",
}

# --- signal 5: name/product-page keywords ----------------------------------
# Ordered most-specific first. Each entry is (compiled pattern, slug). These
# catch the FORM factors the Gemini taxonomy has no field for — a SCARA and a
# delta are both "stationary/manufacturing-industrial" to the classifier.
_KEYWORD_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bscara\b"), "scara-robot"),
    (re.compile(r"\bdelta[ -]?(robot|picker)?\b"), "delta-robot"),
    (re.compile(r"\b(cobot|collaborative robot|collaborative arm)\b"), "collaborative-robot"),
    (re.compile(r"\b(exoskeleton|exosuit|exo-?suit)\b"), "exosuit"),
    (re.compile(r"\b(humanoid|bipedal|biped)\b"), "humanoid"),
    (re.compile(r"\b(quadruped|quadrupedal|four-?legged)\b"), "quadruped"),
    (re.compile(r"\b(gripper|end[- ]?effector|end[- ]of[- ]arm|eoat|robotic hand)\b"), "end-effectors"),
    (re.compile(r"\b(drone|uav|unmanned aerial|multirotor|quadcopter)\b"), "aerial"),
    (re.compile(r"\b(auv|rov|underwater|submarine|subsea|submersible)\b"), "marine"),
    (re.compile(r"\b(agv|amr|autonomous mobile robot|automated guided vehicle)\b"), "mobile-robots"),
    (re.compile(r"\b(forklift|pallet (jack|truck)|stacker)\b"), "warehouse-robots"),
    (re.compile(r"\b(surgical|surgery|rehabilitation|medical robot)\b"), "medical-robots"),
    (re.compile(r"\b(vacuum|mopping|floor scrub|window clean)\b"), "cleaning-robots"),
    (re.compile(r"\b(harvest|weeding|orchard|greenhouse|tractor)\b"), "agricultural-robots"),
    (re.compile(r"\b(stem|classroom|teaching robot|educational kit)\b"), "educational-robots"),
    (re.compile(r"\b(jetson|compute module|onboard computer|dev(elopment)? kit)\b"), "computing-platform"),
    (re.compile(r"\b(articulated (robot|arm)|6-?axis|七軸|robot arm|robotic arm)\b"), "robotic-arms"),
    (re.compile(r"\b(welding|painting|palletiz|machine tending|injection mould)\b"), "industrial-robot"),
]

# Concepts that make a broader sibling redundant. Keeping both just dilutes the
# facet: a robot tagged `quadruped` does not also need `legged-robots`.
_IMPLIES: dict[str, str] = {
    "humanoid": "legged-robots",
    "quadruped": "legged-robots",
    "scara-robot": "robotic-arms",
    "delta-robot": "robotic-arms",
    "collaborative-robot": "robotic-arms",
    "warehouse-robots": "logistics-robots",
}

# Rank decides which survive the MAX_CATEGORIES cap: form factor beats domain,
# domain beats locomotion, and `other` is always last.
_RANK: dict[str, int] = {
    "humanoid": 0, "quadruped": 0, "scara-robot": 0, "delta-robot": 0,
    "collaborative-robot": 0, "exosuit": 0, "end-effectors": 0,
    "computing-platform": 0,
    "industrial-robot": 1, "robotic-arms": 1,
    "medical-robots": 2, "agricultural-robots": 2, "educational-robots": 2,
    "warehouse-robots": 2, "delivery-robots": 2, "cleaning-robots": 2,
    "security": 2, "military": 2, "food-service-robots": 2, "research-robots": 2,
    "logistics-robots": 3, "service-robots": 3, "consumer-robot": 3,
    "home-robots": 3,
    "mobile-robots": 4, "legged-robots": 4, "aerial": 4, "marine": 4,
    "other": 9,
}


def _split_keys(raw: str | None) -> list[str]:
    """Pipe/comma-separated key strings -> lowercase keys."""
    if not raw:
        return []
    return [p.strip().lower() for p in re.split(r"[|,;]+", str(raw)) if p.strip()]


def _canonical(slug: str) -> str:
    """Normalize an incoming slug/name to a canonical slug, or '' if unknown.

    Accepts what the API returns for `categories` (display NAMES like
    "Industrial-Robot") as well as raw slugs, so an existing assignment
    round-trips instead of being re-created under a new slug.
    """
    key = re.sub(r"[^a-z0-9]+", "-", str(slug or "").lower()).strip("-")
    return key if key in CANONICAL_CATEGORY_SLUGS else ""


def derive_category_slugs(
    *,
    name: str = "",
    text: str = "",
    movement_type_keys: str = "",
    sub_category_slug: str = "",
    use_keys: str = "",
    industry_keys: str = "",
    existing: str = "",
    fallback: str = "",
) -> str:
    """Return a pipe-joined `category_slugs` string, or '' when nothing matched.

    `existing` is whatever the robot already carries (slugs or display names);
    it is kept and ranked alongside the derived ones so a re-run never drops a
    curated assignment.

    `fallback` is the slug to use when no signal matched at all — pass "other"
    ONLY from a caller that has actually read the product page and still cannot
    classify. Discovery must leave it blank: an unresearched robot tagged
    "Other" looks classified, which hides the gap from the reviewer instead of
    closing it.
    """
    picked: list[str] = []

    def add(slug: str) -> None:
        if slug and slug in CANONICAL_CATEGORY_SLUGS and slug not in picked:
            picked.append(slug)

    for raw in _split_keys(existing):
        add(_canonical(raw))

    # Keyword matching is deliberately two-stage and BOUNDED. Callers pass whole
    # product pages as `text`, and an OEM nav or footer listing "SCARA robots |
    # delta robots | cobots" would otherwise stamp all three form factors onto
    # every model on the site. The name is direct evidence about this model; the
    # body text is only consulted when the name says nothing, and then only the
    # opening window, which is the product blurb rather than the chrome.
    name_l = (name or "").lower()
    name_hits = [slug for pattern, slug in _KEYWORD_RULES if pattern.search(name_l)]
    for slug in name_hits:
        add(slug)
    if not name_hits:
        head = re.sub(r"\s+", " ", (text or ""))[:TEXT_MATCH_WINDOW].lower()
        for pattern, slug in _KEYWORD_RULES:
            if pattern.search(head):
                add(slug)

    add(_BY_SUB_CATEGORY.get((sub_category_slug or "").strip().lower(), ""))
    for key in _split_keys(use_keys):
        add(_BY_USE.get(key, ""))
    for key in _split_keys(industry_keys):
        add(_BY_INDUSTRY.get(key, ""))
    for key in _split_keys(movement_type_keys):
        add(_BY_MOVEMENT.get(key, ""))

    # Drop broader siblings made redundant by a more specific pick.
    redundant = {_IMPLIES[s] for s in picked if s in _IMPLIES}
    picked = [s for s in picked if s not in redundant]

    if not picked:
        fb = _canonical(fallback)
        if not fb:
            return ""
        picked = [fb]

    return "|".join(_ranked(picked)[:MAX_CATEGORIES])


def _ranked(picked: list[str]) -> list[str]:
    """Rank-then-discovery-order. The order index must be captured BEFORE the
    sort — `list.index` inside the key function reads the half-sorted list."""
    order = {slug: i for i, slug in enumerate(picked)}
    return sorted(picked, key=lambda s: (_RANK.get(s, 5), order[s]))


def categories_from_discovery_hints(hints: list[str] | None) -> str:
    """Map directory-source category labels (Robolist etc.) onto canonical slugs.

    Discovery knows a company's focus long before any robot page is fetched;
    that is a weak signal for the company, not a claim about a specific model,
    so only unambiguous labels map through.
    """
    picked: list[str] = []
    for hint in hints or []:
        slug = _canonical(hint)
        if not slug:
            slug = derive_category_slugs(name=str(hint)).split("|")[0]
        if slug and slug not in picked:
            picked.append(slug)
    return "|".join(_ranked(picked)[:MAX_CATEGORIES])
