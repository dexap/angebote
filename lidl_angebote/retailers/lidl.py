"""Lidl: Sonderpreis = "Mit Lidl Plus"-Preis neben dem normalen Angebotspreis."""

from .base import Retailer, conditions, first_deal, other_texts


def special_price(price, deals):
    sales, special = first_deal(deals, "SALES_PRICE"), first_deal(deals, "SPECIAL_PRICE")
    # Gibt es nur einen SPECIAL_PRICE, ist er der Angebotspreis selbst, kein Zusatz-Sonderpreis.
    extra = special if sales else None
    extras = other_texts(deals)
    if not extra:
        return None, None, extras
    condition = ", ".join(conditions(extra))
    if extra["min"] >= price:  # Mengenpreis ("4 für 2 €"), kein Einzelpreis
        return None, None, [f"{condition} {extra['min']:.2f} €".replace(".", ",").strip()] + extras
    return extra["min"], condition or "Sonderpreis", extras


LIDL = Retailer(
    "lidl", "Lidl", "https://www.kaufda.de/Geschaefte/Lidl",
    food_only=True, common_only=False, special_price=special_price,
)
