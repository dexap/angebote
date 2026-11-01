"""Backend des NBA-Verletzungs-Reports: zieht täglich die Daten und baut die Seite.

Quellen (öffentliche ESPN-JSON-Endpunkte, nur Python-Standardbibliothek):
  - Teams:        site.api.espn.com/apis/site/v2/sports/basketball/nba/teams
  - Kader+Gehalt: …/teams/<id>/roster   (contract.salary, Saison 2027 = 2026-27)
  - Verletzungen: …/nba/injuries        (nur der *aktuelle* Stand, keine Historie)
  - Tabelle:      site.api.espn.com/apis/v2/sports/basketball/nba/standings
  - Meldungen:    …/nba/news

Weil ESPN keine Verletzungshistorie liefert, schreibt `update` sie selbst fort
(history.json): eine Kennzahlen-Zeile pro Tag und jeder Spieler, der seit Beginn
der Aufzeichnung einmal verletzt gemeldet war.

  python3 nba/build.py update --data-dir DIR    # Quellen abrufen -> DIR/data.json, DIR/history.json
  python3 nba/build.py site --data-dir DIR --out _site/nba   # Seite aus DIR bauen (offline)
"""

import argparse
import html
import json
import re
import shutil
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
STANDINGS = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings"
SEASON_YEAR = 2027  # ESPN zählt die Saison 2026-27 als 2027
SEASON = "2026-27"

# Abwesenheiten auf dem Injury Report, die keine Verletzung sind.
NON_INJURY = {"Rest", "Personal", "Illness", "Suspension", "Not Injury Related", "League Suspension"}

BODY_DE = {
    "Achilles": "Achillessehne", "Ankle": "Knöchel", "Back": "Rücken", "Calf": "Wade",
    "Foot": "Fuß", "Hamstring": "Oberschenkel (hinten)", "Heel": "Ferse", "Hip": "Hüfte",
    "Knee": "Knie", "Leg": "Bein", "Shoulder": "Schulter", "Wrist": "Handgelenk",
    "Hand": "Hand", "Finger": "Finger", "Groin": "Leiste", "Quadriceps": "Oberschenkel (vorn)",
    "Thigh": "Oberschenkel", "Toe": "Zeh", "Elbow": "Ellbogen", "Neck": "Nacken",
    "Head": "Kopf", "Concussion": "Gehirnerschütterung", "Abdomen": "Bauch", "Chest": "Brust",
    "Oblique": "Rumpfmuskulatur", "Shin": "Schienbein", "Achilles Tendon": "Achillessehne",
    "Rest": "Pause", "Personal": "Persönlich", "Illness": "Krankheit", "Unbekannt": "Unbekannt",
}

NEWS_RE = re.compile(r"injur|surger|\btorn\b|\btear\b|strain|sprain|fractur|broken|sidelined|concussion|"
                     r"\bout (at least|for|indefinitely|\d)|\bmiss(es|ing)? |\bsits?\b|re-?evaluat|\bMRI\b|"
                     r"week-to-week|day-to-day", re.I)


# --------------------------------------------------------------------------- Abruf

def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (nba-injury-board)"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** (i + 1))


def fetch_raw():
    """Alle Rohdaten von ESPN. Meldungen sind optional (Fehler -> leer)."""
    teams = [t["team"] for t in get(f"{API}/teams")["sports"][0]["leagues"][0]["teams"]]
    with ThreadPoolExecutor(8) as ex:
        rosters = list(ex.map(lambda t: get(f"{API}/teams/{t['id']}/roster"), teams))
    try:
        news = get(f"{API}/news?limit=60")
    except Exception as e:  # pragma: no cover - nur Netzfehler
        print(f"Warnung: Meldungen nicht abrufbar ({e})", file=sys.stderr)
        news = {"articles": []}
    return {"teams": teams, "rosters": rosters, "injuries": get(f"{API}/injuries"),
            "standings": get(STANDINGS), "news": news}


# --------------------------------------------------------------------------- Aufbereitung

def athlete_id(athlete):
    for link in athlete.get("links", []):
        m = re.search(r"/id/(\d+)", link.get("href", ""))
        if m:
            return m.group(1)
    return None


def _injuries(raw):
    out = {}
    for team in raw["injuries"].get("injuries", []):
        for x in team.get("injuries", []):
            det = x.get("details") or {}
            kind = det.get("type") or "Unbekannt"
            out[athlete_id(x["athlete"])] = {
                "status": x.get("status", ""),
                "type": kind,
                "type_de": BODY_DE.get(kind, kind),
                "side": det.get("side"),
                "return": det.get("returnDate"),
                "since": (x.get("date") or "")[:10],
                "note": x.get("shortComment", ""),
                "injury": kind not in NON_INJURY,
            }
    return out


def _records(raw):
    rec = {}
    for conf in raw["standings"].get("children", []):
        for e in conf["standings"]["entries"]:
            s = {st["name"]: st.get("value") for st in e["stats"]}
            rec[e["team"]["abbreviation"]] = {"w": int(s.get("wins") or 0), "l": int(s.get("losses") or 0),
                                              "conf": conf.get("abbreviation") or conf.get("name", "")}
    return rec


def _news(raw, limit=8):
    out = []
    for a in raw["news"].get("articles", []):
        head = a.get("headline") or ""
        if a.get("type") not in ("HeadlineNews", "Story") or not NEWS_RE.search(head):
            continue
        out.append({"headline": head, "description": a.get("description") or "",
                    "published": a.get("published", ""),
                    "url": ((a.get("links") or {}).get("web") or {}).get("href", "")})
    out.sort(key=lambda n: n["published"], reverse=True)
    return out[:limit]


def transform(raw, now):
    injuries = _injuries(raw)
    record = _records(raw)
    teams, players = [], []
    for t, roster in zip(raw["teams"], raw["rosters"]):
        abbr = t["abbreviation"]
        teams.append({
            "abbr": abbr, "name": t["displayName"], "short": t.get("shortDisplayName", t["displayName"]),
            "color": "#" + (t.get("color") or "333333"), "alt": "#" + (t.get("alternateColor") or "999999"),
            **record.get(abbr, {"w": 0, "l": 0, "conf": ""}),
        })
        for a in roster.get("athletes", []):
            c = a.get("contract") or {}
            salary = c.get("salary") if (c.get("season") or {}).get("year") == SEASON_YEAR else None
            players.append({
                "id": a["id"], "name": a["displayName"], "team": abbr,
                "pos": (a.get("position") or {}).get("abbreviation", ""),
                "age": a.get("age"), "salary": salary or None,
                "inj": injuries.pop(a["id"], None),
            })
    if injuries:
        print(f"Hinweis: {len(injuries)} Verletzte ohne Kaderzuordnung", file=sys.stderr)
    players.sort(key=lambda p: (-(p["salary"] or 0), p["name"]))
    return {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "injury_report_at": raw["injuries"].get("timestamp"),
        "season": SEASON,
        "teams": teams,
        "players": players,
        "news": _news(raw),
    }


def metrics(data):
    P = data["players"]
    paid = [p for p in P if p["salary"]]
    inj = [p for p in P if p["inj"] and p["inj"]["injury"]]
    games = sum(t["w"] + t["l"] for t in data["teams"]) / max(len(data["teams"]), 1)
    return {
        "players": len(P),
        "injured": len(inj),
        "out": sum(1 for p in inj if p["inj"]["status"] == "Out"),
        "injured_salary": sum(p["salary"] or 0 for p in inj),
        "payroll": sum(p["salary"] for p in paid),
        "top50": sum(1 for p in paid[:50] if p["inj"] and p["inj"]["injury"]),
        "stars": sum(1 for p in paid if p["salary"] >= 40e6 and p["inj"] and p["inj"]["injury"]),
        "games": round(games, 1),
    }


def update_history(history, data, day):
    """Tageskennzahlen + Verletzten-Register fortschreiben. `day` = ISO-Datum (UTC)."""
    history = history or {}
    days = [d for d in history.get("days", []) if d["date"] != day]
    days.append({"date": day, **metrics(data)})
    days.sort(key=lambda d: d["date"])
    reg = history.get("players", {})
    for p in data["players"]:
        j = p["inj"]
        if not (j and j["injury"]):
            continue
        e = reg.get(p["id"])
        first = min(day, j["since"] or day)
        if e is None:
            e = reg[p["id"]] = {"name": p["name"], "first": first, "types": []}
        e.update(name=p["name"], team=p["team"], salary=p["salary"], last=day,
                 first=min(e["first"], first))
        if j["type_de"] not in e["types"]:
            e["types"].append(j["type_de"])
    return {"season": data["season"], "since": days[0]["date"], "days": days, "players": reg}


def annotate(data, history):
    """Genesene Spieler (laut Register früher verletzt, heute nicht mehr) markieren."""
    reg = history.get("players", {})
    for p in data["players"]:
        e = reg.get(p["id"])
        if e and not (p["inj"] and p["inj"]["injury"]):
            p["was"] = {"first": e["first"], "last": e["last"], "types": e["types"]}
    data["tracking_since"] = history.get("since")
    data["ever_injured"] = len(reg)
    return data


# --------------------------------------------------------------------------- Seite

def _fmt_bn(v):
    return f"{v / 1e9:.2f}".replace(".", ",") + " Mrd. $"


def og_description(data):
    m = metrics(data)
    return (f"{m['injured']} verletzte Spieler, {_fmt_bn(m['injured_salary'])} Gehalt auf der Verletztenliste, "
            f"{m['top50']} der 50 Topverdiener fehlen – nach Ø {str(m['games']).replace('.', ',')} Spielen pro Team. "
            f"Alle 30 Teams, alle Gehälter, täglich aktualisiert.")


def build_site(data_dir, out_dir):
    data_dir, out = Path(data_dir), Path(out_dir)
    data = json.loads((data_dir / "data.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    page = (HERE / "index.html").read_text(encoding="utf-8")
    page = page.replace("__OG_DESCRIPTION__", html.escape(og_description(data), quote=True))
    (out / "index.html").write_text(page, encoding="utf-8")
    shutil.copy(HERE / "og.png", out / "og.png")
    for name in ("data.json", "history.json"):
        if (data_dir / name).exists():
            shutil.copy(data_dir / name, out / name)


def update(data_dir, raw=None, now=None):
    data_dir = Path(data_dir)
    now = now or datetime.now(timezone.utc)
    data = transform(raw or fetch_raw(), now)
    if len(data["teams"]) != 30 or len(data["players"]) < 300:
        raise SystemExit(f"Unplausible Daten ({len(data['teams'])} Teams, {len(data['players'])} Spieler) – abgebrochen")
    hist_path = data_dir / "history.json"
    history = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else {}
    history = update_history(history, data, now.strftime("%Y-%m-%d"))
    annotate(data, history)
    data_dir.mkdir(parents=True, exist_ok=True)
    dump = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":"))
    (data_dir / "data.json").write_text(dump(data), encoding="utf-8")
    hist_path.write_text(dump(history), encoding="utf-8")
    m = metrics(data)
    print(f"{m['players']} Spieler, {m['injured']} verletzt, {len(history['days'])} Tage Verlauf, "
          f"{len(history['players'])} Spieler im Register -> {data_dir}")
    return data, history


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("update", help="Quellen abrufen, data.json + history.json fortschreiben")
    u.add_argument("--data-dir", default=str(HERE))
    s = sub.add_parser("site", help="Seite aus vorhandenen Daten bauen (offline)")
    s.add_argument("--data-dir", default=str(HERE))
    s.add_argument("--out", default="_site/nba")
    args = p.parse_args(argv)
    if args.cmd == "update":
        update(args.data_dir)
    else:
        build_site(args.data_dir, args.out)


if __name__ == "__main__":
    main()
