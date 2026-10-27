import copy
import json
from datetime import date

import pytest

from lidl_angebote import check, normalize, site
from lidl_angebote.normalize import rules
from lidl_angebote.normalize.llm import OllamaError
from lidl_angebote.normalize.pipeline import Normalizer, validate


class FakeLLM:
    model = "fake"

    def __init__(self, fix=lambda t: t, fail=False):
        self.fix, self.fail, self.calls = fix, fail, []

    def correct(self, system, texts):
        self.calls.append(list(texts))
        if self.fail:
            raise OllamaError("aus")
        return [self.fix(t) for t in texts]


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Diese Gläser machen schon beim\nEinschenken\ngute Laune.", "Diese Gläser machen schon beim Einschenken gute Laune"),
        ("Je Stück\\n", "Je Stück"),
        ("Versch. Sorten.", "Versch. Sorten"),
        ("Je 10 Stk.", "Je 10 Stk."),
        ("Frisch ...", "Frisch"),
        ("Milch , Käse,Brot", "Milch, Käse, Brot"),
        ("0,25 Pfand", "0,25 Pfand"),
        ("zzgl. 0.25 Pfand, 1.299 Stück", "zzgl. 0,25 Pfand, 1.299 Stück"),
        ("je 295g, 3,5% Fett, 0,5l", "je 295 g, 3,5 % Fett, 0,5 l"),
        ("Je St.", "Je St."),
        ("zzgl. 0.25€ Pfand", "zzgl. 0,25 € Pfand"),
        ("nur € 1,99", "nur 1,99 €"),
        ("Bio\xadMilch  \xa0 frisch", "BioMilch frisch"),
        ("   ", ""),
    ],
)
def test_clean_german(raw, expected):
    assert rules.clean(raw) == expected


def test_clean_offer_texts_drops_empty_fields_and_duplicate_notes():
    offer = {"id": "1", "name": "Tee.", "brand": "  ", "description": "\n", "notes": ["Je Stück.", "Je Stück", " "]}
    assert rules.clean_offer_texts(offer) == {"id": "1", "name": "Tee", "notes": ["Je Stück"]}


def test_locale_formats_prices_and_dates():
    de = normalize.get_locale("de")
    assert de.format_price(1234.5) == "1.234,50 €"
    assert de.format_price(0.99) == "0,99 €"
    assert de.format_date("2026-10-26") == "26.10.2026"
    assert de.format_date(date(2026, 1, 5)) == "05.01.2026"


def test_locale_is_extensible_and_unknown_code_fails():
    us = normalize.Locale("en-us", ".", ",", "$", False, "%m/%d/%Y", frozenset())
    assert us.format_price(1234.5) == "$1,234.50"
    assert us.format_date("2026-10-26") == "10/26/2026"
    with pytest.raises(ValueError, match="Unbekannte Sprache"):
        normalize.get_locale("xx")


def test_prompt_exists_for_every_locale():
    for locale in normalize.LOCALES.values():
        assert "texts" in locale.prompt


@pytest.mark.parametrize(
    "original, candidate, ok",
    [
        ("BIO-MILCH 3,5 % Fett", "Bio-Milch 3,5 % Fett", True),
        ("Frische Milch.", "Frische Milch", True),  # Schlusspunkt
        ("Versch. Sorten. Tiefgefroren. Je 460 ml", "Versch. Sorten Tiefgefroren Je 460 ml", False),  # innere Punkte bleiben
        ("Nur, solange der Vorrat reicht!", "Nur solange der Vorrat reicht", False),
        ("Gyrossuppe oder Biftekitopf", "Gyrosuppe oder Biftekitopf", True),  # Tippfehler
        ("NUTELLA", "Nutella", True),
        ("Kräuter/ Leicht\nAus Kuhmilch", "Kräuter/ Leicht aus Kuhmilch", True),
        ("Bio-Milch 3,5 % Fett", "Bio-Milch 3,8 % Fett", False),  # Zahl verändert
        ("Bio-Milch 3,5 % Fett", "Bio-Milch 3 % Fett", False),  # Ziffer fehlt
        ("Tee", "Tee\nGrün", False),
        ("Tee", "", False),
        ("Back-Hirtenkäse", "Back-Hirtnägelkäse", False),  # erfundenes Wort
        ("Schoko Kugeln Vollmilch", "Schoko-Kugeln-Vollmilch", False),  # Bindestriche
        ("Versch. Sorten. Tiefgefroren. Je 460 ml", "Versch. Sorten, je 460 ml", False),  # Wort gelöscht
        ("Schokolade Alpenmilch", "Schokolade", False),
        ("Schokolade", "Schokolade Alpenmilch", False),  # Wort hinzugefügt
        ("Anno »1688«", "Anno 1688", False),
        ("Weiße Bohnen", "Weißer Bohnen", False),  # Beugung geändert
        ("Mini-Bifteki", "Mini-Bifteke", False),
        ("Müllermilch ZERO", "Müller-Milch ZERO", False),
        ("2-teilig, je Set", "2-Teilig, je Set", False),
        ("Versch. Sorten, Gekühlt", "Versch. Sorten, gekühlt", True),
        ("je 400 g", "Je 400 g", True),
    ],
)
def test_validate(original, candidate, ok):
    assert validate(original, candidate) is ok


OFFERS = [
    {"id": "1", "name": "BIO-MILCH 3,5 % Fett.", "description": "Je 1 l", "notes": ["Je Stück."], "brand": "Weihenstephan"},
    {"id": "2", "name": "Bio-Milch 3,5 % Fett", "price": 1.0},
]


def test_rules_only_without_llm():
    out = Normalizer().offers(OFFERS)
    assert out[0]["name"] == "BIO-MILCH 3,5 % Fett"
    assert out[0]["notes"] == ["Je Stück"]
    assert OFFERS[0]["name"] == "BIO-MILCH 3,5 % Fett."  # Eingabe unverändert


def test_llm_corrects_validates_and_asks_each_unique_text_once():
    llm = FakeLLM(lambda t: t.replace("BIO-MILCH 3,5 % Fett", "Bio-Milch 3,5 % Fett"))
    out = Normalizer(llm=llm).offers(OFFERS)
    assert out[0]["name"] == "Bio-Milch 3,5 % Fett"
    assert out[1]["name"] == "Bio-Milch 3,5 % Fett"
    asked = [t for call in llm.calls for t in call]
    assert sorted(asked) == sorted(set(asked))  # keine Duplikate
    assert "Weihenstephan" not in asked and "Je Stück" not in asked  # Marke/Notes nie ans Modell


def test_llm_answer_changing_numbers_is_discarded():
    llm = FakeLLM(lambda t: t.replace("3,5", "3,8"))
    out = Normalizer(llm=llm).offers(OFFERS)
    assert out[1]["name"] == "Bio-Milch 3,5 % Fett"


def test_llm_wrong_length_falls_back_to_single_requests():
    class Short(FakeLLM):
        def correct(self, system, texts):
            self.calls.append(list(texts))
            return texts[:1] if len(texts) > 1 else texts

    llm = Short()
    out = Normalizer(llm=llm).offers(OFFERS)
    assert out[1]["name"] == "Bio-Milch 3,5 % Fett"
    assert any(len(c) == 1 for c in llm.calls)


def test_cache_prevents_second_model_call(tmp_path):
    cache = tmp_path / "c" / "cache.json"
    first = FakeLLM(lambda t: t.replace("BIO-MILCH", "Bio-Milch"))
    out1 = Normalizer(llm=first, cache_path=cache).offers(OFFERS)
    assert first.calls and cache.exists()
    second = FakeLLM(fail=True)
    out2 = Normalizer(llm=second, cache_path=cache).offers(OFFERS)
    assert second.calls == [] and out2 == out1


def test_model_outage_degrades_to_rules_and_logs():
    logs = []
    normalizer = Normalizer(llm=FakeLLM(fail=True), log=logs.append)
    out = normalizer.offers(OFFERS)
    assert out[0]["name"] == "BIO-MILCH 3,5 % Fett"
    assert logs and logs[0].startswith("Warnung")


def test_from_args_without_reachable_ollama_warns_and_uses_rules(tmp_path, capsys):
    import argparse

    parser = argparse.ArgumentParser()
    normalize.add_arguments(parser)
    args = parser.parse_args(["--ollama-url", "http://127.0.0.1:9", "--cache", str(tmp_path / "c.json")])
    normalizer = normalize.from_args(args)
    assert normalizer.llm is None
    assert "Warnung" in capsys.readouterr().err


def test_site_build_with_transform_stays_schema_valid(tmp_path, fake_fetch):
    llm = FakeLLM(lambda t: t)
    normalizer = Normalizer(llm=llm)
    site.build_site(tmp_path, date(2026, 9, 29), fetch=fake_fetch, transform=normalizer.offers)
    offers = json.loads((tmp_path / "all.json").read_text(encoding="utf-8"))
    assert offers and check.check_offers(offers) == []
    assert llm.calls
    assert all("\n" not in o.get("description", "") for o in offers)
