from datetime import date

import pytest

from lidl_angebote import retailers, scraper

KW40 = date(2026, 10, 2)


def test_registry_has_lidl_and_rewe():
    assert set(retailers.RETAILERS) == {"lidl", "rewe"}
    lidl, rewe = retailers.RETAILERS["lidl"], retailers.RETAILERS["rewe"]
    assert (lidl.name, lidl.url) == ("Lidl", "https://www.kaufda.de/Geschaefte/Lidl")
    assert (rewe.name, rewe.url) == ("REWE", "https://www.kaufda.de/Geschaefte/REWE")
    assert lidl.food_only is True and lidl.common_only is False
    assert rewe.food_only is False and rewe.common_only is True


def test_rewe_scrape_returns_only_offers_common_to_all_markets(fake_fetch):
    result = scraper.scrape(KW40, fetch=fake_fetch, config=retailers.REWE)

    assert result["retailer"] == "REWE"
    assert result["scope"] == "national"
    assert len(result["brochures"]) == 2
    assert sorted(o["name"] for o in result["offers"]) == ["Chips", "Haarspray", "Pepsi"]


def test_rewe_keeps_non_food(fake_fetch):
    offers = scraper.scrape(KW40, fetch=fake_fetch, config=retailers.REWE)["offers"]
    haarspray = next(o for o in offers if o["name"] == "Haarspray")
    assert haarspray["category_group"] == "Drogerie und Haushalt"
    assert haarspray["retailer"] == "rewe"


def test_rewe_ignores_other_publishers(fake_fetch):
    brochures = scraper.load_retailer(fake_fetch, config=retailers.REWE)["brochures"]
    assert len(brochures) == 2


def test_lidl_still_food_only_and_scope_all(fake_fetch):
    result = scraper.scrape(KW40, fetch=fake_fetch)
    assert result["scope"] == "all"
    assert {o["retailer"] for o in result["offers"]} == {"lidl"}
    assert {o["category_group"] for o in result["offers"]} == {"Lebensmittel und Getränke"}


def test_common_only_with_single_brochure_keeps_everything(fake_fetch):
    retailer = scraper.load_retailer(fake_fetch, config=retailers.REWE)
    retailer["brochures"] = retailer["brochures"][:1]
    names = {o["name"] for o in scraper.scrape(KW40, fetch=fake_fetch, retailer=retailer, config=retailers.REWE)["offers"]}
    assert {"Chips", "Pepsi", "Haarspray"} < names and len(names) == 5


def test_unknown_retailer_key():
    with pytest.raises(KeyError):
        retailers.get("aldi")


def test_rewe_bonus_becomes_special_price(fake_fetch):
    offers = scraper.scrape(KW40, fetch=fake_fetch, config=retailers.REWE)["offers"]
    chips = next(o for o in offers if o["name"] == "Chips")
    assert chips["price"] == 1.49
    assert chips["special_price"] == 1.39
    assert chips["special_price_condition"] == "REWE Bonus: 0,10 €"
    assert "notes" not in chips
