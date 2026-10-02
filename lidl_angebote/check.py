"""Checkup der einheitlichen Angebots-Schnittstelle (für alle Händler).

``python -m lidl_angebote.check`` scrapt live und prüft jedes Angebot;
``site.build_site`` ruft ``ensure_valid`` auf, damit nichts Kaputtes veröffentlicht wird.
"""

import argparse
import re
import sys
from datetime import date

from . import kaufda, retailers, scraper

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class SchemaError(ValueError):
    pass


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_iso_date(value):
    if not isinstance(value, str) or not _DATE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _nonempty_str(value):
    return isinstance(value, str) and value.strip() != ""


def _price(value):
    return _is_number(value) and value > 0


def _str_list(value):
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _unit_price(value):
    return (
        isinstance(value, dict)
        and set(value) == {"amount", "unit", "quantity"}
        and _price(value["amount"])
        and _nonempty_str(value["unit"])
        and _price(value["quantity"])
    )


def _percent(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value < 100


def _nonempty_strs(value):
    return _str_list(value) and len(value) > 0


# Pflichtfelder: immer vorhanden. Reihenfolge = Reihenfolge im JSON.
REQUIRED = {
    "retailer": lambda v: v in retailers.RETAILERS,
    "id": _nonempty_str,
    "name": _nonempty_str,
    "price": _price,
    "is_drink": lambda v: isinstance(v, bool),
    "valid_from": _is_iso_date,
    "valid_until": _is_iso_date,
}

# Optionalfelder: fehlen, wenn es keinen Wert gibt (nie null / "" / []).
OPTIONAL = {
    "brand": _nonempty_str,
    "description": _nonempty_str,
    "regular_price": _price,  # durchgestrichener Normalpreis, sonst UVP
    "special_price": _price,  # Preis mit Kundenkarte/Bonus (Lidl Plus, REWE Bonus), immer < price
    "special_price_condition": _nonempty_str,
    "discount_percent": _percent,  # gegenüber regular_price
    "unit_price": _unit_price,
    "notes": _nonempty_strs,  # Preisbedingungen und Zusatzaktionen
    "category_group": _nonempty_str,  # oberste Kategorie, z. B. "Drogerie und Haushalt"
}

FIELDS = tuple(REQUIRED) + tuple(OPTIONAL)


def check_offer(offer):
    """Liste der Probleme eines Angebots (leer = gültig)."""
    problems = [f"{f}: fehlt" for f in REQUIRED if f not in offer]
    for field, value in offer.items():
        rule = REQUIRED.get(field) or OPTIONAL.get(field)
        if rule is None:
            problems.append(f"{field}: unerwartetes Feld")
        elif not rule(value):
            hint = " (leere Werte weglassen)" if value in (None, "", []) and field in OPTIONAL else ""
            problems.append(f"{field}: ungültiger Wert {value!r}{hint}")
    if problems:
        return problems

    if offer["valid_from"] > offer["valid_until"]:
        problems.append("valid_from: liegt nach valid_until")
    if ("special_price" in offer) != ("special_price_condition" in offer):
        problems.append("special_price: nur zusammen mit special_price_condition")
    if "special_price" in offer and offer["special_price"] >= offer["price"]:
        problems.append("special_price: nicht kleiner als price")
    if "discount_percent" in offer and "regular_price" not in offer:
        problems.append("discount_percent: ohne regular_price")
    return problems


def check_offers(offers):
    """Probleme aller Angebote inkl. doppelter IDs, jeweils mit ID davor."""
    problems, seen = [], set()
    for offer in offers:
        offer_id = offer.get("id")
        problems += [f"{offer_id}: {p}" for p in check_offer(offer)]
        if offer_id in seen:
            problems.append(f"{offer_id}: doppelte id")
        seen.add(offer_id)
    return problems


def ensure_valid(offers, label=None):
    problems = check_offers(offers)
    if problems:
        shown = "\n  ".join(problems[:20])
        more = f"\n  … und {len(problems) - 20} weitere" if len(problems) > 20 else ""
        raise SchemaError(f"{label + ': ' if label else ''}{len(problems)} Schema-Probleme\n  {shown}{more}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="lidl-angebote-check", description="Schnittstelle live prüfen.")
    parser.add_argument("--date", type=date.fromisoformat, default=kaufda.today(), help="Stichtag (YYYY-MM-DD)")
    parser.add_argument("--retailer", choices=sorted(retailers.RETAILERS), action="append", help="Standard: alle")
    args = parser.parse_args(argv)

    failed = False
    for key in args.retailer or sorted(retailers.RETAILERS):
        try:
            offers = scraper.scrape(args.date, config=retailers.get(key))["offers"]
        except scraper.NoBrochureError as e:
            print(f"{key}: {e}")
            continue
        problems = check_offers(offers)
        if problems:
            failed = True
            print(f"{key}: {len(offers)} Angebote, {len(problems)} Probleme")
            for p in problems[:30]:
                print(f"  {p}")
        else:
            print(f"{key}: {len(offers)} Angebote, OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
