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
