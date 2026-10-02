import json
from datetime import date

from lidl_angebote import cli, scraper

WEEKLY = "d6c82e39-5052-48b8-b8d0-814ec3babd87"


def test_scrape_builds_result(fake_fetch):
    result = scraper.scrape(date(2026, 10, 2), fetch=fake_fetch)

    assert result["retailer"] == "Lidl"
    assert result["source"] == "https://www.kaufda.de/Geschaefte/Lidl"
    assert result["week"] == {"year": 2026, "number": 40, "start": "2026-09-28", "end": "2026-10-04"}
    assert [b["id"] for b in result["brochures"]] == [WEEKLY]
    assert result["count"] == len(result["offers"]) == 8
    assert "generated_at" in result


def test_scrape_requests_brochure_pages_with_location(fake_fetch):
    scraper.scrape(date(2026, 10, 2), fetch=fake_fetch)
    viewer_calls = [u for u in fake_fetch.calls if "content-viewer-be" in u]
    assert viewer_calls == [
        f"https://content-viewer-be.kaufda.de/v1/brochures/{WEEKLY}/pages"
        "?partner=kaufda_web&lat=52.522&lng=13.4161"
    ]


def test_scrape_offers_sorted_by_page_then_name(fake_fetch):
    offers = scraper.scrape(date(2026, 10, 2), fetch=fake_fetch)["offers"]
    keys = [(o["page"], o["name"]) for o in offers]
    assert keys == sorted(keys)


def test_scrape_deduplicates_offers_across_brochures(fake_fetch):
    # Beide Prospekte liefern im Fake dieselben Seiten -> keine Duplikate.
    result = scraper.scrape(date(2026, 10, 2), fetch=fake_fetch, include_long_running=True)
    assert len(result["brochures"]) == 2
    ids = [o["id"] for o in result["offers"]]
    assert len(ids) == len(set(ids))


def test_scrape_without_drinks(fake_fetch):
    result = scraper.scrape(date(2026, 10, 2), fetch=fake_fetch, include_drinks=False)
    assert all(not o["is_drink"] for o in result["offers"])
    assert result["filters"] == {"include_drinks": False, "include_long_running": False}


def test_default_output_path():
    assert cli.default_output_path(date(2026, 10, 2)) == "data/lidl_2026-KW40.json"


def test_cli_writes_json(tmp_path, monkeypatch, fake_fetch):
    monkeypatch.setattr(scraper, "http_get", fake_fetch)
    out = tmp_path / "angebote.json"

    exit_code = cli.main(["--date", "2026-10-02", "--output", str(out)])

    assert exit_code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["count"] == 8
    assert "Eisbergsalat" in out.read_text(encoding="utf-8")  # UTF-8, nicht escaped


def test_cli_fails_cleanly_without_brochures(tmp_path, monkeypatch, fake_fetch, capsys):
    monkeypatch.setattr(scraper, "http_get", fake_fetch)
    exit_code = cli.main(["--date", "2026-12-01", "--output", str(tmp_path / "x.json")])
    assert exit_code == 1
    assert "Kein" in capsys.readouterr().err
