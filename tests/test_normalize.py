import argparse
import json
import re
from datetime import date

import pytest

from lidl_angebote import check, normalize, site
from lidl_angebote.normalize import rules
from lidl_angebote.normalize.llm import Ollama, OllamaError
from lidl_angebote.normalize.pipeline import BATCH_SIZE, Normalizer, validate


class FakeLLM:
    """Meldet Tippfehler aus ``typos`` ({falsch: richtig}); ``choose`` entscheidet die Zweitmeinung."""

    model = "fake"

    def __init__(self, typos=None, fail=False, choose=None):
        self.map, self.fail, self.choose, self.calls, self.judged = typos or {}, fail, choose, [], []

    def typos(self, system, texts):
        self.calls.append(list(texts))
        if self.fail:
            raise OllamaError("aus")
        return [
            {"id": i, "wort": w, "korrekt": self.map[w]}
            for i, text in enumerate(texts, 1)
            for w in re.findall(r"[^\W\d_]+", text)
            if w in self.map
        ]

    def judge(self, system, payload):
        self.judged.append(payload)
        if self.fail:
            raise OllamaError("aus")
        return self.choose(payload)


# --- Regeln ------------------------------------------------------------------------------------------


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


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("NUTELLA", "Nutella"),
        ("BIO-MILCH 3,5 % Fett", "Bio-Milch 3,5 % Fett"),
        ("HDMI Kabel", "HDMI Kabel"),  # kurz = Kürzel
        ("je 400 g", "Je 400 g"),
        ("versch. Sorten", "Versch. Sorten"),
        ("iPhone Hülle", "iPhone Hülle"),
        ("2-teilig, je Set", "2-teilig, je Set"),
        ("Tee aus Bio-Anbau", "Tee aus Bio-Anbau"),
    ],
)
def test_fix_case(raw, expected):
    assert rules.fix_case(raw) == expected


def test_clean_offer_texts_drops_empty_fields_and_duplicate_notes_and_keeps_brand_case():
    offer = {"id": "1", "name": "Tee.", "brand": "  ", "description": "\n", "notes": ["Je Stück.", "Je Stück", " "]}
    assert rules.clean_offer_texts(offer) == {"id": "1", "name": "Tee", "notes": ["Je Stück"]}
    assert rules.clean_offer_texts({"name": "NUTELLA", "brand": "TUBORG"}) == {"name": "Nutella", "brand": "TUBORG"}


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


def test_prompts_exist_for_every_locale():
    for locale in normalize.LOCALES.values():
        assert "fixes" in locale.prompt
        assert "wahl" in locale.judge_prompt


# --- Prüfung ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "original, candidate, ok",
    [
        ("Gyrossuppe oder Biftekitopf", "Gyrosuppe oder Biftekitopf", True),  # ein Buchstabe weniger
        ("Sprühshane mit Sahne", "Sprühsahne mit Sahne", True),  # Buchstabendreher
        ("Kartofeln, frisch", "Kartoffeln, frisch", True),
        ("NUTELLA", "Nutella", True),
        ("je 400 g", "Je 400 g", True),
        ("Frische Milch.", "Frische Milch", True),  # Schlusspunkt
        ("Bio-Milch 3,5 % Fett", "Bio-Milch 3,8 % Fett", False),  # Zahl verändert
        ("Tee", "Tee\nGrün", False),
        ("Tee", "", False),
        ("Back-Hirtenkäse", "Back-Hirtnägelkäse", False),  # erfundenes Wort (mehr als eine Änderung)
        ("Schoko Kugeln Vollmilch", "Schoko-Kugeln-Vollmilch", False),  # Wörter zusammengezogen
        ("Versch. Sorten. Tiefgefroren. Je 460 ml", "Versch. Sorten Tiefgefroren Je 460 ml", False),  # innere Punkte
        ("Schokolade Alpenmilch", "Schokolade", False),
        ("Schokolade", "Schokolade Alpenmilch", False),
        ("Anno »1688«", "Anno 1688", False),
        ("Weiße Bohnen", "Weißer Bohnen", False),  # Beugung
        ("Haltbare Milch", "Haltbar Milch", False),
        ("Mini-Bifteki", "Mini-Bifteke", False),
        ("Müllermilch ZERO", "Müller-Milch ZERO", False),
        ("2-teilig, je Set", "2-Teilig, je Set", False),
        ("Katze Hund", "Katze Mund", False),  # kurzes Wort: kein Tippfehler-Vorschlag
    ],
)
def test_validate(original, candidate, ok):
    assert validate(original, candidate) is ok


# --- Ablauf ------------------------------------------------------------------------------------------

OFFERS = [
    {"id": "1", "name": "Gekochte Kartofeln", "description": "Je 1 kg", "notes": ["Je Stück."], "brand": "Weihenstephan"},
    {"id": "2", "name": "Gekochte Bohnen", "price": 1.0},
    {"id": "3", "name": "Tee", "price": 2.0},
]
FIX = {"Kartofeln": "Kartoffeln"}


def test_rules_only_without_llm():
    out = Normalizer().offers([{"id": "1", "name": "NUTELLA", "description": "Je 1 kg.", "notes": ["Je Stück."]}])
    assert out == [{"id": "1", "name": "Nutella", "description": "Je 1 kg", "notes": ["Je Stück"]}]


def test_model_gets_only_numbered_texts_with_unchecked_words_and_fix_is_applied():
    llm = FakeLLM(FIX)
    out = Normalizer(llm=llm).offers(OFFERS)
    assert out[0]["name"] == "Gekochte Kartoffeln"
    assert OFFERS[0]["name"] == "Gekochte Kartofeln"  # Eingabe unverändert
    asked = [t for call in llm.calls for t in call]
    assert "Tee" not in asked and "Je 1 kg" not in asked  # keine prüfbaren Wörter
    assert out[2]["name"] == "Tee"


def test_checked_words_are_remembered_across_texts_and_runs(tmp_path):
    cache = tmp_path / "c.json"
    first = FakeLLM(FIX)
    Normalizer(llm=first, cache_path=cache).offers(OFFERS)
    assert first.calls
    again = FakeLLM(FIX)
    Normalizer(llm=again, cache_path=cache).offers(OFFERS)
    assert again.calls == []  # Texte stehen im Cache
    other = FakeLLM(FIX)  # anderer Text, aber nur bekannte Wörter
    Normalizer(llm=other, cache_path=cache).offers([{"id": "9", "name": "Gekochte Bohnen frisch", "price": 1.0}])
    assert [t for call in other.calls for t in call] == ["Gekochte Bohnen frisch"]  # "frisch" (6) ist neu
    third = FakeLLM(FIX)
    Normalizer(llm=third, cache_path=cache).offers([{"id": "10", "name": "Bohnen gekochte", "price": 1.0}])
    assert third.calls == []  # alle Wörter schon geprüft


def test_batches_of_at_most_batch_size():
    offers = [{"id": str(i), "name": f"Schokolade{'x' * i}", "price": 1.0} for i in range(BATCH_SIZE + 4)]
    llm = FakeLLM()
    Normalizer(llm=llm).offers(offers)
    assert [len(c) for c in llm.calls] == [BATCH_SIZE, 4]


def test_words_joined_by_slash_or_hyphen_are_checked_and_fixed():
    offers = [{"id": "1", "name": "Deutshcland/Italien, Klasse I", "price": 1.0}, {"id": "2", "name": "Back-Kartofeln", "price": 1.0}]
    llm = FakeLLM({"Deutshcland": "Deutschland", "Kartofeln": "Kartoffeln"})
    out = Normalizer(llm=llm).offers(offers)
    assert [o["name"] for o in out] == ["Deutschland/Italien, Klasse I", "Back-Kartoffeln"]


def test_fix_only_replaces_whole_words():
    offers = [{"id": "1", "name": "Kartofeln und Kartofelnsalat", "price": 1.0}]
    out = Normalizer(llm=FakeLLM({"Kartofeln": "Kartoffeln"})).offers(offers)
    assert out[0]["name"] == "Kartoffeln und Kartofelnsalat"


def test_unplausible_fix_is_dropped_without_judge():
    llm = FakeLLM({"Kartofeln": "Pommesfritten"})
    out = Normalizer(llm=llm).offers(OFFERS)
    assert out[0]["name"] == "Gekochte Kartofeln"


# --- Zweitmeinung (Thinking) bei abgelehnten Korrekturen ---------------------------------------------

JOFFERS = [
    {"id": "1", "name": "Mozarela mit Tomaten", "description": "Je 200 g", "notes": ["Je Packung"], "price": 1.0},
    {"id": "2", "name": "Tee", "price": 2.0},
]
TWO_EDITS = {"Mozarela": "Mozzarella"}  # zwei Änderungen: validate() lehnt ab, Zweitmeinung entscheidet
CHANGE = "Mozzarella mit Tomaten"
ORIGINAL = "Mozarela mit Tomaten"


def takes_change(payload):
    return "a" if payload["a"] == CHANGE else "b"


def keeps_original(payload):
    return "a" if payload["a"] == ORIGINAL else "b"


def test_rejected_fix_goes_to_judge_with_the_whole_offer():
    llm = FakeLLM(TWO_EDITS, choose=takes_change)
    out = Normalizer(llm=llm, judge_budget=60).offers(JOFFERS)
    assert out[0]["name"] == CHANGE
    assert len(llm.judged) == 1
    payload = llm.judged[0]
    assert payload["feld"] == "name"
    assert payload["angebot"]["notes"] == ["Je Packung"] and payload["angebot"]["description"] == "Je 200 g"
    assert {payload["a"], payload["b"]} == {ORIGINAL, CHANGE}


def test_judge_can_keep_the_original():
    llm = FakeLLM(TWO_EDITS, choose=keeps_original)
    assert Normalizer(llm=llm, judge_budget=60).offers(JOFFERS)[0]["name"] == ORIGINAL


def test_judge_without_usable_answer_keeps_the_original():
    llm = FakeLLM(TWO_EDITS, choose=lambda payload: None)
    assert Normalizer(llm=llm, judge_budget=60).offers(JOFFERS)[0]["name"] == ORIGINAL


def test_judge_order_is_stable_per_text():
    first, second = FakeLLM(TWO_EDITS, choose=takes_change), FakeLLM(TWO_EDITS, choose=takes_change)
    Normalizer(llm=first, judge_budget=60).offers(JOFFERS)
    Normalizer(llm=second, judge_budget=60).offers(JOFFERS)
    assert (first.judged[0]["a"], first.judged[0]["b"]) == (second.judged[0]["a"], second.judged[0]["b"])


def test_changed_digits_never_reach_the_judge():
    llm = FakeLLM({"Mozarela": "Mozar3la"}, choose=takes_change)
    out = Normalizer(llm=llm, judge_budget=60).offers(JOFFERS)
    assert llm.judged == [] and out[0]["name"] == ORIGINAL


def test_no_judge_budget_means_no_second_opinion():
    llm = FakeLLM(TWO_EDITS, choose=takes_change)
    out = Normalizer(llm=llm).offers(JOFFERS)
    assert llm.judged == [] and out[0]["name"] == ORIGINAL


def test_judgement_is_cached_and_not_asked_again(tmp_path):
    cache = tmp_path / "cache.json"
    Normalizer(llm=FakeLLM(TWO_EDITS, choose=takes_change), cache_path=cache, judge_budget=60).offers(JOFFERS)
    again = FakeLLM(TWO_EDITS, choose=takes_change)
    out = Normalizer(llm=again, cache_path=cache, judge_budget=60).offers(JOFFERS)
    assert again.calls == [] and again.judged == [] and out[0]["name"] == CHANGE


def test_exhausted_budget_defers_to_next_run(tmp_path):
    cache, logs = tmp_path / "cache.json", []
    first = FakeLLM(TWO_EDITS, choose=takes_change)
    normalizer = Normalizer(llm=first, cache_path=cache, judge_budget=0.001, log=logs.append)
    normalizer._judge_spent = 1  # Budget schon aufgebraucht
    out = normalizer.offers(JOFFERS)
    assert first.judged == [] and out[0]["name"] == ORIGINAL  # vorerst Original
    assert normalizer.stats["pending"] == 1 and any("verschoben" in m for m in logs)

    later = FakeLLM(TWO_EDITS, choose=takes_change)
    out = Normalizer(llm=later, cache_path=cache, judge_budget=60).offers(JOFFERS)
    assert later.calls == []  # Erstdurchlauf nicht wiederholt
    assert len(later.judged) == 1 and out[0]["name"] == CHANGE


def test_model_outage_degrades_to_rules_and_logs():
    logs = []
    out = Normalizer(llm=FakeLLM(fail=True), log=logs.append).offers(OFFERS)
    assert out[0]["name"] == "Gekochte Kartofeln" and logs[0].startswith("Warnung")


def test_judge_outage_keeps_original_and_logs():
    logs = []
    llm = FakeLLM(TWO_EDITS, choose=takes_change)
    llm.judge = lambda system, payload: (_ for _ in ()).throw(OllamaError("aus"))
    out = Normalizer(llm=llm, judge_budget=60, log=logs.append).offers(JOFFERS)
    assert out[0]["name"] == ORIGINAL and any(m.startswith("Warnung") for m in logs)


# --- Client / Einbindung --------------------------------------------------------------------------------


def test_ollama_typos_sends_numbered_texts_and_drops_malformed_fixes(monkeypatch):
    sent = {}

    def fake_post(self, path, payload):
        sent.update(payload)
        fixes = [
            {"id": 1, "wort": "a", "korrekt": "b"},
            {"id": 9, "wort": "x", "korrekt": "y"},  # id außerhalb
            {"id": 2, "wort": "x"},  # unvollständig
            "kaputt",
        ]
        return {"message": {"content": json.dumps({"fixes": fixes})}}

    monkeypatch.setattr(Ollama, "_post", fake_post)
    assert Ollama().typos("prompt", ["eins", "zwei"]) == [{"id": 1, "wort": "a", "korrekt": "b"}]
    assert sent["messages"][1]["content"] == "1: eins\n2: zwei"
    assert sent["think"] is False and sent["options"]["num_ctx"] == 2048


def test_from_args_without_reachable_ollama_warns_and_uses_rules(tmp_path, capsys):
    parser = argparse.ArgumentParser()
    normalize.add_arguments(parser)
    args = parser.parse_args(["--ollama-url", "http://127.0.0.1:9", "--cache", str(tmp_path / "c.json")])
    normalizer = normalize.from_args(args)
    assert normalizer.llm is None
    assert "Warnung" in capsys.readouterr().err


def test_site_build_with_transform_stays_schema_valid(tmp_path, fake_fetch):
    llm = FakeLLM()
    site.build_site(tmp_path, date(2026, 9, 29), fetch=fake_fetch, transform=Normalizer(llm=llm).offers)
    offers = json.loads((tmp_path / "all.json").read_text(encoding="utf-8"))
    assert offers and check.check_offers(offers) == []
    assert llm.calls
    assert all("\n" not in o.get("description", "") for o in offers)
