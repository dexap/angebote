# angebote

Wochenangebote von [kaufda.de](https://www.kaufda.de) als JSON – direkt aus den JSON-Antworten der Seite, ohne PDF/OCR. Nur Python-Standardbibliothek.

- **Lidl**: nur Lebensmittel & Getränke.
- **REWE**: alle Kategorien (Lebensmittel, Drogerie, Haushalt, …), nur *nationale* Angebote – kaufda führt je Markt einen Prospekt „Dein Markt“, übernommen wird, was in allen Markt-Prospekten steht. (rewe.de selbst ist per Bot-Schutz gesperrt und wird nicht gescrapt.)

Als Claude-Code-Skill: [`.claude/skills/lidl-angebote/SKILL.md`](.claude/skills/lidl-angebote/SKILL.md)

## Nutzung

```bash
python3 -m lidl_angebote                 # -> data/lidl_<Jahr>-KW<Woche>.json
python3 -m lidl_angebote --retailer rewe # -> data/rewe_<Jahr>-KW<Woche>.json
python3 -m lidl_angebote --help
```

Optionen: `--retailer lidl|rewe`, `--date YYYY-MM-DD`, `--next` (Woche danach), `--output PATH` (`-` = stdout), `--no-drinks`, `--include-long-running`.

## JSON-API

Der Workflow `.github/workflows/pages.yml` baut täglich (und bei jedem Push auf `main`) eine statische API und veröffentlicht sie auf GitHub Pages. Inhalt ist jeweils nur die Liste der Angebote, ohne Prospekt `[]`. Alle Händler liefern dasselbe Schema – siehe [SCHEMA.md](SCHEMA.md).

| URL | Inhalt |
|---|---|
| `https://dexap.github.io/angebote/lidl.json` | Lidl, aktuelle Woche (`lidl/` = dasselbe als `index.html`) |
| `…/lidl/next.json` | Lidl, nächste Woche |
| `…/rewe.json`, `…/rewe/next.json` | REWE (national), aktuelle / nächste Woche |
| `…/all.json`, `…/all/next.json` | alle Händler zusammen (Feld `retailer` unterscheidet) |

Einmalig nötig: *Settings → Pages → Build and deployment → Source: GitHub Actions*.

Lokal bauen: `python3 -m lidl_angebote.site --out _site`

Neue Händler: siehe [SCHEMA.md](SCHEMA.md) (Abschnitt „Neuer Händler“).

### Schema-Checkup

`python3 -m lidl_angebote.check` scrapt live und prüft jedes Angebot gegen die Schnittstelle (Typen, Preise > 0, ISO-Daten, eindeutige IDs, Kategorie-Gruppe, `unit_price`). `site.py` führt dieselbe Prüfung vor dem Schreiben aus – bei Fehlern wird nichts veröffentlicht.

## Tests

```bash
pip install pytest
python3 -m pytest                        # Unit-Tests mit Fixtures (offline)
LIVE=1 python3 -m pytest tests/test_live.py   # Live gegen kaufda.de
```

Entwicklung test-first: erst Test/Fixture anpassen, dann Code.
