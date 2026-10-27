"""Angebote normalisieren: Regeln, dann (optional) Sprachmodell mit Validierung und Cache."""

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from . import rules
from .llm import Ollama, OllamaError
from .locales import DEFAULT, LOCALES, get_locale

PUNCTUATION = ".,;:!?"
BATCH_SIZE = 8
MIN_WORD_SIMILARITY = 0.93  # Buchstabenänderungen nur bei langen Wörtern mit einem Tippfehler (Neuerfindung nein)
MODEL_FIELDS = ("name", "description")  # ``brand`` (Eigenname) und ``notes`` (feste Formeln) nur per Regeln
DEFAULT_CACHE = Path(os.environ.get("ANGEBOTE_CACHE") or Path.home() / ".cache" / "angebote" / "normalize.json")


def _digits(text):
    return sorted(re.findall(r"\d", text))


def _core(word):
    return word.strip(PUNCTUATION)  # Satzzeichen am Rand dürfen sich ändern, Klammern/Anführungszeichen nicht


def _tail(word):
    return word[len(word.rstrip(PUNCTUATION)) :]


def _title(word):
    return "-".join(part.capitalize() for part in word.split("-"))


def _word_ok(old, new):
    """Erlaubte Änderung eines Wortes: übliche Schreibweise (klein, Satzanfang, bei Versalien auch Titel) oder Tippfehler."""
    if old == new:
        return True
    if old.lower() == new.lower():
        return new == new.lower() or new == new[0].upper() + new[1:].lower() or (old.isupper() and new == _title(new))
    if old.count("-") != new.count("-"):
        return False
    return difflib.SequenceMatcher(None, old, new).ratio() >= MIN_WORD_SIMILARITY


def validate(original, candidate):
    """Übernimmt der Regeltext das Modellergebnis?

    Erlaubt sind nur Änderungen einzelner Wörter (siehe ``_word_ok``). Wörter hinzufügen, löschen,
    zusammenziehen oder Ziffern ändern darf das Modell nicht; dann bleibt der Regeltext.
    """
    if not candidate.strip() or "\n" in candidate or "\\" in candidate:
        return False
    if _digits(original) != _digits(candidate):
        return False
    old, new = original.split(), candidate.split()
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag != "replace" or i2 - i1 != j2 - j1:
            return False
        for offset, (a, b) in enumerate(zip(old[i1:i2], new[j1:j2])):
            if not _word_ok(_core(a), _core(b)):
                return False
            if i1 + offset < len(old) - 1 and _tail(a) != _tail(b):  # nur am Textende dürfen Satzzeichen wegfallen
                return False
    return True


class Normalizer:
    def __init__(self, locale=DEFAULT, llm=None, cache_path=None, log=None):
        self.locale, self.llm = locale, llm
        self.cache_path = Path(cache_path) if cache_path else None
        self.log = log or (lambda message: None)
        self.prompt = locale.prompt
        self.stats = {"texts": 0, "cached": 0, "model": 0, "kept": 0, "rules_only": 0}
        self._cache = self._load()
        self._salt = f"{llm.model if llm else ''}|{hashlib.sha1(self.prompt.encode()).hexdigest()}"

    def _load(self):
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8")) if self.cache_path else {}
        except (OSError, ValueError):
            return {}

    def _save(self):
        if not self.cache_path:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._cache, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.cache_path)

    def _key(self, text):
        return hashlib.sha1(f"{self._salt}|{self.locale.code}|{text}".encode()).hexdigest()

    def _ask(self, texts):
        """Modellantwort je Text oder ``None`` (Länge falsch); Einzelanfrage als Rückfall."""
        answer = self.llm.correct(self.prompt, texts)
        if len(answer) == len(texts):
            return answer
        if len(texts) == 1:
            return [None]
        return [r for text in texts for r in self._ask([text])]

    def _resolve(self, texts):
        """``{regeltext: endtext}`` für alle Texte; füllt den Cache auf."""
        todo = [t for t in texts if len(t) > 2 and self._key(t) not in self._cache]
        self.stats["cached"] += len(texts) - len(todo)
        if self.llm is not None:
            for start in range(0, len(todo), BATCH_SIZE):
                batch = todo[start : start + BATCH_SIZE]
                try:
                    answers = self._ask(batch)
                except OllamaError as e:
                    self.log(f"Warnung: {e}; Rest nur mit Regeln")
                    self.llm = None
                    break
                for text, answer in zip(batch, answers):
                    fixed = rules.clean(answer, self.locale) if answer else ""
                    ok = bool(fixed) and validate(text, fixed)
                    self._cache[self._key(text)] = fixed if ok else text
                    self.stats["model" if ok else "kept"] += 1
                self._save()
                self.log(f"{min(start + BATCH_SIZE, len(todo))}/{len(todo)} Texte vom Modell geprüft")
        self.stats["rules_only"] += sum(1 for t in todo if self._key(t) not in self._cache)
        return {t: self._cache.get(self._key(t), t) for t in texts}

    def offers(self, offers):
        """Normalisierte Kopie der Angebote (Eingabe bleibt unverändert)."""
        cleaned = [rules.clean_offer_texts(o, self.locale) for o in offers]
        texts = list(dict.fromkeys(o[f] for o in cleaned for f in MODEL_FIELDS if f in o))
        self.stats["texts"] += len(texts)
        mapping = self._resolve(texts)
        out = []
        for offer in cleaned:
            offer = dict(offer, **{f: mapping[offer[f]] for f in MODEL_FIELDS if f in offer})
            out.append(offer)
        return out


def normalize_offers(offers, locale=DEFAULT, llm=None, cache_path=None):
    return Normalizer(locale, llm, cache_path).offers(offers)


# --- Kommandozeile ------------------------------------------------------------------------------


def add_arguments(parser):
    group = parser.add_argument_group("Normalisierung")
    group.add_argument("--lang", default=DEFAULT.code, choices=sorted(LOCALES), help="Sprache (Standard: de)")
    group.add_argument("--no-llm", action="store_true", help="nur Regeln, kein Sprachmodell")
    group.add_argument("--model", default=os.environ.get("ANGEBOTE_MODEL", "qwen3.5:2b"), help="Ollama-Modell")
    group.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))
    group.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help=f"Cache-Datei (Standard: {DEFAULT_CACHE})")


def _log(message):
    prefix = "::warning::" if message.startswith("Warnung") and os.environ.get("GITHUB_ACTIONS") else ""
    print(prefix + message, file=sys.stderr, flush=True)


def from_args(args):
    llm = None
    if not args.no_llm:
        llm = Ollama(args.ollama_url, args.model)
        if not llm.available():
            _log(f"Warnung: Ollama-Modell {args.model} unter {args.ollama_url} nicht erreichbar; nur Regeln")
            llm = None
    return Normalizer(get_locale(args.lang), llm, args.cache, log=_log)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="lidl-angebote-normalize", description="Angebots-JSON normalisieren.")
    parser.add_argument("input", nargs="?", default="-", help="JSON-Datei mit Angeboten (Standard: stdin)")
    parser.add_argument("--output", default="-", help="Ausgabe (Standard: stdout)")
    add_arguments(parser)
    args = parser.parse_args(argv)

    source = sys.stdin if args.input == "-" else open(args.input, encoding="utf-8")
    offers = json.load(source)
    normalizer = from_args(args)
    text = json.dumps(normalizer.offers(offers), ensure_ascii=False, indent=1) + "\n"
    if args.output == "-":
        sys.stdout.write(text)
    else:
        Path(args.output).write_text(text, encoding="utf-8")
    print(normalizer.stats, file=sys.stderr)
    return 0
