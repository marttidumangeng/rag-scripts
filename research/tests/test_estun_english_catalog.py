from estun_english_catalog import (
    ESTUN_ENGLISH_LIST_URLS,
    lookup_estun_english_entry,
)


def test_estun_english_list_urls():
    assert len(ESTUN_ENGLISH_LIST_URLS) == 4
    assert all("en.estun.com" in u for u in ESTUN_ENGLISH_LIST_URLS)


def test_lookup_estun_ier_alias():
    entry = lookup_estun_english_entry("iER8-720-MI-C", "iER8-720-MI-C")
    assert entry is not None
    assert "en.estun.com" in entry["url"]
    assert entry.get("image")


def test_lookup_estun_er_name():
    entry = lookup_estun_english_entry("ER130-2865-BD", "ER130-2865-BD")
    assert entry is not None
    assert "list_" in entry["url"]
