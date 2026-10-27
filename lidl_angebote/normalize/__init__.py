"""Text-Normalisierung der Angebote: deterministische Regeln + kleines lokales Sprachmodell (Ollama).

``python -m lidl_angebote.normalize <Verzeichnis>`` schreibt die JSON-Dateien der API in-place um.
Zahlen, Preise und Datumsangaben fasst nur der Regel-Teil an (je Sprache in ``locales.py``);
das Modell korrigiert Rechtschreibung und wird bei jeder Abweichung verworfen (``validate``).
"""

from .locales import DEFAULT, LOCALES, Locale, get_locale
from .pipeline import Normalizer, add_arguments, from_args, normalize_offers

__all__ = ["DEFAULT", "LOCALES", "Locale", "Normalizer", "add_arguments", "from_args", "get_locale", "normalize_offers"]
