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

    @property
    def prompt(self):
        return (PROMPTS / f"{self.code}.md").read_text(encoding="utf-8")

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
        "stk st pck pckg pkg ca inkl zzgl versch vol max min mind ggf bzw evtl etc nr usw u a z b d h g kg ml l cl".split()
    ),
)

LOCALES = {loc.code: loc for loc in (DE,)}
DEFAULT = DE


def get_locale(code):
    try:
        return LOCALES[code]
    except KeyError:
        raise ValueError(f"Unbekannte Sprache {code!r}; vorhanden: {', '.join(sorted(LOCALES))}") from None
