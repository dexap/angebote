"""Live-Test gegen kaufda.de. Läuft nur mit LIVE=1 (Netzwerk nötig)."""

import os
from datetime import date

import pytest

from lidl_angebote import scraper

pytestmark = pytest.mark.skipif(os.environ.get("LIVE") != "1", reason="nur mit LIVE=1")


def test_live_scrape_returns_food_offers():
    result = scraper.scrape(date.today())
    assert result["brochures"], "kein Lidl-Wochenprospekt gefunden"
    assert result["count"] > 20
    for offer in result["offers"]:
        assert offer["price"] > 0
        assert offer["category_path"][0] == "Lebensmittel und Getränke"
