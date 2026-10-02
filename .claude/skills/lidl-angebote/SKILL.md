---
name: lidl-angebote
description: Holt die aktuellen Lidl-Angebote der Woche (nur Lebensmittel und Getränke, die im Wochenprospekt preisreduziert sind) von kaufda.de und speichert sie als JSON. Nutze diesen Skill, wenn nach Lidl-Angeboten, dem aktuellen Lidl-Prospekt, Lidl-Preisen diese Woche oder einer Angebotsliste für den Einkauf gefragt wird.
---

# Lidl-Wochenangebote als JSON

Holt die Angebote **direkt aus den JSON-Antworten von kaufda.de** – kein PDF, kein OCR.

## Ausführen

Im Repository-Root:

```bash
python3 -m lidl_angebote                      # aktuelle Woche -> data/lidl_<Jahr>-KW<Woche>.json
python3 -m lidl_angebote --date 2026-10-05    # Woche zu einem Stichtag (z. B. nächste Woche)
python3 -m lidl_angebote --no-drinks          # ohne Getränke
python3 -m lidl_angebote --include-long-running  # auch Langläufer-Prospekte (> 14 Tage, z. B. "Preisführer")
python3 -m lidl_angebote -o -                 # JSON auf stdout
```

Exit-Code 1 = kein passender Wochenprospekt gefunden (Meldung auf stderr).

Danach dem Nutzer kurz berichten: Anzahl Angebote, Prospekt + Gültigkeit, Pfad der JSON-Datei. Bei Fragen ("Was gibt's günstig an Käse?") die JSON-Datei auswerten statt neu abzurufen.

## Was passiert

1. `GET https://www.kaufda.de/Geschaefte/Lidl` → `__NEXT_DATA__` (Next.js) enthält alle Lidl-Prospekte (`pageInformation.brochures.*`) und den Standort (`pageInformation.location`).
2. Auswahl: Prospekte, deren Gültigkeit die ISO-Woche (Mo–So, Europe/Berlin) des Stichtags überlappt und ≤ 14 Tage läuft.
3. `GET https://content-viewer-be.kaufda.de/v1/brochures/<contentId>/pages?partner=kaufda_web&lat=..&lng=..` → alle Seiten mit `offers[].content` (Produkte, Kategorien, `deals` mit Preisen).
4. Filter: Produkt-Kategoriepfad beginnt mit `DE-104` („Lebensmittel und Getränke“), Preis vorhanden, Angebot in der Woche gültig. Mehrprodukt-Angebote werden pro Produkt aufgeteilt.

## Ausgabe (Auszug)

```json
{
  "retailer": "Lidl",
  "week": {"year": 2026, "number": 40, "start": "2026-09-28", "end": "2026-10-04"},
  "brochures": [{"id": "…", "title": "LIDL LOHNT SICH", "valid_from": "2026-09-28", "valid_until": "2026-10-02"}],
  "count": 240,
  "offers": [{
    "name": "Tafelschokolade Alpenmilch", "brand": "FIN CARRÉ", "description": "Je 100 g",
    "price": 0.39, "regular_price": 0.79, "uvp": null, "discount_percent": 51,
    "special_price": null, "special_price_condition": null,
    "base_price": "1 kg = 3.90", "conditions": [], "extras": [],
    "category": "Fairtrade", "category_path": ["Lebensmittel und Getränke", "…"], "is_drink": false,
    "valid_from": "2026-09-28", "valid_until": "2026-10-02", "page": 7, "image": "https://…"
  }]
}
```

Preisfelder aus `deals[].type`: `SALES_PRICE` → `price`, `REGULAR_PRICE` → `regular_price` (Streichpreis), `RECOMMENDED_RETAIL_PRICE` → `uvp`, `SPECIAL_PRICE` → `special_price` (meist „Mit Lidl Plus“), `OTHER` → `extras`.

## Wenn es bricht

- **403 / Netzwerkfehler**: `www.kaufda.de` und `content-viewer-be.kaufda.de` müssen erreichbar sein (Proxy, Pi-hole, Cloud-Netzwerk-Policy).
- **`Kein __NEXT_DATA__` / KeyError / 0 Angebote**: kaufda hat die Struktur geändert. Vorgehen **test-first**:
  1. Rohdaten neu holen und ansehen (HTML der Händlerseite, JSON der Viewer-API).
  2. Fixtures in `tests/fixtures/` aktualisieren bzw. einen neuen, fehlschlagenden Test schreiben.
  3. `lidl_angebote/kaufda.py` anpassen, bis `python3 -m pytest` grün ist; dann `LIVE=1 python3 -m pytest tests/test_live.py`.
