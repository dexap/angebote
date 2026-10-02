"""Baut die statische JSON-API für GitHub Pages.

    lidl.json, lidl/index.html            -> Angebote der aktuellen Woche
    lidl/next.json, lidl/next/index.html  -> Angebote der nächsten Woche

Inhalt ist jeweils nur die Liste der Angebote; ohne Prospekt ``[]``.
Netzwerk- oder Parserfehler brechen ab, damit nichts Leeres veröffentlicht wird.
"""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from . import kaufda, scraper

ENDPOINTS = {"lidl": 0, "lidl/next": 7}  # Pfad -> Tage ab heute

INDEX_HTML = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><title>Angebote-API</title></head>
<body>
<h1>Angebote-API</h1>
<ul>
<li><a href="lidl.json">lidl.json</a> (auch <a href="lidl/">lidl/</a>) – Lidl, aktuelle Woche</li>
<li><a href="lidl/next.json">lidl/next.json</a> (auch <a href="lidl/next/">lidl/next/</a>) – Lidl, nächste Woche</li>
</ul>
</body></html>
"""


def _offers(ref_date, fetch, retailer):
    try:
        return scraper.scrape(ref_date, fetch=fetch, retailer=retailer)["offers"]
    except scraper.NoBrochureError:
        return []


def build_site(out_dir, today, fetch=None):
    out = Path(out_dir)
    retailer = scraper.load_retailer(fetch)
    results = {path: _offers(today + timedelta(days=days), fetch, retailer) for path, days in ENDPOINTS.items()}

    for path, offers in results.items():
        text = json.dumps(offers, ensure_ascii=False, indent=1) + "\n"
        for target in (out / f"{path}.json", out / path / "index.html"):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
    (out / ".nojekyll").write_text("")
    (out / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    return {path: len(offers) for path, offers in results.items()}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="lidl-angebote-site", description="Statische JSON-API bauen.")
    parser.add_argument("--out", default="_site", help="Zielverzeichnis (Standard: _site)")
    parser.add_argument("--date", type=date.fromisoformat, default=kaufda.today(), help="Stichtag (YYYY-MM-DD)")
    args = parser.parse_args(argv)

    counts = build_site(args.out, args.date)
    for path, count in counts.items():
        print(f"{path}: {count} Angebote")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
