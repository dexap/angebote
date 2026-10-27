"""Deterministische Textbereinigung (ohne KI): Escapes, Leerzeichen, Abkürzungen, Satzpunkte, Preisformat, Versalien."""

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
_WORD = re.compile(r"(?<![^\W\d_])([^\W\d_]+)(\.?)(?![^\W\d_])")  # Wort mit optionalem Punkt; auch hinter "-" ("230-g-Pckg.")
_SAINT = re.compile(r" [A-ZÄÖÜ]")  # "St. Moritz" ist kein "Stück"
_BEFORE_SORTEN = re.compile(r"(?<![^\W\d_])([^\W\d_]{5,7})\.?(?= Sorten\b)")  # Tippfehler in "Versch. Sorten"


def clean(text, locale=DEFAULT):
    """Ein Textfeld bereinigen; gibt "" zurück, wenn nichts übrig bleibt."""
    text = _ESCAPES.sub(" ", text.replace("\xad", ""))
    text = _SPACE.sub(" ", text.replace("\xa0", " ")).strip()
    text = _PRICE_BEFORE.sub(lambda m: f"{m.group(1)} €", text)
    text = _PRICE.sub(lambda m: f"{m.group(1)}{locale.decimal_sep}{m.group(2)} {locale.currency_symbol}", text)
    text = _DECIMAL_POINT.sub(locale.decimal_sep, text)
    text = _UNIT_GLUE.sub(r"\1 \2", text)
    text = expand_abbreviations(text, locale)
    text = _SPACE_BEFORE.sub(r"\1", text)
    text = _COMMA_NO_SPACE.sub(r"\1 ", text)
    text = _strip_final_period(text, locale)
    return _SPACE.sub(" ", text).strip(" ,;:")


def edit_distance(a, b):
    """Edit-Distanz (Einfügen, Löschen, Ersetzen, Vertauschen zweier Nachbarn = je 1)."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def _as_written(word, full):
    """Anfangsbuchstabe wie in der Abkürzung: ``Ca.`` -> ``Circa``, ``ca.`` -> ``circa``."""
    return full[0].upper() + full[1:] if word[:1].isupper() else full


def expand_abbreviations(text, locale=DEFAULT):
    """Abkürzungen ausschreiben (``Versch.`` -> ``Verschiedene``, ``230-g-Pckg.`` -> ``230-g-Packung``); Einheiten und ``Vol.`` bleiben."""
    for phrase, full in locale.phrase_expansions:
        found = re.compile(r"(?<![^\W\d_])" + re.escape(phrase).replace(r"\ ", r"\s?") + r"(?![^\W\d_])", re.IGNORECASE)
        text = found.sub(full, text)
    table = dict(locale.expansions)

    def single(match):
        word, dot = match.groups()
        key = word.lower() + dot
        if key == "min.":  # "40 Min." = Minuten, sonst "Min. 2 Stück" = mindestens
            return "Minuten" if text[: match.start()].rstrip()[-1:].isdigit() else _as_written(word, "mindestens")
        full = table.get(key)
        if full is None or (key == "st." and _SAINT.match(text, match.end())):
            return match.group(0)
        return _as_written(word, full)

    def typo(match):  # "Verscg Sorten" -> "Verschiedene Sorten"
        word = match.group(1)
        return _as_written(word, table["versch."]) if edit_distance(word.lower(), "versch") == 1 else match.group(0)

    if "versch." in table:
        text = _BEFORE_SORTEN.sub(typo, text)
    return _WORD.sub(single, text)


def _strip_final_period(text, locale):
    while text.endswith("."):
        word = _LAST_WORD.search(text)
        if word and word.group(1).lower() in locale.abbreviations:
            break
        text = text[:-1].rstrip()
    return text


def _title(word):
    return "-".join(part.capitalize() for part in word.split("-"))


def fix_case(text, locale=DEFAULT):
    """Versalien-Wörter normal schreiben (``NUTELLA`` -> ``Nutella``) und den Textanfang groß (``je 5 g`` -> ``Je 5 g``)."""
    words = text.split(" ")
    for i, word in enumerate(words):
        core = word.strip(".,;:!?()»«\"'/")
        letters = core.replace("-", "")
        if letters.isalpha() and letters.isupper() and len(letters) >= locale.shouting_min_letters:
            words[i] = word.replace(core, _title(core), 1)
        elif i == 0 and core[:1].islower() and core.isalpha() and core == core.lower():  # nicht "iPhone", "2-teilig"
            words[i] = word.replace(core, core[0].upper() + core[1:], 1)
    return " ".join(words)


def clean_offer_texts(offer, locale=DEFAULT):
    """Kopie des Angebots mit bereinigten Textfeldern (``name``, ``brand``, ``description``, ``notes``)."""
    out = dict(offer)
    for field in ("name", "brand", "description"):
        if field in out:
            out[field] = clean(out[field], locale)
            if field != "brand":  # Marken behalten ihre Schreibweise (TUBORG, REWE)
                out[field] = fix_case(out[field], locale)
    if "notes" in out:
        out["notes"] = list(dict.fromkeys(n for n in (clean(n, locale) for n in out["notes"]) if n))
    return {k: v for k, v in out.items() if v not in ("", [])}
