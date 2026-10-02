"""Penny: Sonderpreis = App-Preis ("Nur mit App", "mit PENNY App", ... einheitlich "Mit PENNY App").

Der Preis ohne App ist der Hauptpreis (``price``). Steht er nur als REGULAR_PRICE neben dem App-Preis,
wird er dafür zum SALES_PRICE; Hinweise "Ohne PENNY App" entfallen (stehen schon in der Bedingung).
"""

from .base import Retailer, card_price


def _condition(text):
    return "Mit PENNY App" if "app" in text.lower() else text


def _has_app(deal):
    return any("app" in (c.get("other") or "").lower() for c in deal.get("conditions", []))


def _without_app_hint(deal):
    kept = [c for c in deal.get("conditions", []) if not ("ohne" in (c.get("other") or "").lower() and "app" in (c.get("other") or "").lower())]
    return {**deal, "conditions": kept}


def prepare_deals(deals):
    deals = [_without_app_hint(d) for d in deals]
    app_price = any(d.get("type") == "SPECIAL_PRICE" and _has_app(d) for d in deals)
    if app_price and not any(d.get("type") == "SALES_PRICE" for d in deals):
        deals = [{**d, "type": "SALES_PRICE"} if d.get("type") == "REGULAR_PRICE" else d for d in deals]
    return deals


def special_price(price, deals):
    return card_price(price, deals, normalize=_condition)


PENNY = Retailer(
    "penny", "Penny", "https://www.kaufda.de/Geschaefte/Penny-Markt",
    food_only=False, common_only=False, special_price=special_price, prepare_deals=prepare_deals,
)
