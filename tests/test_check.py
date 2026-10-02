import copy
from datetime import date

import pytest

from lidl_angebote import check, retailers, scraper

GOOD = {
    "retailer": "lidl",
    "id": "abc",
    "name": "Kiwi",
    "brand": "Zespri",
    "description": "Neuseeland",
    "price": 0.44,
    "regular_price": 0.60,
    "discount_percent": 27,
    "special_price": 0.39,
    "special_price_condition": "Mit Lidl Plus",
    "unit_price": {"amount": 3.9, "unit": "kg", "quantity": 1},
    "notes": ["Je Stück", "Gratis dazu"],
    "category_group": "Lebensmittel und Getränke",
    "is_drink": False,
    "valid_from": "2026-09-28",
    "valid_until": "2026-10-02",
}

MINIMAL = {
    "retailer": "rewe",
    "id": "x",
    "name": "Salz",
    "price": 0.5,
    "is_drink": False,
    "valid_from": "2026-09-28",
    "valid_until": "2026-10-02",
}


def bad(**changes):
    offer = copy.deepcopy(GOOD)
    offer.update(changes)
    return offer


def test_valid_offer_has_no_problems():
    assert check.check_offer(GOOD) == []


def test_minimal_offer_without_optional_fields_is_valid():
    assert check.check_offer(MINIMAL) == []


@pytest.mark.parametrize(
    "changes, fragment",
    [
        ({"price": 0}, "price"),
        ({"price": "0.44"}, "price"),
        ({"price": True}, "price"),
        ({"name": ""}, "name"),
        ({"retailer": "aldi"}, "retailer"),
        ({"regular_price": -1.0}, "regular_price"),
        ({"discount_percent": 120}, "discount_percent"),
        ({"valid_from": "28.09.2026"}, "valid_from"),
        ({"valid_from": "2026-10-03"}, "valid_from"),
        ({"category_group": ""}, "category_group"),
        ({"is_drink": "nein"}, "is_drink"),
        ({"unit_price": {"amount": 1, "unit": "kg"}}, "unit_price"),
        ({"unit_price": {"amount": -1, "unit": "kg", "quantity": 1}}, "unit_price"),
        ({"notes": "je"}, "notes"),
        # leere Optionalfelder müssen fehlen, nicht null/leer sein
        ({"brand": None}, "brand"),
        ({"description": ""}, "description"),
        ({"notes": []}, "notes"),
        # Zusammenhänge
        ({"special_price": 0.5}, "special_price"),
        ({"special_price": 0.44}, "special_price"),
        ({"special_price_condition": "x", "special_price": None}, "special_price"),
        # entfernte Felder
        ({"page": 3}, "page"),
        ({"brochure_id": "b"}, "brochure_id"),
        ({"category": "Zespri"}, "category"),
        ({"offer_id": "o"}, "offer_id"),
        ({"base_price": "1 kg = 3.90"}, "base_price"),
        ({"uvp": 1.0}, "uvp"),
        ({"conditions": ["Je Stück"]}, "conditions"),
        ({"extras": ["x"]}, "extras"),
        ({"image": "https://x/y.jpg"}, "image"),
        ({"category_path": ["Obst"]}, "category_path"),
    ],
)
def test_invalid_field_is_reported(changes, fragment):
    problems = check.check_offer(bad(**changes))
    assert problems and any(fragment in p for p in problems)


def test_special_price_needs_condition():
    offer = bad()
    del offer["special_price_condition"]
    assert any("special_price" in p for p in check.check_offer(offer))


def test_discount_needs_reference_price():
    offer = bad()
    del offer["regular_price"]
    assert any("discount_percent" in p for p in check.check_offer(offer))


def test_missing_required_field_is_reported():
    offer = copy.deepcopy(GOOD)
    del offer["valid_until"]
    assert any("valid_until" in p for p in check.check_offer(offer))


def test_unexpected_field_is_reported():
    assert any("extra" in p for p in check.check_offer(bad(extra=1)))


def test_check_offers_finds_duplicate_ids_and_names_the_offer():
    problems = check.check_offers([GOOD, copy.deepcopy(GOOD)])
    assert any("doppelte id" in p and "abc" in p for p in problems)


def test_check_offers_prefixes_problems_with_id():
    problems = check.check_offers([bad(id="x1", price=0)])
    assert problems[0].startswith("x1: ")


def test_raise_on_problems():
    with pytest.raises(check.SchemaError) as e:
        check.ensure_valid([bad(price=0)])
    assert "price" in str(e.value)
    check.ensure_valid([GOOD])


@pytest.mark.parametrize("key", ["lidl", "rewe"])
def test_scraped_offers_satisfy_schema(fake_fetch, key):
    offers = scraper.scrape(date(2026, 10, 2), fetch=fake_fetch, config=retailers.get(key))["offers"]
    assert offers
    assert check.check_offers(offers) == []


def test_cli_reports_ok_and_failure(monkeypatch, fake_fetch, capsys):
    monkeypatch.setattr(scraper, "http_get", fake_fetch)
    assert check.main(["--date", "2026-10-02"]) == 0
    out = capsys.readouterr().out
    assert "lidl" in out and "rewe" in out and "OK" in out

    monkeypatch.setattr(check, "check_offers", lambda offers: ["x: price kaputt"])
    assert check.main(["--date", "2026-10-02"]) == 1
    assert "price kaputt" in capsys.readouterr().out
