import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def retailer_html():
    return (FIXTURES / "retailer_page.html").read_text(encoding="utf-8")


@pytest.fixture
def brochure_pages():
    return json.loads((FIXTURES / "brochure_pages.json").read_text(encoding="utf-8"))


NEXT_WEEK_BROCHURE = "2a8a792c-d99b-4497-90f7-d5a875f9b7e3"


@pytest.fixture
def brochure_pages_next():
    return json.loads((FIXTURES / "brochure_pages_next.json").read_text(encoding="utf-8"))


REWE_MARKET_A = "8671d3e2-879b-4911-a62a-6964f2910f8d"
REWE_MARKET_B = "70235f32-cc7a-44b7-a585-8e8c3bbec178"


@pytest.fixture
def rewe_retailer_html():
    return (FIXTURES / "rewe_retailer_page.html").read_text(encoding="utf-8")


@pytest.fixture
def penny_retailer_html():
    return (FIXTURES / "penny_retailer_page.html").read_text(encoding="utf-8")


PENNY_WEEK = "e8de9515-1a27-476d-a59d-6954b697b264"


@pytest.fixture
def rewe_pages():
    """Zwei Märkte: je 3 gemeinsame Angebote (Chips, Pepsi, Haarspray) plus marktspezifische."""
    return {
        REWE_MARKET_A: (FIXTURES / "rewe_pages_a.json").read_text(encoding="utf-8"),
        REWE_MARKET_B: (FIXTURES / "rewe_pages_b.json").read_text(encoding="utf-8"),
    }


@pytest.fixture
def fake_fetch(retailer_html, brochure_pages, brochure_pages_next, rewe_retailer_html, rewe_pages, penny_retailer_html):
    """Ersetzt HTTP: liefert Fixtures je nach URL und merkt sich die Aufrufe."""
    calls = []

    def fetch(url):
        calls.append(url)
        if url.startswith("https://www.kaufda.de/Geschaefte/Lidl"):
            return retailer_html
        if url.startswith("https://www.kaufda.de/Geschaefte/REWE"):
            return rewe_retailer_html
        if url.startswith("https://www.kaufda.de/Geschaefte/Penny-Markt"):
            return penny_retailer_html
        if url.startswith(f"https://content-viewer-be.kaufda.de/v1/brochures/{PENNY_WEEK}/"):
            return (FIXTURES / "penny_pages.json").read_text(encoding="utf-8")
        for market, text in rewe_pages.items():
            if url.startswith(f"https://content-viewer-be.kaufda.de/v1/brochures/{market}/"):
                return text
        if url.startswith(f"https://content-viewer-be.kaufda.de/v1/brochures/{NEXT_WEEK_BROCHURE}/"):
            return json.dumps(brochure_pages_next)
        if url.startswith("https://content-viewer-be.kaufda.de/v1/brochures/"):
            return json.dumps(brochure_pages)
        raise AssertionError(f"unerwartete URL: {url}")

    fetch.calls = calls
    return fetch
