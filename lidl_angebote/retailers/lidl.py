"""Lidl: Sonderpreis = "Mit Lidl Plus"-Preis neben dem normalen Angebotspreis."""

from .base import Retailer, card_price


def special_price(price, deals):
    return card_price(price, deals)


LIDL = Retailer(
    "lidl", "Lidl", "https://www.kaufda.de/Geschaefte/Lidl",
    food_only=True, common_only=False, special_price=special_price,
)
