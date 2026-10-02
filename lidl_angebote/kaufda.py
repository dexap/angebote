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


def _first(deals, deal_type):
    return next((d for d in deals if d.get("type") == deal_type and (d.get("min") or 0) > 0), None)


def _conditions(deal):
    if not deal:
        return []
    return [c["other"].strip() for c in deal.get("conditions", []) if c.get("other", "").strip()]


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


def _record(content, product, deals, index, multi, page_number, validity, brochure):
    sales = _first(deals, "SALES_PRICE")
    special = _first(deals, "SPECIAL_PRICE")
    main = sales or special
    if not main:
        return None
    extra_special = special if sales else None  # z. B. "Mit Lidl Plus"

    price = _price(main)
    regular = _price(_first(deals, "REGULAR_PRICE"))
    uvp = _price(_first(deals, "RECOMMENDED_RETAIL_PRICE"))
    reference = regular or uvp
    discount = round((reference - price) / reference * 100) if reference and reference > price else None
    path = _flat_path(product.get("categoryPaths"))
    names = [p["name"] for p in path]
    extras = [
        d["description"].strip()
        for d in deals
        if d.get("type") == "OTHER" and (d.get("description") or "").strip()
    ]

    return {
        "id": f"{content['id']}#{index}" if multi else content["id"],
        "offer_id": content["id"],
        "name": product["name"].replace("\xad", ""),
        "brand": product.get("brandName"),
        "description": " ".join(p["paragraph"].strip() for p in product.get("description", []) if p.get("paragraph")),
        "price": price,
        "regular_price": regular,
        "uvp": uvp,
        "special_price": _price(extra_special),
        "special_price_condition": ", ".join(_conditions(extra_special)) or None,
        "discount_percent": discount,
        "base_price": main.get("priceByBaseUnit") or None,
        "conditions": _conditions(main),
        "extras": extras,
        "category": names[-1] if names else None,
        "category_path": names,
        "is_drink": any(n in DRINK_CATEGORIES for n in names),
        "valid_from": validity[0].isoformat(),
        "valid_until": validity[1].isoformat(),
        "brochure_id": brochure["id"],
        "brochure_title": brochure["title"],
        "page": page_number + 1,
        "image": content.get("image"),
    }


def parse_offers(pages, brochure, week, include_drinks=True):
    """Lebensmittel-Angebote eines Prospekts (Antwort der Viewer-API)."""
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
                if not _is_food(_flat_path(product.get("categoryPaths"))):
                    continue
                own = _deals_for(product, deals, multi)
                record = _record(content, product, own, index, multi, page["number"], validity, brochure)
                if record is None or (not include_drinks and record["is_drink"]):
                    continue
                offers.append(record)
    return offers
