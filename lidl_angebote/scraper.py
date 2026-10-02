"""Holt die Lidl-Angebote der Woche per HTTP und baut das Ergebnis-JSON."""

import json
import time
import urllib.request
from datetime import datetime, timezone

from . import kaufda

RETAILER = "Lidl"
RETAILER_URL = "https://www.kaufda.de/Geschaefte/Lidl"
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


def scrape(ref_date, fetch=None, include_drinks=True, include_long_running=False):
    fetch = fetch or http_get
    week = kaufda.week_range(ref_date)

    next_data = kaufda.extract_next_data(fetch(RETAILER_URL))
    lat, lng = kaufda.location(next_data)
    brochures = kaufda.select_brochures(
        kaufda.find_brochures(next_data, publisher=RETAILER), week, include_long_running
    )
    if not brochures:
        raise NoBrochureError(f"Kein {RETAILER}-Prospekt für {week[0]} – {week[1]} gefunden.")

    offers, seen = [], set()
    for brochure in brochures:
        pages = json.loads(fetch(PAGES_URL.format(id=brochure["id"], lat=lat, lng=lng)))
        for offer in kaufda.parse_offers(pages, brochure, week, include_drinks=include_drinks):
            if offer["id"] not in seen:
                seen.add(offer["id"])
                offers.append(offer)
    offers.sort(key=lambda o: (o["page"], o["name"]))

    iso = ref_date.isocalendar()
    return {
        "retailer": RETAILER,
        "source": RETAILER_URL,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "week": {"year": iso[0], "number": iso[1], "start": week[0].isoformat(), "end": week[1].isoformat()},
        "filters": {"include_drinks": include_drinks, "include_long_running": include_long_running},
        "brochures": brochures,
        "count": len(offers),
        "offers": offers,
    }
