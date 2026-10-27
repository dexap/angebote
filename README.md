# angebote

Wochenangebote von [kaufda.de](https://www.kaufda.de) als JSON – direkt aus den JSON-Antworten der Seite, ohne PDF/OCR. Nur Python-Standardbibliothek.

- **Lidl**: nur Lebensmittel & Getränke.
- **Penny**: alle Kategorien, Sonderpreis = App-Preis ([kaufda](https://www.kaufda.de/Geschaefte/Penny-Markt)).
- **REWE**: alle Kategorien (Lebensmittel, Drogerie, Haushalt, …), nur *nationale* Angebote – kaufda führt je Markt einen Prospekt „Dein Markt“, übernommen wird, was in allen Markt-Prospekten steht. (rewe.de selbst ist per Bot-Schutz gesperrt und wird nicht gescrapt.)

Als Claude-Code-Skill: [`.claude/skills/lidl-angebote/SKILL.md`](.claude/skills/lidl-angebote/SKILL.md)

## Nutzung

```bash
python3 -m lidl_angebote                 # -> data/lidl_<Jahr>-KW<Woche>.json
python3 -m lidl_angebote --retailer rewe # -> data/rewe_<Jahr>-KW<Woche>.json
python3 -m lidl_angebote --help
```

Optionen: `--retailer lidl|rewe|penny`, `--date YYYY-MM-DD`, `--next` (Woche danach), `--output PATH` (`-` = stdout), `--no-drinks`, `--include-long-running`.

## JSON-API

Der Workflow `.github/workflows/pages.yml` baut täglich (und bei jedem Push auf `main`) eine statische API und veröffentlicht sie auf GitHub Pages. Tests laufen auf GitHub, Scrapen und Normalisieren auf dem Homeserver (self-hosted Runner, siehe [Normalisierung](#normalisierung)), der Deploy wieder auf GitHub. Inhalt ist jeweils nur die Liste der Angebote, ohne Prospekt `[]`. Alle Händler liefern dasselbe Schema – siehe [SCHEMA.md](SCHEMA.md).

| URL | Inhalt |
|---|---|
| `https://dexap.github.io/angebote/lidl.json` | Lidl, aktuelle Woche (`lidl/` = dasselbe als `index.html`) |
| `…/lidl/next.json` | Lidl, nächste Woche |
| `…/rewe.json`, `…/rewe/next.json` | REWE (national), aktuelle / nächste Woche |
| `…/penny.json`, `…/penny/next.json` | Penny, aktuelle / nächste Woche |
| `…/all.json`, `…/all/next.json` | alle Händler zusammen (Feld `retailer` unterscheidet) |

Einmalig nötig: *Settings → Pages → Build and deployment → Source: GitHub Actions*.

Lokal bauen: `python3 -m lidl_angebote.site --out _site`

Neue Händler: siehe [SCHEMA.md](SCHEMA.md) (Abschnitt „Neuer Händler“).

### Normalisierung

Vor dem Veröffentlichen werden die Texte (`name`, `description`, `notes`, `brand`) bereinigt. Zahlen, Preise und Daten fasst nur der Regel-Teil an.

1. **Regeln** (`normalize/rules.py`, ohne KI): `\n`/Escapes, Leerzeichen, Satzpunkte am Ende (Abkürzungen wie „Stk.“ bleiben), `0.25` → `0,25`, `500g` → `500 g`, `0,99€` → `0,99 €`, Versalien-Wörter ab 5 Buchstaben (`NUTELLA` → `Nutella`, nicht bei `brand`), Textanfang groß.
2. **Tippfehler-Prüfung** (`name`, `description`): [Ollama](https://ollama.com) mit `gemma4:e4b` auf dem Homeserver, Prompt `normalize/prompts/de.md`. Das Modell bekommt nur **nummerierte Texte mit noch ungeprüften Wörtern** (ab 6 Buchstaben) und meldet **nur Korrekturen** (`id`, `wort`, `korrekt`), keine neu geschriebenen Texte. Das spart Ausgabe-Token (auf der CPU der Engpass) und die Zuordnung übernimmt Python. 16 Texte je Anfrage, Kontext 2048, Thinking aus.
3. **Prüfung** (`validate()`): Eine Korrektur gilt nur bei genau einem geänderten Buchstaben (Einfügen, Löschen, Ersetzen, Vertauschen) in einem Wort ab 6 Buchstaben, mit gleichem Anfang und gleicher Endung (keine Beugung), ohne Änderung von Ziffern, Wortzahl, Bindestrichen oder inneren Satzzeichen. Wortendungen (Beugung) dürfen sich nie ändern, auch nicht durch die Zweitmeinung. Zusätzlich muss das korrigierte Wort schon in anderen Texten vorkommen (Vokabular, im Cache gemerkt), sonst entscheidet die Zweitmeinung. Reine Groß-/Kleinschreibungs-Vorschläge und Abkürzungen (`Versch.`) werden verworfen.
4. **Zweitmeinung** (nur wenn die Prüfung eine Korrektur ablehnt): dasselbe Modell mit aktiviertem Thinking bekommt das **vollständige Angebots-JSON** (Notizen, Einheiten, Marke, Kategorie, …) plus beide Fassungen (Reihenfolge stabil gemischt) und wählt die sinnvollere (`prompts/de.judge.md`). Ziffern und Umbrüche kann auch sie nicht ändern (`hard_ok`). Thinking ist langsam: je Lauf gibt es ein Zeitbudget (`--judge-minutes`, Standard 30; `--no-judge` schaltet es ab), Rest folgt im nächsten Lauf.
5. **Cache** (`~/.cache/angebote/normalize.json`, `ANGEBOTE_CACHE`): je Text und je Wort („schon geprüft“). Nur neue Texte mit unbekannten Wörtern gehen ans Modell.
6. **Ausfall**: Ist Ollama nicht erreichbar, läuft der Build nur mit Regeln und meldet `::warning::`.

**Sprachen:** `normalize/locales.py` (`Locale`: Dezimaltrenner, Währung, Datumsformat, Abkürzungen) und `normalize/prompts/<code>.md`. Eine neue Sprache braucht beides, dann `--lang <code>`.

```bash
python3 -m lidl_angebote.site --out _site --normalize   # wie im Workflow
python3 -m lidl_angebote.normalize all.json              # einzelne Datei, Ausgabe auf stdout
python3 -m lidl_angebote.normalize --help                # --no-llm, --model, --ollama-url, --cache, --lang
```

**Betrieb auf dem Homeserver**

- Ollama: `docker run -d --name ollama --restart unless-stopped -p 127.0.0.1:11434:11434 -v ollama:/root/.ollama ollama/ollama` und `docker exec ollama ollama pull gemma4:e4b`
- Runner: `~/actions-runner` (Label `homeserver`), User-Service `systemctl --user status github-runner`. Der Pages-Workflow läuft nur bei `schedule`, `push` und `workflow_dispatch`, nie bei Pull Requests, damit fremder Code nicht auf dem Server landet.

### Schema-Checkup

`python3 -m lidl_angebote.check` scrapt live und prüft jedes Angebot gegen die Schnittstelle (Typen, Preise > 0, ISO-Daten, eindeutige IDs, Kategorie-Gruppe, `unit_price`). `site.py` führt dieselbe Prüfung vor dem Schreiben aus – bei Fehlern wird nichts veröffentlicht.

## Tests

```bash
pip install pytest
python3 -m pytest                        # Unit-Tests mit Fixtures (offline)
LIVE=1 python3 -m pytest tests/test_live.py   # Live gegen kaufda.de
```

Entwicklung test-first: erst Test/Fixture anpassen, dann Code.
