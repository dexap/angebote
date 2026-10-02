from datetime import date

import pytest

from lidl_angebote import kaufda

WEEKLY = "d6c82e39-5052-48b8-b8d0-814ec3babd87"  # LIDL LOHNT SICH, 28.09.–02.10.
LONG_RUNNING = "1bbb9c94-cc71-4377-9559-92bdde57b926"  # Preisführer, bis 31.12.
NEXT_WEEK = "2a8a792c-d99b-4497-90f7-d5a875f9b7e3"  # LIDL LOHNT SICH, 05.10.–10.10.

KW40 = (date(2026, 9, 28), date(2026, 10, 4))


# --- __NEXT_DATA__ -----------------------------------------------------------


def test_extract_next_data_returns_page_information(retailer_html):
    data = kaufda.extract_next_data(retailer_html)
    assert data["props"]["pageProps"]["pageInformation"]["type"] == "GLOBAL_RETAILER_LANDING_PAGE"


def test_extract_next_data_raises_without_script():
    with pytest.raises(ValueError, match="__NEXT_DATA__"):
        kaufda.extract_next_data("<html><body>nichts</body></html>")


def test_location_from_page(retailer_html):
    data = kaufda.extract_next_data(retailer_html)
    assert kaufda.location(data) == (52.522, 13.4161)


# --- Woche / Prospekte ---------------------------------------------------------


@pytest.mark.parametrize(
    "ref, expected",
    [
        (date(2026, 10, 2), KW40),  # Freitag
        (date(2026, 9, 28), KW40),  # Montag
        (date(2026, 10, 4), KW40),  # Sonntag
        (date(2026, 10, 5), (date(2026, 10, 5), date(2026, 10, 11))),
    ],
)
def test_week_range_is_monday_to_sunday(ref, expected):
    assert kaufda.week_range(ref) == expected


def test_find_brochures_only_lidl_and_deduplicated(retailer_html):
    data = kaufda.extract_next_data(retailer_html)
    brochures = kaufda.find_brochures(data, publisher="Lidl")
    ids = [b["id"] for b in brochures]
    assert sorted(ids) == sorted([WEEKLY, LONG_RUNNING, NEXT_WEEK])
    weekly = next(b for b in brochures if b["id"] == WEEKLY)
    assert weekly == {
        "id": WEEKLY,
        "title": "LIDL LOHNT SICH",
        "valid_from": "2026-09-28",
        "valid_until": "2026-10-02",
        "page_count": 73,
    }


def _brochures(retailer_html):
    return kaufda.find_brochures(kaufda.extract_next_data(retailer_html), publisher="Lidl")


def test_select_weekly_brochures_for_current_week(retailer_html):
    selected = kaufda.select_brochures(_brochures(retailer_html), KW40)
    assert [b["id"] for b in selected] == [WEEKLY]


def test_select_weekly_brochures_for_next_week(retailer_html):
    selected = kaufda.select_brochures(_brochures(retailer_html), (date(2026, 10, 5), date(2026, 10, 11)))
    assert [b["id"] for b in selected] == [NEXT_WEEK]


def test_select_brochures_with_long_running(retailer_html):
    selected = kaufda.select_brochures(_brochures(retailer_html), KW40, include_long_running=True)
    assert sorted(b["id"] for b in selected) == sorted([WEEKLY, LONG_RUNNING])


# --- Angebote ----------------------------------------------------------------

BROCHURE = {
    "id": WEEKLY,
    "title": "LIDL LOHNT SICH",
    "valid_from": "2026-09-28",
    "valid_until": "2026-10-02",
    "page_count": 73,
}


def _offers(brochure_pages, **kw):
    return kaufda.parse_offers(brochure_pages, BROCHURE, week=KW40, **kw)


def _by_name(offers, name):
    return next(o for o in offers if o["name"] == name)


def test_parse_offers_keeps_only_food_and_drinks(brochure_pages):
    names = sorted(o["name"] for o in _offers(brochure_pages))
    assert names == sorted(
        [
            "Eisbergsalat",
            "Kiwi, lose",
            "Granatapfel",
            "Tafelschokolade Alpenmilch",
            "Tomatenketchup",
            "Mayonnaise Das Original",
            "Mixgetränk",
            "LICOR 43",
        ]
    )


def test_parse_offers_without_drinks(brochure_pages):
    names = {o["name"] for o in _offers(brochure_pages, include_drinks=False)}
    assert "Mixgetränk" not in names
    assert "LICOR 43" not in names
    assert "Kiwi, lose" in names


def test_offer_with_regular_price_and_discount(brochure_pages):
    o = _by_name(_offers(brochure_pages), "Tafelschokolade Alpenmilch")
    assert o["price"] == 0.39
    assert o["regular_price"] == 0.79
    assert "uvp" not in o  # uvp ist in regular_price aufgegangen
    assert o["discount_percent"] == 51
    assert "base_price" not in o
    assert o["unit_price"] == {"amount": 3.9, "unit": "kg", "quantity": 1}
    assert o["brand"] == "FIN CARRÉ"
    assert o["description"] == "Je 100 g"
    assert o["is_drink"] is False


def test_offer_record_has_all_fields(brochure_pages):
    o = _by_name(_offers(brochure_pages), "Kiwi, lose")
    assert o == {
        "retailer": "lidl",
        "id": o["id"],
        "name": "Kiwi, lose",
        "brand": "Zespri",
        "description": "Neuseeland Green Kiwifruit, Klasse I",
        "price": 0.44,
        "regular_price": 0.49,
        "discount_percent": 10,
        "category_group": "Lebensmittel und Getränke",
        "is_drink": False,
        "valid_from": "2026-09-28",
        "valid_until": "2026-10-02",
    }


def test_lidl_plus_special_price(brochure_pages):
    o = _by_name(_offers(brochure_pages), "Granatapfel")
    assert o["price"] == 0.89
    assert o["special_price"] == 0.79
    assert o["special_price_condition"] == "Mit Lidl Plus"
    assert o["regular_price"] == 1.11
    assert o["notes"] == ["Je Stück"]


def test_uvp_becomes_regular_price_and_extras_become_notes(brochure_pages):
    o = _by_name(_offers(brochure_pages), "LICOR 43")
    assert o["price"] == 11.99
    assert o["regular_price"] == 15.99
    assert "uvp" not in o
    assert o["discount_percent"] == 25
    assert o["notes"] == ["Licor 43 kaufen H-Milch gratis dazu"]
    assert o["is_drink"] is True


def test_multi_product_offer_is_split_per_product(brochure_pages):
    offers = _offers(brochure_pages)
    ketchup = _by_name(offers, "Tomatenketchup")
    mayo = _by_name(offers, "Mayonnaise Das Original")
    assert ketchup["id"].split("#")[0] == mayo["id"].split("#")[0]
    assert ketchup["id"] != mayo["id"]
    assert ketchup["unit_price"] == {"amount": 2.98, "unit": "l", "quantity": 1}
    assert mayo["unit_price"] == {"amount": 4.36, "unit": "l", "quantity": 1}
    assert ketchup["regular_price"] == mayo["regular_price"] == 6.49


def test_invalid_offer_validity_falls_back_to_brochure(brochure_pages):
    o = _by_name(_offers(brochure_pages), "Eisbergsalat")
    assert (o["valid_from"], o["valid_until"]) == ("2026-09-28", "2026-10-02")


def test_offers_without_price_are_skipped(brochure_pages):
    offer = brochure_pages["contents"][1]["offers"][0]
    offer["content"]["deals"] = [{"type": "OTHER", "min": 0, "max": 0, "conditions": [], "description": "Gratis"}]
    names = {o["name"] for o in _offers(brochure_pages)}
    assert "Eisbergsalat" not in names


def test_offers_outside_week_are_skipped(brochure_pages):
    offers = kaufda.parse_offers(brochure_pages, BROCHURE, week=(date(2026, 10, 5), date(2026, 10, 11)))
    assert offers == []


def test_parse_offers_non_food_only_when_requested(brochure_pages):
    food = _offers(brochure_pages)
    everything = _offers(brochure_pages, food_only=False)
    assert len(everything) > len(food)
    assert {o["category_group"] for o in everything} - {"Lebensmittel und Getränke"}


def test_parse_offers_sets_retailer_key(brochure_pages):
    assert {o["retailer"] for o in _offers(brochure_pages, retailer="rewe")} == {"rewe"}


def test_empty_values_are_omitted_from_records(brochure_pages):
    for o in _offers(brochure_pages, food_only=False):
        assert all(v not in (None, "", [], {}) for v in o.values()), o


def test_trivial_je_condition_is_dropped(brochure_pages):
    for o in _offers(brochure_pages, food_only=False):
        assert all(c.strip().lower() != "je" for c in o.get("notes", []))


def test_removed_fields_are_not_emitted(brochure_pages):
    for o in _offers(brochure_pages, food_only=False):
        assert not {"offer_id", "uvp", "conditions", "extras"} & set(o)


def test_unparseable_base_price_is_dropped(brochure_pages):
    pages = brochure_pages
    for page in pages["contents"]:
        for item in page["offers"]:
            for deal in (item.get("content") or {}).get("deals", []):
                if deal.get("priceByBaseUnit"):
                    deal["priceByBaseUnit"] = "1 kg = ab 8.13"
    offers = _offers(pages)
    assert offers and all("unit_price" not in o and "base_price" not in o for o in offers)


def test_notes_combine_conditions_and_extras_without_duplicates(brochure_pages):
    o = _by_name(_offers(brochure_pages), "Granatapfel")
    assert o["notes"] == ["Je Stück"]
    licor = _by_name(_offers(brochure_pages), "LICOR 43")
    assert licor["notes"] == ["Licor 43 kaufen H-Milch gratis dazu"]
