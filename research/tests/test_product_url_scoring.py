"""--product-pages-only must not discard descriptive product slugs.

The strict filter penalises long slugs (-20 over five words) on the theory that
they are blog posts. akarobotics.com files every robot under a long descriptive
slug — /products/wallhiker-w-06-uhp-water-blasting-magnetic-crawler-robot/ is
eight words — so the penalty took each one from +9 to -11 and the crawler
discarded all 12 products before reading a single page. A URL the site itself
files under a product container is exempt; the blog penalty still applies
everywhere else.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from discover_robots import _in_product_container, _score_url_as_product  # noqa: E402

AKA = "https://www.akarobotics.com/products/wallhiker-w-06-uhp-water-blasting-magnetic-crawler-robot/"


class TestProductContainer:
    @pytest.mark.parametrize("url", [
        "https://x.com/products/some-very-long-descriptive-robot-name-here/",
        "https://x.com/product/arm-7-axis/",
        "https://x.com/robots/humanoid-general-purpose-worker/",
        "https://x.com/catalog/mobile-robot-500kg-payload/",
        AKA,
    ])
    def test_recognised(self, url):
        assert _in_product_container(url) is True

    @pytest.mark.parametrize("url", [
        "https://x.com/products/",                      # the index itself, nothing below
        "https://x.com/blog/our-new-robot/",
        "https://x.com/robot-restaurant-singapore/",     # 'robot' is part of a slug, not a segment
        "https://x.com/",
    ])
    def test_not_recognised(self, url):
        assert _in_product_container(url) is False


class TestStrictScoring:
    def test_long_product_slug_survives_strict_mode(self):
        assert _score_url_as_product(AKA, strict=True) > 0

    def test_long_product_slug_scores_same_strict_or_not(self):
        assert _score_url_as_product(AKA, strict=True) == _score_url_as_product(AKA, strict=False)

    @pytest.mark.parametrize("url", [
        "https://x.com/blog/why-we-built-a-robot-for-warehouses-in-2026/",
        "https://x.com/case-study/acme-deploys-fifty-robots-across-europe/",
    ])
    def test_blogs_and_case_studies_still_excluded(self, url):
        assert _score_url_as_product(url, strict=True) < 0

    def test_long_non_product_slug_still_penalised(self):
        loose = "https://x.com/how-our-warehouse-automation-changed-everything-last-year/"
        assert _score_url_as_product(loose, strict=True) < _score_url_as_product(loose, strict=False)

    def test_static_assets_still_rejected_inside_a_product_container(self):
        assert _score_url_as_product("https://x.com/products/spec-sheet.pdf", strict=True) == -10
