"""target_not_found fail-closed gates for discovery/enrich quality."""

from __future__ import annotations

from web_extract import (
    PageContent,
    confirm_target_on_page,
    model_name_in_page,
    select_images_for_pages,
)


def _page(*, url: str, title: str = "", text: str = "", images: list[str] | None = None) -> PageContent:
    return PageContent(
        url=url,
        html="",
        title=title,
        text=text,
        images=images or [],
    )


def test_confirm_target_requires_name_on_page():
    page = _page(
        url="https://oem.example/products/arm-x7",
        title="Arm X7 industrial cobot",
        text="Payload 7kg. The Arm X7 reaches 900mm.",
    )
    assert model_name_in_page("Arm X7", "X7", page)
    assert confirm_target_on_page("Arm X7", "X7", page)


def test_confirm_target_fails_when_sibling_only():
    page = _page(
        url="https://oem.example/products/arm-x5",
        title="Arm X5",
        text="Our popular Arm X5 cobot. See also the lineup.",
    )
    # Sibling page: shared generic path token "arm" must not confirm X9.
    assert not confirm_target_on_page("Arm X9", "X9", page)
    assert not confirm_target_on_page("Cobot Zed-900", "Zed-900", page)


def test_confirm_target_accepts_url_slug_when_text_opaque():
    page = _page(
        url="https://oem.example/robots/rm65-force/",
        title="Product detail",
        text="Payload and reach listed in the table below.",
    )
    assert confirm_target_on_page("RM65 Force", "RM65-F", page)


def test_select_images_fail_closed_when_model_absent():
    page = _page(
        url="https://www.estun.com/gjjjqr/356.html",
        title="Some other model page",
        text="Catalog overview without the target SKU",
        images=[
            "https://www.estun.com/uploads/20250903/robot-hero.png",
            "https://www.estun.com/uploads/20250903/robot-side.png",
        ],
    )
    hero, gallery = select_images_for_pages(
        [page],
        product_url=page.url,
        name="iER8-720-MI-C",
        model_name="iER8-720-MI-C",
        tokens=["ier8", "720"],
    )
    assert hero == ""
    assert gallery == []
