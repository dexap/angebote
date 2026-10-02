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


@pytest.fixture
def fake_fetch(retailer_html, brochure_pages, brochure_pages_next):
    """Ersetzt HTTP: liefert Fixtures je nach URL und merkt sich die Aufrufe."""
    calls = []

    def fetch(url):
        calls.append(url)
        if url.startswith("https://www.kaufda.de/Geschaefte/Lidl"):
            return retailer_html
        if url.startswith(f"https://content-viewer-be.kaufda.de/v1/brochures/{NEXT_WEEK_BROCHURE}/"):
            return json.dumps(brochure_pages_next)
        if url.startswith("https://content-viewer-be.kaufda.de/v1/brochures/"):
            return json.dumps(brochure_pages)
        raise AssertionError(f"unerwartete URL: {url}")

    fetch.calls = calls
    return fetch
