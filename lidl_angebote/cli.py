import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from . import kaufda, scraper


def default_output_path(ref_date):
    year, week, _ = ref_date.isocalendar()
    return f"data/lidl_{year}-KW{week:02d}.json"


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="lidl-angebote",
        description="Lidl-Lebensmittelangebote der aktuellen Woche von kaufda.de als JSON speichern.",
    )
    parser.add_argument("--date", type=date.fromisoformat, default=kaufda.today(), help="Stichtag (YYYY-MM-DD), Standard: heute")
    parser.add_argument("--output", "-o", help="Ziel-Datei (Standard: data/lidl_<Jahr>-KW<Woche>.json), '-' für stdout")
    parser.add_argument("--next", action="store_true", help="Woche nach dem Stichtag (nächster Prospekt)")
    parser.add_argument("--no-drinks", action="store_true", help="Getränke ausschließen")
    parser.add_argument("--include-long-running", action="store_true", help="auch Langläufer-Prospekte (> 14 Tage)")
    args = parser.parse_args(argv)
    if args.next:
        args.date += timedelta(days=7)

    try:
        result = scraper.scrape(
            args.date,
            include_drinks=not args.no_drinks,
            include_long_running=args.include_long_running,
        )
    except scraper.NoBrochureError as e:
        print(e, file=sys.stderr)
        return 1

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output == "-":
        print(text)
        return 0
    out = Path(args.output or default_output_path(args.date))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    titles = ", ".join(f"{b['title']} ({b['valid_from']} – {b['valid_until']})" for b in result["brochures"])
    print(f"{result['count']} Angebote aus {titles} -> {out}", file=sys.stderr)
    return 0
