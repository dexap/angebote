# Angebots-Schnittstelle

Alle Händler (`lidl`, `rewe`, …) geben **dasselbe Schema** aus: `retailers/<händler>.py` übersetzt die Eigenheiten des Händlers, ausgegeben wird nur über `kaufda._record` und geprüft von `check.py` (`python3 -m lidl_angebote.check`; der Site-Build bricht bei Verstößen ab).

**Regel:** Optionale Felder fehlen, wenn es keinen Wert gibt – nie `null`, `""` oder `[]`. Pflichtfelder sind immer da.

## Pflichtfelder

| Feld | Typ | Bedeutung |
|---|---|---|
| `retailer` | string | `lidl`, `rewe`, … |
| `id` | string | eindeutig; bei Mehrprodukt-Anzeigen `<uuid>#<n>` |
| `name` | string | Produktname |
| `price` | number | Angebotspreis in € (> 0) |
| `is_drink` | bool | Getränk |
| `valid_from`, `valid_until` | `YYYY-MM-DD` | Gültigkeit |

## Optionale Felder

| Feld | Typ | Bedeutung |
|---|---|---|
| `brand`, `description` | string | Marke; Beschreibung/Packungsgröße |
| `regular_price` | number | Vergleichspreis: durchgestrichener Normalpreis, sonst die unverbindliche Preisempfehlung (UVP) |
| `discount_percent` | int | Rabatt gegenüber `regular_price` (nur mit diesem) |
| `special_price` | number | **Preis mit Kundenkarte/Bonus** (immer < `price`), siehe unten |
| `special_price_condition` | string | Bedingung dazu (immer zusammen mit `special_price`) |
| `unit_price` | `{amount, unit, quantity}` | Grundpreis, z. B. `{3.9, "kg", 1}` = 3,90 €/kg; fehlt, wenn der Text nicht eindeutig ist (Spannen, „ab …“) |
| `notes` | string[] | Preisbedingungen und Zusatzaktionen („3 für 2“, „Je Stück“, „Vereinsschein gratis“, „4 für 2,00 €“); das bloße „je“ entfällt |
| `category_group` | string | oberste Kategorie („Lebensmittel und Getränke“, „Drogerie und Haushalt“, …) |

## Sonderpreis je Händler (`special_price`)

- **Lidl:** „Mit Lidl Plus“-Preis. Ohne Bedingungstext: `"Sonderpreis"`. Mengenpreise („4 für 2 €“) sind kein Einzelpreis und landen in `notes`.
- **REWE:** „Bonus“ (Cashback in der REWE App) wird vom `price` abgezogen: `0,10 € Bonus` → `price − 0,10`; `10 % Bonus` → `price × 0,9`. Bedingung: `"REWE Bonus: 0,10 €"` / `"REWE Bonus: 10 %"`. Ist der Bonus größer als der Preis, bleibt er als Text in `notes`.

## Neuer Händler

1. `retailers/<key>.py` mit `Retailer(...)` und der Funktion `special_price(price, deals) -> (preis|None, bedingung|None, extras)`.
2. In `retailers/__init__.py` eintragen.
3. Tests in `tests/test_loyalty.py`/`test_retailers.py`, Fixtures unter `tests/fixtures/`.
4. `python3 -m lidl_angebote.check` muss „OK“ zeigen.
