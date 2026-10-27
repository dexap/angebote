"""Deterministische Textbereinigung (ohne KI): Escapes, Leerzeichen, Satzpunkte, Preisformat."""

import re

from .locales import DEFAULT

_ESCAPES = re.compile(r"\\[nrt]")  # wörtliche "\n" im Text
_SPACE = re.compile(r"\s+")
_SPACE_BEFORE = re.compile(r"\s+([,;:!?])")
_COMMA_NO_SPACE = re.compile(r"([,;:!?])(?=[^\W\d_])")  # "a,b" -> "a, b" (nicht in "0,25")
_PRICE_BEFORE = re.compile(r"(?:€|EUR)\s*(\d+(?:[.,]\d{1,2})?)")  # "€ 0,99" -> "0,99 €"
_PRICE = re.compile(r"(\d+)[.,](\d{2})\s*(?:€|EUR\b|Euro\b)")  # "0.99€", "0,99 EUR" -> "0,99 €"
_UNIT_GLUE = re.compile(r"(\d)(kg|mg|g|ml|cl|l|cm|mm|m|%)(?![^\W\d_])")  # "500g" -> "500 g"
_DECIMAL_POINT = re.compile(r"(?<=\d)\.(?=\d{1,2}(?!\d))")  # "0.25" -> "0,25" (nicht "1.299")
_LAST_WORD = re.compile(r"([^\W\d_]+)\.$")


def clean(text, locale=DEFAULT):
    """Ein Textfeld bereinigen; gibt "" zurück, wenn nichts übrig bleibt."""
    text = _ESCAPES.sub(" ", text.replace("\xad", ""))
    text = _SPACE.sub(" ", text.replace("\xa0", " ")).strip()
    text = _PRICE_BEFORE.sub(lambda m: f"{m.group(1)} €", text)
    text = _PRICE.sub(lambda m: f"{m.group(1)}{locale.decimal_sep}{m.group(2)} {locale.currency_symbol}", text)
    text = _DECIMAL_POINT.sub(locale.decimal_sep, text)
    text = _UNIT_GLUE.sub(r"\1 \2", text)
    text = _SPACE_BEFORE.sub(r"\1", text)
    text = _COMMA_NO_SPACE.sub(r"\1 ", text)
    text = _strip_final_period(text, locale)
    return _SPACE.sub(" ", text).strip(" ,;:")


def _strip_final_period(text, locale):
    while text.endswith("."):
        word = _LAST_WORD.search(text)
        if word and word.group(1).lower() in locale.abbreviations:
            break
        text = text[:-1].rstrip()
    return text


def clean_offer_texts(offer, locale=DEFAULT):
    """Kopie des Angebots mit bereinigten Textfeldern (``name``, ``brand``, ``description``, ``notes``)."""
    out = dict(offer)
    for field in ("name", "brand", "description"):
        if field in out:
            out[field] = clean(out[field], locale)
    if "notes" in out:
        out["notes"] = list(dict.fromkeys(n for n in (clean(n, locale) for n in out["notes"]) if n))
    return {k: v for k, v in out.items() if v not in ("", [])}
