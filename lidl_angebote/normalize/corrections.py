"""Wörterbuch „falsch -> richtig“: einmal bestätigte Korrekturen werden ohne KI auf alle Texte angewandt.

Liegt als einfache JSON-Datei außerhalb des Repos (Standard ``~/.local/share/angebote/corrections.<sprache>.json``,
Verzeichnis per ``ANGEBOTE_DATA``). Schlüssel sind klein geschrieben, Wörter oder Wortgruppen; die Datei darf von Hand
bearbeitet werden (``python -m lidl_angebote.normalize.wordbook --help``). Gelernt wird nur, was die Prüfung oder
die Zweitmeinung bestanden hat. Ist die Datei nicht lesbar, wird sie nie überschrieben.
"""

import json
import os
import re
from pathlib import Path

from .locales import DEFAULT

DATA_DIR = Path(os.environ.get("ANGEBOTE_DATA") or Path.home() / ".local" / "share" / "angebote")
_LETTER = r"[^\W\d_]"


def default_path(lang=DEFAULT.code):
    return DATA_DIR / f"corrections.{lang}.json"


def _match_case(matched, right):
    """Der erste Buchstabe folgt dem gefundenen Text (Satzanfang bleibt groß, Mitte bleibt klein)."""
    if matched[:1].isupper():
        return right[:1].upper() + right[1:]
    return right[:1].lower() + right[1:]


class Corrections:
    def __init__(self, path=None, log=None):
        self.path = Path(path) if path else None
        self.log = log or (lambda message: None)
        self._entries, self._readonly, self._pattern = {}, False, None
        self._load()

    def _load(self):
        if not self.path or not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
                raise ValueError("erwartet ein Objekt mit Text-Werten")
        except (OSError, ValueError) as e:
            self._readonly = True
            self.log(f"Warnung: Wörterbuch {self.path} nicht lesbar ({e}); wird ignoriert und nicht verändert")
            return
        self._entries = {k.strip().lower(): v.strip() for k, v in data.items() if k.strip() and v.strip()}

    def _save(self):
        if not self.path or self._readonly:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(dict(sorted(self._entries.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def __len__(self):
        return len(self._entries)

    def __contains__(self, wrong):
        return wrong.strip().lower() in self._entries

    def items(self):
        return sorted(self._entries.items())

    def apply(self, text):
        """Text mit allen bekannten Korrekturen; nur ganze Wörter bzw. Wortgruppen, Großschreibung am Anfang bleibt."""
        if not self._entries:
            return text
        if self._pattern is None:
            keys = sorted(self._entries, key=len, reverse=True)  # längste zuerst: Wortgruppen vor Einzelwörtern
            self._pattern = re.compile(
                r"(?<!%s)(?:%s)(?!%s)" % (_LETTER, "|".join(re.escape(k) for k in keys), _LETTER), re.IGNORECASE
            )
        return self._pattern.sub(lambda m: _match_case(m.group(0), self._entries[m.group(0).lower()]), text)

    def learn(self, wrong, right):
        """Neue Korrektur merken; ``True``, wenn der Eintrag neu ist. Bestehende Einträge werden nie überschrieben."""
        wrong, right = wrong.strip(), right.strip()
        key = wrong.lower()
        if not wrong or not right or key == right.lower() or self._readonly:
            return False
        if key in self._entries:
            if self._entries[key].lower() != right.lower():
                self.log(f"Warnung: Wörterbuch kennt {wrong!r} schon als {self._entries[key]!r}, nicht {right!r}")
            return False
        self._entries[key], self._pattern = right, None
        self._save()
        return True

    def forget(self, wrong):
        removed = self._entries.pop(wrong.strip().lower(), None) is not None
        if removed:
            self._pattern = None
            self._save()
        return removed
