"""Baut die statische JSON-API (GitHub Pages / lokaler Server).

    <händler>.json, <händler>/index.html            -> Angebote der aktuellen Woche
    <händler>/next.json, <händler>/next/index.html  -> Angebote der nächsten Woche
    all.json, all/...                               -> alle Händler zusammen

Händler siehe ``retailers.RETAILERS``. Inhalt ist jeweils nur die Liste der Angebote;
ohne Prospekt ``[]``. Netzwerk-, Parser- oder Schemafehler brechen ab, damit nichts
Leeres oder Kaputtes veröffentlicht wird.
"""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from . import check, kaufda, retailers, scraper

WEEKS = {"": 0, "/next": 7}  # Pfad-Suffix -> Tage ab heute
ALL = "all"


def _offers(ref_date, fetch, loaded, config):
    try:
        return scraper.scrape(ref_date, fetch=fetch, retailer=loaded, config=config)["offers"]
    except scraper.NoBrochureError:
        return []


def _index_html(paths):
    items = "\n".join(f'<li><a href="{path}.json">{path}.json</a> (auch <a href="{path}/">{path}/</a>)</li>' for path in paths)
    return (
        '<!doctype html>\n<html lang="de"><head><meta charset="utf-8"><title>Angebote-API</title></head>\n'
        f"<body>\n<h1>Angebote-API</h1>\n<ul>\n{items}\n</ul>\n</body></html>\n"
    )


def build_site(out_dir, today, fetch=None):
    out = Path(out_dir)
    results = {}
    for key, config in retailers.RETAILERS.items():
        loaded = scraper.load_retailer(fetch, config)
        for suffix, days in WEEKS.items():
            offers = _offers(today + timedelta(days=days), fetch, loaded, config)
            check.ensure_valid(offers, label=f"{key}{suffix}")
            results[key + suffix] = offers
    for suffix in WEEKS:
        results[ALL + suffix] = [o for key in retailers.RETAILERS for o in results[key + suffix]]

    for path, offers in results.items():
        text = json.dumps(offers, ensure_ascii=False, indent=1) + "\n"
        for target in (out / f"{path}.json", out / path / "index.html"):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
    (out / ".nojekyll").write_text("")
    (out / "index.html").write_text(_index_html(list(results)), encoding="utf-8")
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
