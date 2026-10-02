import pytest

from lidl_angebote import kaufda


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1 kg = 3.90", {"amount": 3.9, "unit": "kg", "quantity": 1}),
        ("(1 l = 0.63)", {"amount": 0.63, "unit": "l", "quantity": 1}),
        ("100 g = 1.29", {"amount": 1.29, "unit": "g", "quantity": 100}),
        ("(1 kg = 12,50)", {"amount": 12.5, "unit": "kg", "quantity": 1}),
        ("1 Stück = 0.25", {"amount": 0.25, "unit": "Stück", "quantity": 1}),
        ("(100 ml = 0.99)", {"amount": 0.99, "unit": "ml", "quantity": 100}),
        ("1 kg = 1.299,00", {"amount": 1299.0, "unit": "kg", "quantity": 1}),
        ("36.99/kg", {"amount": 36.99, "unit": "kg", "quantity": 1}),
        ("-.57/Stk.", {"amount": 0.57, "unit": "Stk", "quantity": 1}),
    ],
)
def test_parse_unit_price(text, expected):
    assert kaufda.parse_unit_price(text) == expected


@pytest.mark.parametrize("text", [None, "", "je Packung", "Preis ohne Einheit", "1 kg = 6.32/3.95", "1 kg = ab 8.13", "1kg=ab 4.26", "1 kg = 4.955.74", "1 kg = 1,2,3", "1 kg = 4.95."])
def test_parse_unit_price_unparseable_is_none(text):
    assert kaufda.parse_unit_price(text) is None
