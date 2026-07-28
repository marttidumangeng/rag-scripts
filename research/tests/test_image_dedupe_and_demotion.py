"""Regression tests for image de-duplication and cross-page demotion.

Both defects below shipped real damage and were caught only by hand-built contact
sheets during the 2026-07 greenfield runs:

  * Shopify size variants were not collapsed, so a gallery of ONE asset served at
    _490x/_490x@2x/_70x/... looked like 6 distinct photos (Makeblock mBot2, mTiny).
  * Site-wide graphics were staged as product photos, because the in-loop guard
    only counts robots staged EARLIER — the first claimants keep the asset
    (RobCo: a humanoid "Concept-Robot" render became the hero of 5-axis arms).

URLs here are the real ones from those runs.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from discover_robots import (  # noqa: E402
    _dedupe_cdn_transforms,
    _demote_cross_page_images,
    _image_base_key,
    _img_url,
)

SHOP = "https://www.makeblock.com/cdn/shop/products/"
FLOW = "https://cdn.prod.website-files.com/68f2341d705f07db40d6f962/"


class TestWebflowVariantDedupe:
    """RobCo (Webflow) serves -p-<width> responsive variants of one asset."""

    def test_webflow_p_width_variants_collapse(self):
        urls = [
            FLOW + "69e0efdf_Concept-Robot-RobCo-Alfie-2026-p-500.webp",
            FLOW + "69e0efdf_Concept-Robot-RobCo-Alfie-2026-p-1080.webp",
            FLOW + "69e0efdf_Concept-Robot-RobCo-Alfie-2026-p-1600.webp",
            FLOW + "69e0efdf_Concept-Robot-RobCo-Alfie-2026.webp",
        ]
        assert _dedupe_cdn_transforms(urls) == [FLOW + "69e0efdf_Concept-Robot-RobCo-Alfie-2026.webp"]

    def test_largest_webflow_variant_wins_without_original(self):
        small = FLOW + "Elegante_Elise-p-500.png"
        big = FLOW + "Elegante_Elise-p-1600.png"
        assert _dedupe_cdn_transforms([small, big]) == [big]

    def test_double_encoded_variant_collapses_with_original(self):
        """Real RobCo: Webflow serves -p- variants DOUBLE percent-encoded, so the
        same render appeared twice ('%20' vs '%2520') and survived dedupe."""
        original = FLOW + "68f2341d_Elegante%20Elise%20(1).png"
        variant = FLOW + "68f2341d_Elegante%2520Elise%2520(1)-p-2000.png"
        assert _image_base_key(original) == _image_base_key(variant)
        # the plain original wins, and stays percent-encoded (must remain fetchable)
        assert _dedupe_cdn_transforms([original, variant]) == [original]


class TestPathPrefixTransforms:
    """Saab Seaeye puts the resize in the DIRECTORY: /cdn/w_330/x.jpg is a render
    of /uploads/x.jpg — suffix-based keys can't see it (SR20 staged one image twice)."""

    SE = "https://www.saabseaeye.com"

    def test_cdn_path_transform_collapses_with_uploads_original(self):
        original = self.SE + "/uploads/hi-res-2.png"
        transform = self.SE + "/cdn/w_330/hi-res-2.png"
        assert _dedupe_cdn_transforms([original, transform]) == [original]
        # order-independent
        assert _dedupe_cdn_transforms([transform, original]) == [original]

    def test_largest_path_transform_wins_without_original(self):
        small = self.SE + "/cdn/w_330/hi-res-2.png"
        big = self.SE + "/cdn/w_1600/hi-res-2.png"
        assert _dedupe_cdn_transforms([small, big]) == [big]

    def test_different_files_under_transform_paths_are_kept(self):
        a = self.SE + "/cdn/w_330/hi-res-1.png"
        b = self.SE + "/cdn/w_330/hi-res-2.png"
        c = self.SE + "/cdn/w_330/lo-res-2.png"
        assert len(_dedupe_cdn_transforms([a, b, c])) == 3

    def test_same_filename_in_different_dirs_survives_without_transform(self):
        """No path-transform in play => do NOT merge on bare filename."""
        a = self.SE + "/uploads/2023/hero.jpg"
        b = self.SE + "/uploads/2024/hero.jpg"
        assert len(_dedupe_cdn_transforms([a, b])) == 2


class TestStagedEntryShapes:
    """Staged `images[]` entries are candidate dicts; `image` is a plain string.
    Mixing the two crashed the demotion pass on real RobCo data
    (AttributeError: 'dict' object has no attribute 'split')."""

    def test_img_url_handles_dict_and_string(self):
        assert _img_url({"url": "https://x/a.png", "confidence_score": 90}) == "https://x/a.png"
        assert _img_url("https://x/a.png") == "https://x/a.png"
        assert _img_url(None) == "" and _img_url({}) == ""

    def test_base_key_accepts_candidate_dict(self):
        assert _image_base_key({"url": SHOP + "a_490x@2x.progressive.webp.jpg"}) == \
               _image_base_key(SHOP + "a.png")


class TestShopifyVariantDedupe:
    def test_shopify_size_variants_collapse_to_one_asset(self):
        # Real mBot gallery: one render, six Shopify transforms.
        urls = [
            SHOP + "2mbotpink_490x.progressive.webp.jpg",
            SHOP + "2mbotpink_490x@2x.progressive.webp.jpg",
            SHOP + "2mbotpink_490x@3x.progressive.webp.jpg",
            SHOP + "2mbotpink_70x.progressive.webp.jpg",
            SHOP + "2mbotpink_70x@2x.progressive.webp.jpg",
        ]
        assert len(_dedupe_cdn_transforms(urls)) == 1

    def test_plain_original_beats_sized_variants(self):
        urls = [
            SHOP + "2mbotpink_70x.progressive.webp.jpg",
            SHOP + "2mbotpink.jpg",
            SHOP + "2mbotpink_490x@2x.progressive.webp.jpg",
        ]
        assert _dedupe_cdn_transforms(urls) == [SHOP + "2mbotpink.jpg"]

    def test_largest_variant_wins_when_no_original(self):
        small = SHOP + "mBot2_70x.progressive.webp.jpg"
        big = SHOP + "mBot2_490x@2x.progressive.webp.jpg"
        assert _dedupe_cdn_transforms([small, big]) == [big]

    def test_cache_buster_does_not_split_an_asset(self):
        urls = [SHOP + "mTiny.webp?v=1766999499", SHOP + "mTiny_490x.webp?v=1710147715"]
        assert len(_dedupe_cdn_transforms(urls)) == 1

    def test_distinct_assets_are_not_merged(self):
        urls = [SHOP + "mBot2_490x.jpg", SHOP + "mTiny_490x.jpg", SHOP + "CodeyRocky_490x.jpg"]
        assert len(_dedupe_cdn_transforms(urls)) == 3

    def test_wordpress_variants_still_collapse(self):
        # Pre-existing behaviour must not regress.
        base = "https://www.ufactory.cc/wp-content/uploads/2023/02/xArm-working-range"
        assert len(_dedupe_cdn_transforms([
            base + ".png", base + "-768x578.png", base + "-300x191.png",
        ])) == 1

    def test_base_key_ignores_transform_and_extension_chain(self):
        assert _image_base_key(SHOP + "a_490x@2x.progressive.webp.jpg") == _image_base_key(SHOP + "a.png")


class TestCrossPageDemotion:
    def _stage(self, tmp_path, name, images):
        fp = tmp_path / f"{name}.json"
        fp.write_text(json.dumps({"name": name, "image": images[0], "images": images}),
                      encoding="utf-8")
        return fp

    def test_site_wide_asset_dropped_from_every_robot(self, tmp_path):
        """The RobCo case: a concept render reused across product pages."""
        generic = "https://cdn.example.com/Concept-Robot-Alfie-2026.webp"
        a = self._stage(tmp_path, "elise", ["https://cdn.example.com/Elegante_Elise.png", generic])
        b = self._stage(tmp_path, "gerti", [generic, "https://cdn.example.com/Gigantische_Gerti.png"])
        image_pages = {
            _image_base_key(generic): {"/robot/elise", "/robot/gerti", "/robot/leo"},
            _image_base_key("https://cdn.example.com/Elegante_Elise.png"): {"/robot/elise"},
            _image_base_key("https://cdn.example.com/Gigantische_Gerti.png"): {"/robot/gerti"},
        }
        stats = _demote_cross_page_images([a, b], image_pages)

        assert stats["dropped"] == 2
        for fp, keep in ((a, "Elegante_Elise.png"), (b, "Gigantische_Gerti.png")):
            d = json.loads(fp.read_text(encoding="utf-8"))
            assert d["images"] == [f"https://cdn.example.com/{keep}"]
            assert generic not in d["images"]

    def test_hero_is_repicked_when_it_was_the_generic_asset(self, tmp_path):
        """RobCo's actual failure: the generic render WAS the hero."""
        generic = "https://cdn.example.com/RobCo_Styleframe_003.webp"
        real = "https://cdn.example.com/Fitte_Frida.png"
        fp = self._stage(tmp_path, "frida", [generic, real])   # hero = generic
        stats = _demote_cross_page_images([fp], {
            _image_base_key(generic): {"/p/1", "/p/2"},
            _image_base_key(real): {"/p/frida"},
        })
        d = json.loads(fp.read_text(encoding="utf-8"))
        assert d["image"] == real
        assert stats["hero_repicked"] == 1

    def test_single_page_asset_is_kept(self, tmp_path):
        real = "https://cdn.example.com/Kleiner_Klaus.png"
        fp = self._stage(tmp_path, "klaus", [real])
        stats = _demote_cross_page_images([fp], {_image_base_key(real): {"/robot/klaus"}})
        assert json.loads(fp.read_text(encoding="utf-8"))["images"] == [real]
        assert stats["dropped"] == 0

    def test_demotion_matches_across_size_variants(self, tmp_path):
        """A generic asset served at a different size on each page is still generic."""
        fp = self._stage(tmp_path, "x", ["https://cdn.example.com/banner_490x.jpg"])
        stats = _demote_cross_page_images([fp], {
            _image_base_key("https://cdn.example.com/banner.jpg"): {"/p/1", "/p/2"},
        })
        assert stats["dropped"] == 1
        assert json.loads(fp.read_text(encoding="utf-8"))["images"] == []

    def test_demotion_handles_candidate_dict_entries(self, tmp_path):
        """The real RobCo shape: images[] are dicts, image is a string."""
        generic = FLOW + "Concept-Robot-RobCo-Alfie-2026-p-1080.webp"
        real = FLOW + "Elegante_Elise.png"
        fp = tmp_path / "elise.json"
        fp.write_text(json.dumps({
            "name": "Elegant Elise",
            "image": generic,                                   # hero = plain string
            "images": [{"url": generic, "confidence_score": 70},  # entries = dicts
                       {"url": real, "confidence_score": 90}],
        }), encoding="utf-8")

        stats = _demote_cross_page_images([fp], {
            _image_base_key(generic): {"/p/elise", "/p/gerti", "/p/leo"},
            _image_base_key(real): {"/p/elise"},
        })

        d = json.loads(fp.read_text(encoding="utf-8"))
        assert stats["dropped"] == 1
        assert [x["url"] for x in d["images"]] == [real]
        assert d["image"] == real           # hero re-picked AND still a string
        assert isinstance(d["image"], str)

    def test_robot_left_with_no_images_rather_than_a_wrong_one(self, tmp_path):
        """Correct beats padded: no fallback that re-adds a site-wide asset."""
        generic = "https://cdn.example.com/Concept-Robot.webp"
        fp = self._stage(tmp_path, "daniel", [generic])
        stats = _demote_cross_page_images([fp], {_image_base_key(generic): {"/p/1", "/p/2"}})
        d = json.loads(fp.read_text(encoding="utf-8"))
        assert d["images"] == [] and d["image"] == ""
        assert stats["emptied"] == 1
