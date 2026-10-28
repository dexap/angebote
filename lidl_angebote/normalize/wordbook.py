"""Kommandozeile für das Wörterbuch: ``python -m lidl_angebote.normalize.wordbook list|add|remove``."""

import argparse
import sys
from pathlib import Path

from .corrections import Corrections, default_path
from .locales import DEFAULT, LOCALES


def main(argv=None):
    parser = argparse.ArgumentParser(prog="lidl-angebote-corrections", description="Wörterbuch „falsch -> richtig“ pflegen.")
    parser.add_argument("--lang", default=DEFAULT.code, choices=sorted(LOCALES))
    parser.add_argument("--file", type=Path, help="Datei (Standard: %s)" % default_path())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="alle Einträge anzeigen")
    add = commands.add_parser("add", help="Eintrag hinzufügen")
    add.add_argument("wrong")
    add.add_argument("right")
    remove = commands.add_parser("remove", help="Eintrag löschen")
    remove.add_argument("wrong")
    args = parser.parse_args(argv)

    corrections = Corrections(args.file or default_path(args.lang), log=lambda m: print(m, file=sys.stderr))
    if args.command == "list":
        for wrong, right in corrections.items():
            print(f"{wrong} -> {right}")
        print(f"{len(corrections)} Einträge", file=sys.stderr)
    elif args.command == "add":
        print("hinzugefügt" if corrections.learn(args.wrong, args.right) else "nichts geändert (vorhanden, gleich oder Datei nicht lesbar)")
    else:
        print("gelöscht" if corrections.forget(args.wrong) else "nicht gefunden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
