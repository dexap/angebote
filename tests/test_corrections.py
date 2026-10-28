import json

import pytest

from lidl_angebote.normalize import wordbook
from lidl_angebote.normalize.corrections import Corrections


@pytest.fixture
def book(tmp_path):
    return Corrections(tmp_path / "data" / "corrections.de.json")


def test_applies_whole_words_only_and_keeps_start_case(book):
    book.learn("Standartpackung", "Standardpackung")
    assert book.apply("Standartpackung: 500 ml") == "Standardpackung: 500 ml"
    assert book.apply("je standartpackung 5 g") == "je standardpackung 5 g"  # Mitte bleibt klein
    assert book.apply("Standartpackungen und Standartpackungsgröße") == "Standartpackungen und Standartpackungsgröße"


def test_handles_hyphen_and_slash_words_and_phrases(book):
    book.learn("Gratis-Glas", "Gratisglas")
    book.learn("Deutshcland", "Deutschland")
    book.learn("Pingui/Milchschnitte", "Pinguin/Milchschnitte")
    book.learn("mit zart schmelzend", "mit zartem schmelzend")
    assert book.apply("Mit Gratis-Glas Je 0,5 l") == "Mit Gratisglas Je 0,5 l"
    assert book.apply("Deutshcland/Italien, Klasse I") == "Deutschland/Italien, Klasse I"
    assert book.apply("Pingui/Milchschnitte") == "Pinguin/Milchschnitte"
    assert book.apply("Käse mit zart schmelzend") == "Käse mit zartem schmelzend"


def test_longest_key_wins_over_part_of_it(book):
    book.learn("Gratis", "Kostenlos")
    book.learn("Gratis-Glas", "Gratisglas")
    assert book.apply("Gratis-Glas") == "Gratisglas"
    assert book.apply("Gratis Tasche") == "Kostenlos Tasche"


def test_learning_is_persistent_and_never_overwrites(tmp_path):
    path, logs = tmp_path / "c.json", []
    assert Corrections(path).learn("Kartofeln", "Kartoffeln") is True
    again = Corrections(path, log=logs.append)
    assert again.apply("Kartofeln") == "Kartoffeln" and len(again) == 1
    assert again.learn("kartofeln", "Kartoffeln") is False  # gleicher Eintrag
    assert again.learn("Kartofeln", "Erdäpfel") is False and any("schon" in m for m in logs)  # Konflikt
    assert again.apply("Kartofeln") == "Kartoffeln"
    assert json.loads(path.read_text(encoding="utf-8")) == {"kartofeln": "Kartoffeln"}


@pytest.mark.parametrize("wrong, right", [("", "x"), ("x", ""), ("NUTELLA", "Nutella"), ("Tee", "tee")])
def test_ignores_empty_and_case_only_entries(book, wrong, right):
    assert book.learn(wrong, right) is False and len(book) == 0


def test_unreadable_file_is_ignored_and_never_overwritten(tmp_path):
    path, logs = tmp_path / "c.json", []
    path.write_text('{"kartofeln": "Kartoffeln",', encoding="utf-8")  # kaputt von Hand bearbeitet
    book = Corrections(path, log=logs.append)
    assert book.apply("Kartofeln") == "Kartofeln" and logs and logs[0].startswith("Warnung")
    assert book.learn("Tomatn", "Tomaten") is False
    assert path.read_text(encoding="utf-8") == '{"kartofeln": "Kartoffeln",'


def test_file_with_wrong_types_is_unreadable(tmp_path):
    path = tmp_path / "c.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    assert Corrections(path, log=lambda m: None)._readonly


def test_forget_and_missing_file(book, tmp_path):
    assert len(Corrections(tmp_path / "gibt-es-nicht.json")) == 0
    book.learn("Kartofeln", "Kartoffeln")
    assert book.forget("kartofeln") is True and book.forget("kartofeln") is False
    assert book.apply("Kartofeln") == "Kartofeln"


def test_command_line_add_list_remove(tmp_path, capsys):
    file = str(tmp_path / "c.json")
    assert wordbook.main(["--file", file, "add", "Kartofeln", "Kartoffeln"]) == 0
    assert wordbook.main(["--file", file, "list"]) == 0
    out = capsys.readouterr()
    assert "hinzugefügt" in out.out and "kartofeln -> Kartoffeln" in out.out and "1 Einträge" in out.err
    assert wordbook.main(["--file", file, "remove", "Kartofeln"]) == 0
    assert "gelöscht" in capsys.readouterr().out
