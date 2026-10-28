"""Angebote normalisieren: Regeln, dann (optional) Tippfehler-Prüfung durch ein kleines Sprachmodell.

Das Modell bekommt nur nummerierte Texte mit unbekannten Wörtern und meldet nur Korrekturen
(``wort`` -> ``korrekt``); Python wendet sie an und prüft sie (``validate``). Bei Bedenken
entscheidet eine zweite Runde mit Thinking (``judge``) zwischen Original und Korrektur.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

from . import rules
from .corrections import Corrections, default_path
from .llm import Ollama, OllamaError
from .locales import DEFAULT, LOCALES, get_locale

PUNCTUATION = ".,;:!?"
BATCH_SIZE = 16
MIN_TYPO_LENGTH = 6  # kürzere Wörter ändert nur eine Zweitmeinung, nie die Prüfung allein
MODEL_FIELDS = ("name", "description")  # ``brand`` (Eigenname) und ``notes`` (feste Formeln) nur per Regeln
JUDGE_MINUTES = 30  # Zeitbudget je Lauf für Zweitmeinungen (Thinking ist auf der CPU langsam)
LOGIC_VERSION = 3  # erhöhen, wenn sich die Entscheidungslogik ändert: entwertet gespeicherte Ergebnisse
DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_CACHE = Path(os.environ.get("ANGEBOTE_CACHE") or Path.home() / ".cache" / "angebote" / "normalize.json")
_LETTERS = re.compile(r"[^\W\d_]+")


def _digits(text):
    return sorted(re.findall(r"\d", text))


def _core(word):
    return word.strip(PUNCTUATION)  # Satzzeichen am Rand dürfen sich ändern, Klammern/Anführungszeichen nicht


def _tail(word):
    return word[len(word.rstrip(PUNCTUATION)) :]


def _osa(a, b):
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


def _is_typo_fix(old, new):
    """Ein Tippfehler: langes Wort, genau eine Änderung, gleicher Anfang und gleiche Endung (keine Beugung)."""
    a, b = old.lower(), new.lower()
    return (
        len(old) >= MIN_TYPO_LENGTH
        and bool(b)
        and a[0] == b[0]
        and a[-2:] == b[-2:]
        and old.count("-") == new.count("-")
        and _osa(a, b) == 1
    )


def _title(word):
    return "-".join(part.capitalize() for part in word.split("-"))


def _word_ok(old, new):
    """Erlaubte Änderung eines Wortes: übliche Schreibweise (klein, Satzanfang, bei Versalien auch Titel) oder Tippfehler."""
    if old == new:
        return True
    if old.lower() == new.lower():
        return new == new.lower() or new == new[0].upper() + new[1:].lower() or (old.isupper() and new == _title(new))
    return _is_typo_fix(old, new)


def _inflected(original, candidate):
    """Ändert sich bei gleicher Wortzahl die Endung eines Wortes (Beugung: Wurzel -> Wurzeln)? Das beurteilt das Modell unzuverlässig."""
    old, new = original.split(), candidate.split()
    return len(old) == len(new) and any(
        _core(a) != _core(b) and _core(a).lower() != _core(b).lower() and _core(a)[-2:].lower() != _core(b)[-2:].lower()
        for a, b in zip(old, new)
    )


def hard_ok(original, candidate):
    """Untergrenze, die auch die Zweitmeinung nicht kippt: keine Umbrüche/Escapes, Ziffern und Wortendungen unverändert."""
    if not candidate.strip() or "\n" in candidate or "\\" in candidate:
        return False
    return _digits(original) == _digits(candidate) and not _inflected(original, candidate)


def validate(original, candidate):
    """Übernimmt der Regeltext die Korrektur? Nur Änderungen einzelner Wörter (siehe ``_word_ok``) sind erlaubt."""
    if not hard_ok(original, candidate):
        return False
    old, new = original.split(), candidate.split()
    if len(old) != len(new):
        return False
    for i, (a, b) in enumerate(zip(old, new)):
        if not _word_ok(_core(a), _core(b)):
            return False
        if i < len(old) - 1 and _tail(a) != _tail(b):  # nur am Textende dürfen Satzzeichen wegfallen
            return False
    return True


def _parts(text):
    """Prüfbare Wortteile (klein geschrieben): Buchstabenfolgen ab ``MIN_TYPO_LENGTH``, auch in ``Deutschland/Italien``."""
    return [p.lower() for p in _LETTERS.findall(text) if len(p) >= MIN_TYPO_LENGTH]


def _usable(fix, abbreviations):
    """Nur echte Wortkorrekturen: nicht leer, keine Abkürzung (``Versch.``), nicht nur Groß-/Kleinschreibung (das machen die Regeln)."""
    wrong, right = fix["wort"].strip(), fix["korrekt"].strip()
    return bool(wrong and right) and wrong.lower() != right.lower() and wrong.lower().strip(".") not in abbreviations


def _apply(text, fixes, abbreviations=frozenset()):
    """Text mit den gemeldeten Korrekturen oder ``None``, wenn keine auf ein ganzes Wort des Textes passt."""
    changed = False
    for fix in fixes:
        if not _usable(fix, abbreviations):
            continue
        wrong, right = fix["wort"].strip(), fix["korrekt"].strip()
        found = re.compile(r"(?<![^\W\d_])%s(?![^\W\d_])" % re.escape(wrong))
        text, count = found.subn(lambda _: right, text)
        changed = changed or count > 0
    return text if changed else None


def _applied(text, fixes, abbreviations=frozenset()):
    """Die Korrekturen, die auf ein ganzes Wort des Textes passen (nur diese werden gelernt)."""
    return [f for f in fixes if _usable(f, abbreviations) and _apply(text, [f], abbreviations) is not None]


class Normalizer:
    def __init__(self, locale=DEFAULT, llm=None, cache_path=None, log=None, judge_budget=0, corrections=None):
        """``judge_budget``: Sekunden je Lauf für die Zweitmeinung (0 = aus); ``corrections``: Wörterbuch (``Corrections``)."""
        self.locale, self.llm, self.corrections = locale, llm, corrections
        self.cache_path = Path(cache_path) if cache_path else None
        self.log = log or (lambda message: None)
        self.prompt, self.judge_prompt = locale.prompt, locale.judge_prompt
        self.judge_budget, self._judge_spent = judge_budget, 0.0
        self.stats = dict.fromkeys(
            ("texts", "dictionary", "skipped", "asked", "fixed", "rejected", "judged", "judge_took_change", "pending", "rules_only"), 0
        )
        self._cache = self._load()
        prompts = hashlib.sha1((self.prompt + self.judge_prompt).encode()).hexdigest()
        self._salt = f"{llm.model if llm else ''}|{prompts}|v{LOGIC_VERSION}"
        self._vocab = set((self._cache.get(self._key("\0vocab")) or {}).get("words", []))

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

    def _final(self, text):
        value = self._cache.get(self._key(text))
        return value if isinstance(value, str) else None

    def _pending(self, text):
        value = self._cache.get(self._key(text))
        return value["pending"] if isinstance(value, dict) else None

    def _confirmed(self, fixes):
        """Kommen die korrigierten Wörter schon in anderen Texten vor? Sonst fehlt der Beleg für die Korrektur."""
        return all(p in self._vocab for f in fixes for p in _parts(f["korrekt"]))

    def _remember(self, fixes):
        """Bestätigte Korrekturen ins Wörterbuch aufnehmen (wirkt ab dem nächsten Text)."""
        for fix in fixes:
            if self.corrections is not None and self.corrections.learn(fix["wort"], fix["korrekt"]):
                self.log(f"Wörterbuch lernt: {fix['wort']!r} -> {fix['korrekt']!r}")

    def _pending_fixes(self, text):
        value = self._cache.get(self._key(text))
        return value.get("fixes", []) if isinstance(value, dict) else []

    def _known(self, part):
        return self._cache.get(self._key("wort|" + part)) == 1

    def _unknown_parts(self, text):
        return [p for p in _parts(text) if not self._known(p)]

    def _learn(self, text, fixed_words=()):
        """Die Wörter des Textes gelten als geprüft (außer den korrigierten)."""
        skip = {w.lower() for w in fixed_words}
        for part in _parts(text):
            if part not in skip:
                self._cache[self._key("wort|" + part)] = 1

    def _first_pass(self, texts):
        """Fragt das Modell nach Tippfehlern; unplausible Vorschläge werden für die Zweitmeinung vorgemerkt."""
        todo = [t for t in texts if self._final(t) is None and self._pending(t) is None and self._unknown_parts(t)]
        self.stats["skipped"] += len(texts) - len(todo)
        for start in range(0, len(todo), BATCH_SIZE):
            batch = todo[start : start + BATCH_SIZE]
            try:
                fixes = self.llm.typos(self.prompt, batch)
            except OllamaError as e:
                self.log(f"Warnung: {e}; Rest nur mit Regeln")
                self.llm = None
                return
            self.stats["asked"] += len(batch)
            for index, text in enumerate(batch, 1):
                own = [f for f in fixes if f["id"] == index and _usable(f, self.locale.abbreviations)]
                candidate = _apply(text, own, self.locale.abbreviations)
                if candidate is None:
                    self._cache[self._key(text)] = text
                elif validate(text, candidate) and self._confirmed(own):
                    self._cache[self._key(text)] = candidate
                    self._remember(_applied(text, own, self.locale.abbreviations))
                    self.stats["fixed"] += 1
                elif self.judge_budget and hard_ok(text, candidate):
                    applied = _applied(text, own, self.locale.abbreviations)
                    self._cache[self._key(text)] = {"pending": candidate, "fixes": [[f["wort"], f["korrekt"]] for f in applied]}
                else:
                    self._cache[self._key(text)] = text
                    self.stats["rejected"] += 1
                self._learn(text, [f["wort"] for f in own])
            self._save()
            self.log(f"{min(start + BATCH_SIZE, len(todo))}/{len(todo)} Texte auf Tippfehler geprüft")

    def _judge(self, text, context):
        """Zweitmeinung (Thinking) zwischen Regeltext und Korrektur; Reihenfolge je Text zufällig, aber stabil."""
        field, offer = context[text]
        change = self._pending(text)
        swap = int(hashlib.sha1(text.encode()).hexdigest(), 16) % 2 == 1
        a, b = (change, text) if swap else (text, change)
        started = time.monotonic()
        try:
            choice = self.llm.judge(self.judge_prompt, {"feld": field, "angebot": offer, "a": a, "b": b})
        finally:
            self._judge_spent += time.monotonic() - started
        picked = {"a": a, "b": b}.get(choice, text)  # keine verwertbare Antwort: Original behalten
        if picked == change:
            self._remember({"wort": w, "korrekt": k} for w, k in self._pending_fixes(text))
        self._cache[self._key(text)] = picked
        self.stats["judged"] += 1
        self.stats["judge_took_change"] += picked == change
        self._save()

    def _second_pass(self, texts, context):
        pending = [t for t in texts if self._pending(t) is not None]
        for index, text in enumerate(pending):
            if self._judge_spent >= self.judge_budget:
                self.stats["pending"] += len(pending) - index
                self.log(f"{len(pending) - index} Zweitmeinungen verschoben (Zeitbudget aufgebraucht), folgen im nächsten Lauf")
                return
            try:
                self._judge(text, context)
            except OllamaError as e:
                self.log(f"Warnung: {e}; Zweitmeinungen verschoben")
                self.llm = None
                self.stats["pending"] += len(pending) - index
                return
            self.log(f"Zweitmeinung {index + 1}/{len(pending)}: {text!r} -> {self._final(text)!r}")

    def _resolve(self, texts, context):
        """``{regeltext: endtext}`` für alle Texte; füllt den Cache auf."""
        if self.llm is not None:
            self._first_pass(texts)
        if self.llm is not None and self.judge_budget:
            self._second_pass(texts, context)
        self.stats["rules_only"] += sum(1 for t in texts if self._final(t) is None and self._unknown_parts(t))
        return {t: self._final(t) or t for t in texts}

    def _translate(self, offer):
        """Wörterbuch auf ``name`` und ``description`` anwenden, vor Cache und Modell."""
        if not self.corrections:
            return offer
        out = dict(offer)
        for field in MODEL_FIELDS:
            if field in out:
                out[field] = self.corrections.apply(out[field])
        self.stats["dictionary"] += out != offer
        return out

    def offers(self, offers):
        """Normalisierte Kopie der Angebote (Eingabe bleibt unverändert)."""
        cleaned = [self._translate(rules.clean_offer_texts(o, self.locale)) for o in offers]
        context = {}  # Text -> (Feld, vollständiges Angebot) als Beleg für die Zweitmeinung
        for offer in cleaned:
            for field in MODEL_FIELDS:
                if field in offer:
                    context.setdefault(offer[field], (field, offer))
        texts = list(context)
        self.stats["texts"] += len(texts)
        for text in texts:
            self._vocab.update(_parts(text))
        self._cache[self._key("\0vocab")] = {"words": sorted(self._vocab)}
        mapping = self._resolve(texts, context)
        return [dict(o, **{f: mapping[o[f]] for f in MODEL_FIELDS if f in o}) for o in cleaned]


def normalize_offers(offers, locale=DEFAULT, llm=None, cache_path=None, judge_budget=0, corrections=None):
    return Normalizer(locale, llm, cache_path, judge_budget=judge_budget, corrections=corrections).offers(offers)


# --- Kommandozeile ------------------------------------------------------------------------------


def add_arguments(parser):
    group = parser.add_argument_group("Normalisierung")
    group.add_argument("--lang", default=DEFAULT.code, choices=sorted(LOCALES), help="Sprache (Standard: de)")
    group.add_argument("--no-llm", action="store_true", help="nur Regeln, kein Sprachmodell")
    group.add_argument("--model", default=os.environ.get("ANGEBOTE_MODEL", DEFAULT_MODEL), help=f"Ollama-Modell (Standard: {DEFAULT_MODEL})")
    group.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))
    group.add_argument("--no-judge", action="store_true", help="keine Zweitmeinung (Thinking) bei abgelehnten Korrekturen")
    group.add_argument(
        "--judge-minutes", type=float, default=float(os.environ.get("ANGEBOTE_JUDGE_MINUTES", JUDGE_MINUTES)),
        help=f"Zeitbudget je Lauf für Zweitmeinungen in Minuten (Standard: {JUDGE_MINUTES}); Rest folgt im nächsten Lauf",
    )
    group.add_argument("--corrections", type=Path, help=f"Wörterbuch-Datei (Standard: {default_path()})")
    group.add_argument("--no-corrections", action="store_true", help="Wörterbuch weder anwenden noch lernen")
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
    budget = 0 if args.no_judge else args.judge_minutes * 60
    corrections = None if args.no_corrections else Corrections(args.corrections or default_path(args.lang), log=_log)
    return Normalizer(get_locale(args.lang), llm, args.cache, log=_log, judge_budget=budget, corrections=corrections)


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
