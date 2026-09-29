"""New-world U21 snapshots, isolated from the legacy tracker."""

from __future__ import annotations

import json
import copy
import os
import re
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .api import V1Client, segment


ROOT = Path(__file__).resolve().parents[1]
TRACKER_ROOT = ROOT / "data" / "v1" / "u21-tracker"
LEGACY_LIST = ROOT / "data" / "u21-tracker" / "s73" / "meta.json"
ALIASES = {
    "cymru": "wales", "ceska rep": "czechia", "hellas": "greece",
    "h ayastan": "armenia", "hayastan": "armenia", "eesti": "estonia",
    "españa": "spain", "danmark": "denmark", "deutschland": "germany",
    "h rvatska": "croatia", "hrvatska": "croatia", "italia": "italy",
    "lietuva": "lithuania", "latvija": "latvia", "magyarorszag": "hungary",
    "nederland": "netherlands", "norge": "norway", "polska": "poland",
    "romania": "romania", "rossiya": "russia", "sakartvelo": "georgia",
    "schweiz": "switzerland", "shqiperia": "albania", "slovenija": "slovenia",
    "slovensko": "slovakia", "srbija": "serbia", "suomi": "finland",
    "sverige": "sweden", "turkiye": "turkey", "ukraina": "ukraine",
    "island": "iceland", "osterreich": "austria", "bosna i hercegovina": "bosnia and herzegovina",
    "crna gora": "montenegro", "azerbaycan": "azerbaijan", "makedonija": "north macedonia",
    "usa": "united states", "hong kong": "hong kong", "taiwan": "taiwan",
}
COUNTRY_CODE_OVERRIDES = {
    # Verified against the beta national-team endpoint. These local names do not
    # normalize to the names in the legacy 52-country list.
    "Belarus": "BY", "Belgium": "BE", "Bulgaria": "BG", "Ceska Rep.": "CZ",
    "China": "CN", "Cyprus": "CY", "Hayastan": "AM", "Hellas": "GR",
    "Hong Kong": "HK", "Ireland": "IE", "Israel": "IL", "Luxembourg": "LU",
    "Makedonija": "MK", "Rossiya": "RU", "Sakartvelo": "GE",
    "Taiwan": "TW", "Ukraina": "UA",
}


def _normal(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\b(u ?21|junior|national team)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return ALIASES.get(text, text)


def tracked_names() -> list[dict[str, Any]]:
    return json.loads(LEGACY_LIST.read_text(encoding="utf-8"))["countries"]


def _read(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _pause() -> None:
    # Development tokens allow 30 calls per minute. Scheduled jobs are deliberately slower.
    time.sleep(float(os.environ.get("BB_V1_COLLECTOR_DELAY", "2.1")))


def resolve_teams(client: V1Client, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    """Discover new-world IDs by names; never transform old integer IDs."""
    old = tracked_names()
    expected = {_normal(item["name"]): item for item in old}
    found: dict[str, list[dict[str, str]]] = {key: [] for key in expected}
    for item in (existing or {}).get("teams", []):
        key = _normal(str(item.get("name") or ""))
        if key in found:
            found[key].append({field: item[field] for field in ("countryId", "teamId", "teamName")})
    overrides = {_normal(name): code for name, code in COUNTRY_CODE_OVERRIDES.items()}
    for key, country_id in overrides.items():
        if key not in found or found[key]:
            continue
        _pause()
        teams = client.get(f"/countries/{segment(country_id)}/national-teams").get("teams", [])
        for team in teams:
            if team.get("kind") != "JuniorNationalTeam":
                continue
            found[key].append({"countryId": country_id, "teamId": str(team["id"]), "teamName": str(team["name"])})
    remaining = {key for key, values in found.items() if not values and key not in overrides}
    if remaining:
        countries = client.get("/countries").get("countries", [])
        for country in countries:
            country_id = str(country.get("id") or "")
            if not country_id or country_id in overrides.values():
                continue
            _pause()
            try:
                teams = client.get(f"/countries/{segment(country_id)}/national-teams").get("teams", [])
            except Exception:
                continue
            for team in teams:
                if team.get("kind") != "JuniorNationalTeam":
                    continue
                key = _normal(str(team.get("name") or ""))
                if key in remaining:
                    found[key].append({"countryId": country_id, "teamId": str(team["id"]), "teamName": str(team["name"])})
    mapped, unresolved = [], []
    for key, legacy in expected.items():
        candidates = found[key]
        if len(candidates) != 1:
            unresolved.append({"legacyName": legacy["name"], "candidates": candidates})
            continue
        mapped.append({"name": legacy["name"], **candidates[0]})
    result = {"teams": mapped, "unresolved": unresolved, "resolvedAt": datetime.now(timezone.utc).isoformat()}
    _write(TRACKER_ROOT / "team-map.json", result)
    return result


def current_season(client: V1Client, today: date | None = None) -> tuple[int, int]:
    today = today or datetime.now(timezone.utc).date()
    seasons = client.get("/seasons").get("seasons", [])
    for item in seasons:
        start, end = date.fromisoformat(item["startDate"]), date.fromisoformat(item["endDate"])
        if start <= today <= end:
            return int(item["number"]), (today - start).days // 7 + 1
    raise ValueError("The API did not list a season covering today.")


def collect(client: V1Client, *, today: date | None = None) -> Path:
    mapping = _read(TRACKER_ROOT / "team-map.json")
    if not mapping or mapping.get("unresolved") or len(mapping.get("teams", [])) != len(tracked_names()):
        mapping = resolve_teams(client, mapping)
    if mapping["unresolved"]:
        names = ", ".join(item["legacyName"] for item in mapping["unresolved"])
        raise ValueError(f"Resolve the new-world national teams before publishing snapshots: {names}")
    season, week = current_season(client, today)
    collected = []
    for mapped in mapping["teams"]:
        _pause()
        roster = client.get(f"/national-teams/{segment(mapped['teamId'])}/roster")
        players = []
        for player in roster.get("players", []):
            players.append({
                "playerId": str(player["id"]),
                "name": " ".join(part for part in (player.get("firstName"), player.get("lastName")) if part),
                "position": player.get("bestPosition"),
                "dmi": player.get("dmi"),
                "gameShape": player.get("gameShape"),
                "salary": player.get("salary"),
                "potential": player.get("potential"),
            })
        collected.append({**mapped, "players": players})
    now = datetime.now(timezone.utc).isoformat()
    snapshot = {"world": "v1", "season": season, "week": week, "scrapedAt": now, "countries": collected}
    directory = TRACKER_ROOT / f"s{season}"
    path = directory / f"w{week}.json"
    _write(path, snapshot)
    old_meta = _read(directory / "meta.json") or {}
    weeks = sorted(set(old_meta.get("weeks", [])) | {week})
    synthetic_weeks = sorted(set(old_meta.get("syntheticWeeks", [])) - {week})
    _write(directory / "meta.json", {
        "world": "v1", "season": season, "weeks": weeks, "updatedAt": now,
        "syntheticWeeks": synthetic_weeks,
        "countries": [{key: item[key] for key in ("name", "countryId", "teamId")} for item in collected],
    })
    return path


def add_illustrative_prior_week(season: int, source_week: int, *, root: Path | None = None) -> Path:
    """Add an explicitly synthetic DMI point at 90% of a real snapshot."""
    directory = (root or TRACKER_ROOT) / f"s{season}"
    source = _read(directory / f"w{source_week}.json")
    meta = _read(directory / "meta.json")
    if not source or not meta or source_week <= 1:
        raise ValueError("A source snapshot and metadata are required.")
    week = source_week - 1
    path = directory / f"w{week}.json"
    if path.exists():
        raise FileExistsError(f"Week {week} already exists; refusing to replace it.")
    sample = copy.deepcopy(source)
    sample["week"] = week
    sample.pop("scrapedAt", None)
    sample["syntheticDmi"] = True
    sample["note"] = f"Illustrative DMI = 90% of week {source_week}. Other values are unknown; this is not an observed snapshot."
    for country in sample.get("countries", []):
        for player in country.get("players", []):
            value = player.get("dmi")
            player["dmi"] = round(value * 0.9) if isinstance(value, (int, float)) else None
            for key in ("gameShape", "salary", "potential"):
                player[key] = None
    _write(path, sample)
    meta["weeks"] = sorted(set(meta.get("weeks", [])) | {week})
    meta["syntheticWeeks"] = sorted(set(meta.get("syntheticWeeks", [])) | {week})
    _write(directory / "meta.json", meta)
    return path


def seasons_available(root: Path | None = None) -> list[int]:
    root = root or TRACKER_ROOT
    if not root.exists():
        return []
    return sorted((int(path.name[1:]) for path in root.glob("s*") if path.is_dir() and path.name[1:].isdigit()), reverse=True)


def series(season: int, country_id: str, *, root: Path | None = None) -> dict[str, Any]:
    directory = (root or TRACKER_ROOT) / f"s{season}"
    meta = _read(directory / "meta.json") or {}
    points: dict[str, dict[str, Any]] = {}
    country_name = ""
    for week in meta.get("weeks", []):
        snapshot = _read(directory / f"w{week}.json") or {}
        country = next((item for item in snapshot.get("countries", []) if item.get("countryId") == country_id), None)
        if not country:
            continue
        country_name = country["name"]
        for player in country.get("players", []):
            item = points.setdefault(player["playerId"], {"playerId": player["playerId"], "name": player["name"], "position": player.get("position"), "points": []})
            item["name"] = player["name"]
            item["position"] = player.get("position")
            item["points"].append({"week": week, "dmi": player.get("dmi"), "gameShape": player.get("gameShape"), "salary": player.get("salary"), "potential": player.get("potential"), "syntheticDmi": bool(snapshot.get("syntheticDmi"))})
    return {"season": season, "countryId": country_id, "countryName": country_name, "weeks": meta.get("weeks", []), "syntheticWeeks": meta.get("syntheticWeeks", []), "demo": bool(meta.get("demo")), "players": sorted(points.values(), key=lambda item: item["name"].casefold())}
