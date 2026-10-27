"""Sprach- und Länderspezifisches an einer Stelle: Zahlen, Währung, Datum, Prompt.

Neue Sprache = ein ``Locale`` hier eintragen und ``prompts/<code>.md`` anlegen.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

PROMPTS = Path(__file__).parent / "prompts"


@dataclass(frozen=True)
class Locale:
    code: str
    decimal_sep: str  # trennt Euro und Cent
    thousands_sep: str
    currency_symbol: str
    currency_after: bool  # "0,99 €" (True) oder "€0.99" (False)
    date_format: str  # strftime
    abbreviations: frozenset  # Wörter, deren Schlusspunkt zur Abkürzung gehört
    shouting_min_letters: int = 5  # GROSSGESCHRIEBENE Wörter ab so vielen Buchstaben werden normal geschrieben (kürzere sind meist Kürzel)
    expansions: tuple = ()  # (Abkürzung, ausgeschrieben): "versch." -> "verschiedene"; ohne Punkt im Schlüssel gilt auch das Wort allein
    phrase_expansions: tuple = ()  # dasselbe für Abkürzungen aus mehreren Teilen: "z. B." -> "zum Beispiel"

    @property
    def prompt(self):
        return (PROMPTS / f"{self.code}.md").read_text(encoding="utf-8")

    @property
    def judge_prompt(self):
        return (PROMPTS / f"{self.code}.judge.md").read_text(encoding="utf-8")

    def format_price(self, amount):
        whole, cents = f"{amount:,.2f}".split(".")
        whole = whole.replace(",", self.thousands_sep)
        number = f"{whole}{self.decimal_sep}{cents}"
        return f"{number} {self.currency_symbol}" if self.currency_after else f"{self.currency_symbol}{number}"

    def format_date(self, value):
        return (value if isinstance(value, date) else date.fromisoformat(value)).strftime(self.date_format)


DE = Locale(
    code="de",
    decimal_sep=",",
    thousands_sep=".",
    currency_symbol="€",
    currency_after=True,
    date_format="%d.%m.%Y",
    abbreviations=frozenset(
        "stk st pck pckg pkg ca inkl zzgl versch vol max min mind ggf bzw evtl etc nr usw u a z b d h".split()
    ),
    expansions=(
        ("versch.", "verschiedene"),
        ("zzgl.", "zuzüglich"),
        ("inkl.", "inklusive"),
        ("ca.", "circa"),
        ("max.", "maximal"),
        ("mind.", "mindestens"),
        ("ggf.", "gegebenenfalls"),
        ("bzw.", "beziehungsweise"),
        ("evtl.", "eventuell"),
        ("usw.", "und so weiter"),
        ("nr.", "Nummer"),
        ("tw.", "teilweise"),
        ("teilw.", "teilweise"),
        ("kl.", "Klasse"),
        ("gr.", "Größe"),
        ("fl.", "Flasche"),
        ("st.", "Stück"),
        ("stk.", "Stück"),
        ("stck", "Stück"),
        ("stck.", "Stück"),
        ("pck.", "Packung"),
        ("pckg.", "Packung"),
        ("pkg.", "Packung"),
    ),
    phrase_expansions=(
        ("z. B.", "zum Beispiel"),
        ("d. h.", "das heißt"),
        ("u. a.", "unter anderem"),
        ("i. Tr.", "in der Trockenmasse"),
        ("o. Abb.", "ohne Abbildung"),
    ),
)

LOCALES = {loc.code: loc for loc in (DE,)}
DEFAULT = DE


def get_locale(code):
    try:
        return LOCALES[code]
    except KeyError:
        raise ValueError(f"Unbekannte Sprache {code!r}; vorhanden: {', '.join(sorted(LOCALES))}") from None
