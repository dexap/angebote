"""REWE: "Bonus" (Cashback in der REWE App) wird vom Preis abgezogen und als Sonderpreis ausgegeben.

Der Bonus steht als Freitext in OTHER-Deals: "0,10 € Bonus", "Bonus 10%", "Bonus gültig vom ... 8%".
Andere Texte (z. B. Vereinsscheine) bleiben als ``notes`` erhalten.
"""

import re

from .base import Retailer, other_texts

_EURO = re.compile(r"(\d+(?:,\d{1,2})?)\s*€\s*Bonus", re.I)
_PERCENT = re.compile(r"(\d+(?:,\d+)?)\s*%")


def _parse_bonus(text):
    """-> (neuer Preis als Funktion von price, Bedingungstext) oder None."""
    euro = _EURO.search(text)
    if euro:
        amount = float(euro.group(1).replace(",", "."))
        return (lambda price: price - amount), f"REWE Bonus: {amount:.2f} €".replace(".", ",")
    percent = _PERCENT.search(text)
    if percent and "bonus" in text.lower():
        pct = float(percent.group(1).replace(",", "."))
        return (lambda price: price * (1 - pct / 100)), f"REWE Bonus: {pct:g} %"
    return None


def special_price(price, deals):
    special, condition, extras = None, None, []
    for text in other_texts(deals):
        bonus = _parse_bonus(text) if special is None else None
        reduced = round(bonus[0](price), 2) if bonus else None
        if bonus and 0 < reduced < price:
            special, condition = reduced, bonus[1]
        else:
            extras.append(text)
    return special, condition, extras


REWE = Retailer(
    "rewe", "REWE", "https://www.kaufda.de/Geschaefte/REWE",
    food_only=False, common_only=True, special_price=special_price,
)
