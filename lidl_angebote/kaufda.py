"""Parser für die JSON-Daten von kaufda.de (ohne PDF/OCR).

Zwei Quellen:
- Händlerseite (``/Geschaefte/Lidl``): eingebettetes ``__NEXT_DATA__`` mit den
  aktuellen Prospekten und dem Standort.
- Viewer-API (``content-viewer-be.kaufda.de``): alle Seiten eines Prospekts mit
  den verlinkten Angeboten inkl. Preisen und Kategorien.
"""

import json
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import retailers
from .retailers.base import conditions as _conditions
from .retailers.base import first_deal as _first

TZ = ZoneInfo("Europe/Berlin")

FOOD_CATEGORY_ID = "DE-104"  # "Lebensmittel und Getränke"
DRINK_CATEGORIES = {"Getränke", "Marken Getränke"}
MAX_WEEKLY_DAYS = 14

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def extract_next_data(html):
    match = _NEXT_DATA.search(html)
    if not match:
        raise ValueError("Kein __NEXT_DATA__ im HTML gefunden – Seitenstruktur geändert?")
    return json.loads(match.group(1))


def _page_information(next_data):
    return next_data["props"]["pageProps"]["pageInformation"]


def location(next_data):
    loc = _page_information(next_data)["location"]
    return loc["lat"], loc["lng"]


def _local_date(timestamp):
    try:
        dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        dt = datetime.fromisoformat(timestamp)
    return dt.astimezone(TZ).date()


def today():
    return datetime.now(TZ).date()


def week_range(ref):
    start = ref - timedelta(days=ref.weekday())
    return start, start + timedelta(days=6)


def find_brochures(next_data, publisher="Lidl"):
    """Alle Prospekte des Händlers aus allen Listen der Seite, ohne Duplikate."""
    found = {}
    for entries in _page_information(next_data)["brochures"].values():
        if not isinstance(entries, list):
            continue
        for b in entries:
            if b.get("publisher", {}).get("name", "").lower() != publisher.lower():
                continue
            found.setdefault(
                b["contentId"],
                {
                    "id": b["contentId"],
                    "title": b["title"],
                    "valid_from": _local_date(b["validFrom"]).isoformat(),
                    "valid_until": _local_date(b["validUntil"]).isoformat(),
                    "page_count": b.get("pageCount"),
                },
            )
    return list(found.values())


def _overlaps(start, end, week):
    return start <= week[1] and end >= week[0]


def select_brochures(brochures, week, include_long_running=False):
    """Prospekte, die in der Woche gültig sind; Langläufer (> 14 Tage) nur auf Wunsch."""
    selected = []
    for b in brochures:
        start, end = date.fromisoformat(b["valid_from"]), date.fromisoformat(b["valid_until"])
        if not _overlaps(start, end, week):
            continue
        if not include_long_running and (end - start).days > MAX_WEEKLY_DAYS:
            continue
        selected.append(b)
    return selected


_UNIT_PRICE = re.compile(r"^\(?\s*(\d+(?:[.,]\d+)?)\s*([^\W\d_]+)\s*=\s*(\d[\d.,]*)\s*\)?$")


_PER_UNIT = re.compile(r"^(-?\.\d+|\d[\d.,]*)\s*/\s*([^\W\d_]+)\.?$")


def _number(text):
    """'3.90', '12,50', '1.299,00' und '-.57' -> float."""
    if text.startswith("-."):
        text = text[1:]
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    return float(text)


def parse_unit_price(text):
    """'1 kg = 3.90' / '(1 l = 0.63)' -> {"amount", "unit", "quantity"}; sonst None."""
    text = (text or "").strip()
    per_unit = _PER_UNIT.match(text)  # "36.99/kg", "-.57/Stk."
    if per_unit:
        return {"amount": _number(per_unit.group(1)), "unit": per_unit.group(2), "quantity": 1}
    match = _UNIT_PRICE.match(text)
    if not match:
        return None
    quantity, unit, amount = match.groups()
    quantity = _number(quantity)
    return {
        "amount": _number(amount),
        "unit": unit,
        "quantity": int(quantity) if quantity == int(quantity) else quantity,
    }


def _flat_path(category_paths):
    """Viewer-API liefert einen flachen Pfad, die SEO-Seite eine Liste von Pfaden."""
    if category_paths and isinstance(category_paths[0], list):
        return category_paths[0]
    return category_paths or []


def _is_food(path):
    return bool(path) and path[0].get("id") == FOOD_CATEGORY_ID


def _normalize(text):
    return re.sub(r"[\W_]+", " ", text.replace("\xad", "")).strip().lower()


def _deals_for(product, deals, multi):
    """Bei Mehrprodukt-Angeboten nennt ``deal.description`` das Produkt."""
    if not multi:
        return deals
    name = _normalize(product["name"])
    own, shared = [], []
    for d in deals:
        desc = _normalize(d.get("description") or "")
        if not desc:
            shared.append(d)
        elif name.startswith(desc) or desc.startswith(name):
            own.append(d)
    return own + shared


def _price(deal):
    return deal["min"] if deal else None


def _offer_validity(content, brochure):
    for profile in content.get("publicationProfiles", []):
        v = profile.get("validity", {})
        if v.get("startDate") and v.get("endDate"):
            start, end = _local_date(v["startDate"]), _local_date(v["endDate"])
            if start <= end:
                return start, end
    return date.fromisoformat(brochure["valid_from"]), date.fromisoformat(brochure["valid_until"])


def _record(content, product, deals, index, multi, validity, retailer):
    sales = _first(deals, "SALES_PRICE")
    main = sales or _first(deals, "SPECIAL_PRICE")
    if not main:
        return None

    price = _price(main)
    special_price, special_condition, extras = retailers.get(retailer).special_price(price, deals)
    regular = _price(_first(deals, "REGULAR_PRICE"))
    reference = regular or _price(_first(deals, "RECOMMENDED_RETAIL_PRICE"))  # Normalpreis, sonst UVP
    discount = round((reference - price) / reference * 100) if reference and reference > price else None
    path = _flat_path(product.get("categoryPaths"))
    names = [p["name"] for p in path]
    unit_price = parse_unit_price(main.get("priceByBaseUnit"))
    notes = list(dict.fromkeys(_conditions(main) + extras))  # Preisbedingungen + Zusatzaktionen

    record = {
        "retailer": retailer,
        "id": f"{content['id']}#{index}" if multi else content["id"],
        "name": product["name"].replace("\xad", ""),
        "brand": product.get("brandName"),
        "description": " ".join(p["paragraph"].strip() for p in product.get("description", []) if p.get("paragraph")),
        "price": price,
        "regular_price": reference,
        "special_price": special_price,
        "special_price_condition": special_condition if special_price else None,
        "discount_percent": discount,
        "unit_price": unit_price,
        "notes": notes,
        "category_group": names[0] if names else None,
        "is_drink": any(n in DRINK_CATEGORIES for n in names),
        "valid_from": validity[0].isoformat(),
        "valid_until": validity[1].isoformat(),
    }
    # Leere Werte weglassen (fehlend = nicht vorhanden); ``is_drink`` bleibt immer.
    return {k: v for k, v in record.items() if k == "is_drink" or v not in (None, "", [], {})}


def parse_offers(pages, brochure, week, include_drinks=True, food_only=True, retailer="lidl"):
    """Angebote eines Prospekts (Antwort der Viewer-API); ``food_only`` = nur Lebensmittel und Getränke."""
    offers = []
    for page in pages.get("contents", []):
        for item in page.get("offers", []):
            content = item.get("content") or {}
            products = content.get("products") or []
            deals = content.get("deals") or []
            validity = _offer_validity(content, brochure)
            if not _overlaps(validity[0], validity[1], week):
                continue
            multi = len(products) > 1
            for index, product in enumerate(products):
                if food_only and not _is_food(_flat_path(product.get("categoryPaths"))):
                    continue
                own = _deals_for(product, deals, multi)
                record = _record(content, product, own, index, multi, validity, retailer)
                if record is None or (not include_drinks and record["is_drink"]):
                    continue
                offers.append(record)
    return offers
