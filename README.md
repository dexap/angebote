# angebote

Lidl-Wochenangebote (nur Lebensmittel & Getränke) von [kaufda.de](https://www.kaufda.de/Geschaefte/Lidl) als JSON – direkt aus den JSON-Antworten der Seite, ohne PDF/OCR. Nur Python-Standardbibliothek.

Als Claude-Code-Skill: [`.claude/skills/lidl-angebote/SKILL.md`](.claude/skills/lidl-angebote/SKILL.md)

## Nutzung

```bash
python3 -m lidl_angebote                 # -> data/lidl_<Jahr>-KW<Woche>.json
python3 -m lidl_angebote --help
```

Optionen: `--date YYYY-MM-DD`, `--next` (Woche danach), `--output PATH` (`-` = stdout), `--no-drinks`, `--include-long-running`.

## JSON-API (GitHub Pages)

Der Workflow `.github/workflows/pages.yml` baut täglich (und bei jedem Push auf `main`) eine statische API und veröffentlicht sie auf GitHub Pages. Inhalt ist jeweils nur die Liste der Angebote, ohne Prospekt `[]`.

| URL | Inhalt |
|---|---|
| `https://dexap.github.io/angebote/lidl.json` | aktuelle Woche (`Content-Type: application/json`) |
| `https://dexap.github.io/angebote/lidl/` | dasselbe, als `index.html` |
| `https://dexap.github.io/angebote/lidl/next.json` | nächste Woche |
| `https://dexap.github.io/angebote/lidl/next/` | dasselbe, als `index.html` |

Einmalig nötig: *Settings → Pages → Build and deployment → Source: GitHub Actions*.

Lokal bauen: `python3 -m lidl_angebote.site --out _site`

## Tests

```bash
pip install pytest
python3 -m pytest                        # Unit-Tests mit Fixtures (offline)
LIVE=1 python3 -m pytest tests/test_live.py   # Live gegen kaufda.de
```

Entwicklung test-first: erst Test/Fixture anpassen, dann Code.
