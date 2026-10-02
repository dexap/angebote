"""Gemeinsame Bausteine für Händler-Parser.

Jeder Händler liegt in ``retailers/<key>.py`` und liefert eine ``Retailer``-Konfiguration inkl.
``special_price`` - der händlerspezifischen Auswertung von Sonderpreisen (Lidl Plus, REWE Bonus, ...).
Die Ausgabe der Angebote läuft immer über dieselbe Schnittstelle (siehe ``check.py`` / SCHEMA.md).
"""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Retailer:
    key: str  # URL-/JSON-Schlüssel, Wert des Feldes ``retailer``
    name: str  # Händlername wie im kaufda-Prospekt (``publisher.name``)
    url: str
    food_only: bool  # nur "Lebensmittel und Getränke" oder alle Kategorien
    common_only: bool  # nur Angebote, die in allen Markt-Prospekten stehen ("national")
    # (price, deals) -> (special_price | None, special_price_condition | None, extras)
    special_price: Callable


def first_deal(deals, deal_type):
    return next((d for d in deals if d.get("type") == deal_type and (d.get("min") or 0) > 0), None)


def conditions(deal):
    """Bedingungstexte eines Deals: ohne das bedeutungslose "je", mit großem Anfangsbuchstaben."""
    if not deal:
        return []
    texts = [c["other"].strip() for c in deal.get("conditions", []) if c.get("other", "").strip()]
    return [t[0].upper() + t[1:] for t in texts if t.lower() != "je"]


def other_texts(deals):
    """Freitexte der OTHER-Deals (Zusatzaktionen), ohne leere."""
    return [d["description"].strip() for d in deals if d.get("type") == "OTHER" and (d.get("description") or "").strip()]
