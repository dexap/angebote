"""Händlerspezifische Sonderpreise: Lidl Plus (Lidl) und Bonus (REWE)."""

import pytest

from lidl_angebote import retailers


def other(text):
    return {"type": "OTHER", "min": 0, "max": 0, "conditions": [], "description": text}


def sales(price, *conditions):
    return {"type": "SALES_PRICE", "min": price, "max": price, "conditions": [{"other": c} for c in conditions]}


def special(price, *conditions):
    return {"type": "SPECIAL_PRICE", "min": price, "max": price, "conditions": [{"other": c} for c in conditions]}


REWE = retailers.REWE.special_price
LIDL = retailers.LIDL.special_price


@pytest.mark.parametrize(
    "price, text, expected_price, expected_condition",
    [
        (0.49, "0,10 € Bonus", 0.39, "REWE Bonus: 0,10 €"),
        (1.79, "0,20 € Bonus", 1.59, "REWE Bonus: 0,20 €"),
        (2.00, "Bonus 10%", 1.80, "REWE Bonus: 10 %"),
        (2.00, "10 % Bonus ", 1.80, "REWE Bonus: 10 %"),
        (1.00, "Bonus gültig vom 28.09. bis 04.10.2026 8%", 0.92, "REWE Bonus: 8 %"),
        (1.49, "Diesen Artikel zum Aktionspreis kaufen, 0,10 € Bonus in der REWE App sammeln ", 1.39, "REWE Bonus: 0,10 €"),
        (1.49, "Knoppers\n0,10 € Bonus", 1.39, "REWE Bonus: 0,10 €"),
        (17.99, "9,00 € Bonus", 8.99, "REWE Bonus: 9,00 €"),
    ],
)
def test_rewe_bonus_reduces_price(price, text, expected_price, expected_condition):
    got_price, condition, extras = REWE(price, [sales(price), other(text)])
    assert got_price == expected_price
    assert condition == expected_condition
    assert extras == []


def test_rewe_bonus_larger_than_price_is_kept_as_text_only():
    got_price, condition, extras = REWE(5.00, [sales(5.00), other("9,00 € Bonus")])
    assert (got_price, condition) == (None, None)
    assert extras == ["9,00 € Bonus"]


def test_rewe_other_texts_stay_extras_and_blanks_vanish():
    deals = [sales(2.49), other("0,10 € Bonus"), other("Beim Kauf von 1 Artikel 2 Vereinsscheine gratis"), other(" ")]
    got_price, condition, extras = REWE(2.49, deals)
    assert got_price == 2.39
    assert extras == ["Beim Kauf von 1 Artikel 2 Vereinsscheine gratis"]


def test_rewe_without_bonus():
    assert REWE(1.0, [sales(1.0)]) == (None, None, [])


def test_lidl_plus_price():
    assert LIDL(0.89, [sales(0.89, "Je Stück"), special(0.79, "Mit Lidl Plus")]) == (0.79, "Mit Lidl Plus", [])


def test_lidl_special_only_is_main_price_not_special():
    assert LIDL(0.79, [special(0.79, "Mit Lidl Plus")]) == (None, None, [])


def test_lidl_extras_from_other_deals():
    assert LIDL(11.99, [sales(11.99), other("Licor 43 kaufen H-Milch gratis dazu")]) == (
        None,
        None,
        ["Licor 43 kaufen H-Milch gratis dazu"],
    )


def test_lidl_special_price_without_condition_gets_neutral_label():
    assert LIDL(2.07, [special(1.38), sales(2.07)]) == (1.38, "Sonderpreis", [])


def test_lidl_multi_buy_price_is_an_extra_not_a_special_price():
    deals = [special(2, "Mit Lidl Plus, 4 für"), sales(0.99)]
    assert LIDL(0.99, deals) == (None, None, ["Mit Lidl Plus, 4 für 2,00 €"])


def test_condition_texts_start_uppercase():
    assert LIDL(0.89, [sales(0.89), special(0.79, "mit Lidl Plus")])[1] == "Mit Lidl Plus"
    from lidl_angebote.retailers.base import conditions

    assert conditions(sales(1.0, "je St.", "Je")) == ["Je St."]


PENNY = retailers.get("penny").special_price


@pytest.mark.parametrize(
    "condition",
    ["Nur mit App", "Nur mit der App", "mit PENNY App", "Mit PENNY App", "mit der App", "nur mit der app", "mit Penny App", " Nur mit App"],
)
def test_penny_app_conditions_are_unified(condition):
    assert PENNY(3.29, [sales(3.29), special(2.88, condition)]) == (2.88, "Mit PENNY App", [])


def test_penny_special_only_is_main_price():
    assert PENNY(2.88, [special(2.88, "Nur mit App")]) == (None, None, [])


def test_penny_multi_buy_price_is_a_note():
    assert PENNY(0.99, [sales(0.99), special(2, "Nur mit App")]) == (None, None, ["Mit PENNY App 2,00 €"])


def test_penny_texts_stay_notes():
    assert PENNY(1.0, [sales(1.0), other("Tages Tief Preise online checken")]) == (None, None, ["Tages Tief Preise online checken"])


def regular(price, *conditions):
    return {"type": "REGULAR_PRICE", "min": price, "max": price, "conditions": [{"other": c} for c in conditions]}


PENNY_PREPARE = retailers.get("penny").prepare_deals


def types(deals):
    return [(d["type"], d["min"]) for d in deals]


def test_penny_without_app_price_stays_main_price_and_hint_is_dropped():
    deals = PENNY_PREPARE([special(3.49, "Nur mit der App"), sales(4.59, "Ohne PENNY App")])
    assert PENNY(4.59, deals) == (3.49, "Mit PENNY App", [])
    assert deals[1]["conditions"] == []


def test_penny_app_price_without_sales_price_uses_regular_price_as_main():
    deals = PENNY_PREPARE([special(0.99, "mit der App"), regular(1.19, "Ohne App")])
    assert ("SALES_PRICE", 1.19) in types(deals)
    assert PENNY(1.19, deals) == (0.99, "Mit PENNY App", [])


def test_penny_regular_price_without_condition_also_becomes_main_price():
    deals = PENNY_PREPARE([special(1.99, "Nur mit der App"), regular(2.69)])
    assert PENNY(2.69, deals) == (1.99, "Mit PENNY App", [])


def test_penny_app_price_alone_stays_the_main_price():
    deals = PENNY_PREPARE([special(1.49, "Nur mit der App")])
    assert types(deals) == [("SPECIAL_PRICE", 1.49)]


def test_penny_regular_price_untouched_when_sales_price_exists():
    deals = PENNY_PREPARE([sales(3.29), special(2.88, "mit PENNY App"), regular(4.99)])
    assert ("REGULAR_PRICE", 4.99) in types(deals) and ("SALES_PRICE", 4.99) not in types(deals)


def test_penny_prepare_does_not_mutate_input():
    original = [special(0.99, "mit der App"), regular(1.19, "Ohne App")]
    PENNY_PREPARE(original)
    assert original[1]["type"] == "REGULAR_PRICE" and original[1]["conditions"] == [{"other": "Ohne App"}]


def test_other_retailers_leave_deals_unchanged():
    deals = [special(0.99, "mit der App"), regular(1.19)]
    assert retailers.LIDL.prepare_deals(deals) == deals and retailers.REWE.prepare_deals(deals) == deals
