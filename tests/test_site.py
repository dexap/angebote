import json
from datetime import date

import pytest

from lidl_angebote import site


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def built(tmp_path, fake_fetch):
    site.build_site(tmp_path, today=date(2026, 10, 2), fetch=fake_fetch)
    return tmp_path


def test_current_week_is_plain_offer_list(built):
    offers = _read(built / "lidl.json")
    assert isinstance(offers, list)
    assert len(offers) == 8
    assert {"name", "price", "valid_until"} <= set(offers[0])


def test_exact_paths_serve_same_json_as_index_html(built):
    assert _read(built / "lidl" / "index.html") == _read(built / "lidl.json")
    assert _read(built / "lidl" / "next" / "index.html") == _read(built / "lidl" / "next.json")


def test_next_week_offers(built):
    names = sorted(o["name"] for o in _read(built / "lidl" / "next.json"))
    assert names == ["Almighurt", "Antipasti", "PRINGLES"]


def test_retailer_page_fetched_once(built, fake_fetch):
    assert len([u for u in fake_fetch.calls if "Geschaefte" in u]) == 1


def test_missing_brochure_gives_empty_list(tmp_path, fake_fetch):
    # KW49: kein Wochenprospekt im Fixture
    site.build_site(tmp_path, today=date(2026, 12, 1), fetch=fake_fetch)
    assert _read(tmp_path / "lidl.json") == []
    assert _read(tmp_path / "lidl" / "next.json") == []


def test_network_error_is_not_published_as_empty(tmp_path):
    def broken(url):
        raise OSError("kaufda nicht erreichbar")

    with pytest.raises(OSError):
        site.build_site(tmp_path, today=date(2026, 10, 2), fetch=broken)
    assert not (tmp_path / "lidl.json").exists()


def test_static_files(built):
    assert (built / ".nojekyll").exists()
    index = (built / "index.html").read_text(encoding="utf-8")
    assert "lidl.json" in index and "lidl/next.json" in index


def test_main_writes_site(tmp_path, monkeypatch, fake_fetch):
    from lidl_angebote import scraper

    monkeypatch.setattr(scraper, "http_get", fake_fetch)
    assert site.main(["--out", str(tmp_path), "--date", "2026-10-02"]) == 0
    assert len(_read(tmp_path / "lidl.json")) == 8
