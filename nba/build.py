"""Baut nba/data.json: alle NBA-Kader mit Gehalt 2026-27 und aktuellem Verletzungsstatus.

Quellen (öffentliche ESPN-JSON-Endpunkte, nur Python-Standardbibliothek):
  - Teams:        site.api.espn.com/apis/site/v2/sports/basketball/nba/teams
  - Kader+Gehalt: …/teams/<id>/roster   (Feld contract.salary, Saison 2027 = 2026-27)
  - Verletzungen: …/nba/injuries
  - Tabelle:      site.api.espn.com/apis/v2/sports/basketball/nba/standings

Aufruf: python3 nba/build.py [--out nba/data.json]
"""

import argparse
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

API = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
STANDINGS = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings"
SEASON_YEAR = 2027  # ESPN zählt die Saison 2026-27 als 2027

# Abwesenheiten auf dem Injury Report, die keine Verletzung sind.
NON_INJURY = {"Rest", "Personal", "Illness", "Suspension", "Not Injury Related", "League Suspension"}

BODY_DE = {
    "Achilles": "Achillessehne", "Ankle": "Knöchel", "Back": "Rücken", "Calf": "Wade",
    "Foot": "Fuß", "Hamstring": "Oberschenkel (hinten)", "Heel": "Ferse", "Hip": "Hüfte",
    "Knee": "Knie", "Leg": "Bein", "Shoulder": "Schulter", "Wrist": "Handgelenk",
    "Hand": "Hand", "Finger": "Finger", "Groin": "Leiste", "Quadriceps": "Oberschenkel (vorn)",
    "Thigh": "Oberschenkel", "Toe": "Zeh", "Elbow": "Ellbogen", "Neck": "Nacken",
    "Head": "Kopf", "Concussion": "Gehirnerschütterung", "Abdomen": "Bauch", "Chest": "Brust",
    "Rest": "Pause", "Personal": "Persönlich", "Illness": "Krankheit",
}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (nba-injury-board)"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def athlete_id(athlete):
    for link in athlete.get("links", []):
        m = re.search(r"/id/(\d+)", link.get("href", ""))
        if m:
            return m.group(1)
    return None


def build():
    teams = [t["team"] for t in get(f"{API}/teams")["sports"][0]["leagues"][0]["teams"]]
    with ThreadPoolExecutor(8) as ex:
        rosters = list(ex.map(lambda t: get(f"{API}/teams/{t['id']}/roster"), teams))
    injuries_raw = get(f"{API}/injuries")
    standings = get(STANDINGS)

    injuries = {}
    for team in injuries_raw["injuries"]:
        for x in team["injuries"]:
            det = x.get("details", {})
            kind = det.get("type") or "Unbekannt"
            injuries[athlete_id(x["athlete"])] = {
                "status": x["status"],
                "type": kind,
                "type_de": BODY_DE.get(kind, kind),
                "side": det.get("side"),
                "return": det.get("returnDate"),
                "since": x["date"][:10],
                "note": x.get("shortComment", ""),
                "injury": kind not in NON_INJURY,
            }

    record = {}
    for conf in standings["children"]:
        for e in conf["standings"]["entries"]:
            s = {st["name"]: st.get("value") for st in e["stats"]}
            record[e["team"]["abbreviation"]] = {"w": int(s.get("wins") or 0), "l": int(s.get("losses") or 0),
                                                 "conf": conf["abbreviation"] if "abbreviation" in conf else conf["name"]}

    out_teams, players = [], []
    for t, roster in zip(teams, rosters):
        abbr = t["abbreviation"]
        out_teams.append({
            "abbr": abbr, "name": t["displayName"], "short": t["shortDisplayName"],
            "color": "#" + t.get("color", "333333"), "alt": "#" + t.get("alternateColor", "999999"),
            **record.get(abbr, {"w": 0, "l": 0, "conf": ""}),
        })
        for a in roster["athletes"]:
            c = a.get("contract") or {}
            salary = c.get("salary") if c.get("season", {}).get("year") == SEASON_YEAR else None
            players.append({
                "id": a["id"], "name": a["displayName"], "team": abbr,
                "pos": (a.get("position") or {}).get("abbreviation", ""),
                "age": a.get("age"), "jersey": a.get("jersey"),
                "salary": salary or None,
                "years": c.get("yearsRemaining"),
                "inj": injuries.pop(a["id"], None),
            })
    if injuries:
        print(f"Warnung: {len(injuries)} Verletzte ohne Kaderzuordnung", file=sys.stderr)

    players.sort(key=lambda p: (-(p["salary"] or 0), p["name"]))
    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "injury_report_at": injuries_raw.get("timestamp"),
        "season": "2026-27",
        "teams": out_teams,
        "players": players,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default=str(Path(__file__).with_name("data.json")))
    args = p.parse_args(argv)
    data = build()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    inj = sum(1 for x in data["players"] if x["inj"] and x["inj"]["injury"])
    print(f"{len(data['players'])} Spieler, {len(data['teams'])} Teams, {inj} verletzt -> {args.out}")


if __name__ == "__main__":
    main()
