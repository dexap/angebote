"""Holt die Lidl-Angebote der Woche per HTTP und baut das Ergebnis-JSON."""

import json
import time
import urllib.request
from datetime import datetime, timezone

from . import kaufda
from .retailers import LIDL

RETAILER = LIDL.name
RETAILER_URL = LIDL.url
PAGES_URL = "https://content-viewer-be.kaufda.de/v1/brochures/{id}/pages?partner=kaufda_web&lat={lat}&lng={lng}"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def http_get(url, retries=3, timeout=30):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "de-DE"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except OSError:
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)


class NoBrochureError(RuntimeError):
    pass


def load_retailer(fetch=None, config=LIDL):
    """Händlerseite einmal laden: alle Prospekte des Händlers und Standort."""
    next_data = kaufda.extract_next_data((fetch or http_get)(config.url))
    lat, lng = kaufda.location(next_data)
    return {"brochures": kaufda.find_brochures(next_data, publisher=config.name), "lat": lat, "lng": lng}


def _offer_key(offer):
    return (offer["name"], offer["price"], offer.get("description"), offer["valid_from"], offer["valid_until"])


def _common(per_brochure):
    """Nur Angebote, die in jedem Markt-Prospekt vorkommen (bei einem Prospekt: alle)."""
    if len(per_brochure) < 2:
        return [o for offers in per_brochure for o in offers]
    shared = set.intersection(*({_offer_key(o) for o in offers} for offers in per_brochure))
    return [o for o in per_brochure[0] if _offer_key(o) in shared]


def scrape(ref_date, fetch=None, include_drinks=True, include_long_running=False, retailer=None, config=LIDL):
    fetch = fetch or http_get
    week = kaufda.week_range(ref_date)

    retailer = retailer or load_retailer(fetch, config)
    lat, lng = retailer["lat"], retailer["lng"]
    brochures = kaufda.select_brochures(retailer["brochures"], week, include_long_running)
    if not brochures:
        raise NoBrochureError(f"Kein {config.name}-Prospekt für {week[0]} – {week[1]} gefunden.")

    per_brochure = []
    for brochure in brochures:
        pages = json.loads(fetch(PAGES_URL.format(id=brochure["id"], lat=lat, lng=lng)))
        per_brochure.append(
            kaufda.parse_offers(
                pages, brochure, week, include_drinks=include_drinks, food_only=config.food_only, retailer=config.key
            )
        )
    candidates = _common(per_brochure) if config.common_only else [o for offers in per_brochure for o in offers]

    offers, seen = [], set()
    for offer in candidates:
        if offer["id"] not in seen:
            seen.add(offer["id"])
            offers.append(offer)
    offers.sort(key=lambda o: (o.get("category_group", ""), o["name"]))

    iso = ref_date.isocalendar()
    return {
        "retailer": config.name,
        "source": config.url,
        "scope": "national" if config.common_only else "all",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "week": {"year": iso[0], "number": iso[1], "start": week[0].isoformat(), "end": week[1].isoformat()},
        "filters": {"include_drinks": include_drinks, "include_long_running": include_long_running},
        "brochures": brochures,
        "count": len(offers),
        "offers": offers,
    }
