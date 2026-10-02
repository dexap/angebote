# angebote

Lidl-Wochenangebote (nur Lebensmittel & Getränke) von [kaufda.de](https://www.kaufda.de/Geschaefte/Lidl) als JSON – direkt aus den JSON-Antworten der Seite, ohne PDF/OCR. Nur Python-Standardbibliothek.

Als Claude-Code-Skill: [`.claude/skills/lidl-angebote/SKILL.md`](.claude/skills/lidl-angebote/SKILL.md)

## Nutzung

```bash
python3 -m lidl_angebote                 # -> data/lidl_<Jahr>-KW<Woche>.json
python3 -m lidl_angebote --help
```

Optionen: `--date YYYY-MM-DD`, `--output PATH` (`-` = stdout), `--no-drinks`, `--include-long-running`.

## Tests

```bash
pip install pytest
python3 -m pytest                        # Unit-Tests mit Fixtures (offline)
LIVE=1 python3 -m pytest tests/test_live.py   # Live gegen kaufda.de
```

Entwicklung test-first: erst Test/Fixture anpassen, dann Code.
