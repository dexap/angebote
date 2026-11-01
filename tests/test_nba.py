import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("nba_build", Path(__file__).parents[1] / "nba" / "build.py")
nba = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nba)


def _athlete(aid, name, salary=None, pos="G"):
    a = {"id": aid, "displayName": name, "position": {"abbreviation": pos}, "age": 25}
    if salary is not None:
        a["contract"] = {"salary": salary, "season": {"year": nba.SEASON_YEAR}}
    return a


def _inj(aid, name, kind, status="Out", date="2026-10-28T12:00Z"):
    return {"status": status, "date": date, "shortComment": f"{name} ({kind}) is out.",
            "details": {"type": kind, "returnDate": "2026-11-20"},
            "athlete": {"displayName": name, "links": [{"href": f"https://www.espn.com/nba/player/_/id/{aid}/x"}]}}


def make_raw(injuries):
    teams, rosters = [], []
    for t in range(30):
        abbr = f"T{t:02d}"
        teams.append({"id": str(t), "abbreviation": abbr, "displayName": f"Team {t}", "color": "112233"})
        rosters.append({"athletes": [_athlete(f"{t}{i:02d}", f"Spieler {t}-{i}", salary=(t * 15 + i + 1) * 1_000_000)
                                     for i in range(14)] + [_athlete(f"{t}99", f"Two-Way {t}")]})
    return {
        "teams": teams, "rosters": rosters,
        "injuries": {"timestamp": "2026-11-01T01:00:00Z", "injuries": [{"injuries": injuries}]},
        "standings": {"children": [{"abbreviation": "East", "standings": {"entries": [
            {"team": {"abbreviation": "T00"}, "stats": [{"name": "wins", "value": 4}, {"name": "losses", "value": 2}]}]}}]},
        "news": {"articles": [
            {"type": "HeadlineNews", "headline": "Star suffers torn ACL, out for season", "published": "2026-11-01T10:00Z",
             "links": {"web": {"href": "https://espn.com/a"}}},
            {"type": "HeadlineNews", "headline": "Halloween costumes ranked", "published": "2026-11-01T11:00Z"},
            {"type": "Recap", "headline": "Team wins despite injury", "published": "2026-11-01T12:00Z"},
        ]},
    }


NOW = datetime(2026, 11, 1, 9, tzinfo=timezone.utc)


def test_transform_sorts_by_salary_and_classifies_injuries():
    raw = make_raw([_inj("2913", "Spieler 29-13", "Knee"), _inj("2912", "Spieler 29-12", "Rest")])
    data = nba.transform(raw, NOW)
    salaries = [p["salary"] or 0 for p in data["players"]]
    assert salaries == sorted(salaries, reverse=True)
    top = data["players"][0]
    assert top["name"] == "Spieler 29-13" and top["inj"]["injury"] and top["inj"]["type_de"] == "Knie"
    assert data["players"][1]["inj"]["injury"] is False  # Pause ist keine Verletzung
    assert data["players"][-1]["salary"] is None  # Two-Way ohne Gehalt ans Ende
    assert [n["headline"] for n in data["news"]] == ["Star suffers torn ACL, out for season"]
    assert next(t for t in data["teams"] if t["abbr"] == "T00")["w"] == 4


def test_metrics():
    data = nba.transform(make_raw([_inj("2913", "Spieler 29-13", "Knee", status="Day-To-Day")]), NOW)
    m = nba.metrics(data)
    assert (m["injured"], m["out"], m["top50"], m["players"]) == (1, 0, 1, 450)
    assert m["injured_salary"] == 449_000_000


def test_history_tracks_days_and_recovered_players(tmp_path):
    raw1 = make_raw([_inj("2913", "Spieler 29-13", "Knee", date="2026-10-25T12:00Z")])
    nba.update(tmp_path, raw=raw1, now=NOW)
    # Am Folgetag ist er wieder fit, ein anderer verletzt
    raw2 = make_raw([_inj("2912", "Spieler 29-12", "Ankle")])
    data, hist = nba.update(tmp_path, raw=raw2, now=datetime(2026, 11, 2, 9, tzinfo=timezone.utc))
    assert [d["date"] for d in hist["days"]] == ["2026-11-01", "2026-11-02"]
    assert hist["players"]["2913"]["first"] == "2026-10-25"  # Meldedatum vor Aufzeichnungsbeginn
    assert hist["players"]["2913"]["last"] == "2026-11-01"
    recovered = next(p for p in data["players"] if p["id"] == "2913")
    assert recovered["was"]["types"] == ["Knie"] and recovered["inj"] is None
    assert data["ever_injured"] == 2 and data["tracking_since"] == "2026-11-01"
    # Gleicher Tag erneut -> ersetzt statt doppelt
    _, hist = nba.update(tmp_path, raw=raw2, now=datetime(2026, 11, 2, 15, tzinfo=timezone.utc))
    assert len(hist["days"]) == 2


def test_update_rejects_implausible_data(tmp_path):
    raw = make_raw([])
    raw["teams"], raw["rosters"] = raw["teams"][:5], raw["rosters"][:5]
    with pytest.raises(SystemExit):
        nba.update(tmp_path, raw=raw, now=NOW)
    assert not (tmp_path / "data.json").exists()


def test_build_site_fills_meta(tmp_path):
    nba.update(tmp_path / "d", raw=make_raw([_inj("2913", "Spieler 29-13", "Knee")]), now=NOW)
    nba.build_site(tmp_path / "d", tmp_path / "out")
    page = (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
    assert "__OG_DESCRIPTION__" not in page and "1 verletzte Spieler" in page
    assert {"index.html", "og.png", "data.json", "history.json"} <= {p.name for p in (tmp_path / "out").iterdir()}
    json.loads((tmp_path / "out" / "history.json").read_text(encoding="utf-8"))
