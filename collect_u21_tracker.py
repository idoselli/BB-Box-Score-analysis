"""Collect production BuzzerBeater U21 rosters for Nika's weekly tracker."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import os
import time
from zoneinfo import ZoneInfo

from beta_v1 import tracker
from beta_v1.api import V1Client, segment
from scrape_u21_tracker import env_value, load_dotenv


PRODUCTION_API = "https://next-api.buzzerbeater.com/v1"
EXTRA_COUNTRIES = {"US", "CN", "HK", "TW", "IL"}  # Keep Israel in Nika's tracker.
REQUEST_INTERVAL = 2.1  # Personal tokens allow 30 requests per minute.
FIRST_FRIDAY_OVERRIDES = {74: date(2026, 11, 20)}


def snapshot_period(seasons: list[dict], today: date) -> tuple[int, int]:
    periods = []
    for season in seasons:
        number = season["number"]
        start = date.fromisoformat(season["startDate"])
        end = date.fromisoformat(season["endDate"]) if season.get("endDate") else None
        friday_on_or_before_start = start - timedelta(days=(start.weekday() - 4) % 7)
        first_friday = FIRST_FRIDAY_OVERRIDES.get(number, friday_on_or_before_start)
        if first_friday <= today and (end is None or today <= end):
            periods.append((first_friday, number))

    if not periods:
        raise ValueError(f"The API calendar has no tracker season covering {today}.")
    first_friday, number = max(periods)
    # Each tracker week ends with the Friday training snapshot.
    return number, ((today - first_friday).days + 6) // 7 + 1


def tracked_countries(client: V1Client, country_ids: set[str]) -> list[dict]:
    countries = client.get("/countries")["countries"]
    tracked = {
        country["id"]: country
        for country in countries
        if country.get("confederation") == "Europe" or country["id"] in EXTRA_COUNTRIES
    }
    missing = (country_ids or EXTRA_COUNTRIES) - tracked.keys()
    if missing:
        raise ValueError(f"Expected tracker countries missing from the API: {', '.join(sorted(missing))}.")
    if not country_ids and not any(country.get("confederation") == "Europe" for country in tracked.values()):
        raise ValueError("The API returned no countries in the European confederation.")
    selected = (tracked[code] for code in country_ids) if country_ids else tracked.values()
    return sorted(selected, key=lambda country: country["name"].casefold())


def collect_roster(client: V1Client, country: dict) -> dict:
    code = country["id"]
    time.sleep(REQUEST_INTERVAL)
    teams = client.get(f"/countries/{segment(code)}/national-teams")["teams"]
    junior_teams = [team for team in teams if team["kind"] == "JuniorNationalTeam"]
    if len(junior_teams) != 1:
        raise ValueError(f"Expected one U21 squad for {code}, found {len(junior_teams)}.")

    team_id = junior_teams[0]["id"]
    time.sleep(REQUEST_INTERVAL)
    roster = client.get(f"/national-teams/{segment(team_id)}/roster")
    if roster["teamId"] != team_id or not isinstance(roster["players"], list):
        raise ValueError(f"Invalid roster response for {code}.")

    players = []
    for player in roster["players"]:
        if type(player.get("dmi")) is not int or player["dmi"] < 0:
            raise ValueError(f"Missing or invalid DMI for player {player['id']} in {code}.")
        players.append({
            "playerId": player["id"],
            "name": f"{player['firstName']} {player['lastName']}".strip(),
            "position": player.get("bestPosition"),
            "dmi": player["dmi"],
            "gameShape": player.get("gameShape"),
            "salary": player.get("salary"),
            "potential": player.get("potential"),
        })
    return {
        "countryId": code,
        "name": country["name"],
        "teamId": team_id,
        "players": sorted(players, key=lambda player: (player["name"].casefold(), player["playerId"])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week", type=int, help="Override the calculated tracker week.")
    parser.add_argument("--countries", default="", help="Comma-separated API country codes for a test run.")
    parser.add_argument("--dry-run", action="store_true", help="Verify roster access without writing a snapshot.")
    args = parser.parse_args()
    if args.week is not None and args.week < 1:
        parser.error("--week must be positive")
    if args.countries and not args.dry_run:
        parser.error("--countries requires --dry-run")

    load_dotenv()
    token = env_value("BB_U21_API_TOKEN")
    if not token:
        raise SystemExit("BB_U21_API_TOKEN must contain a production personal token with Public scope.")
    client = V1Client(token, base_url=PRODUCTION_API)
    now = datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("Asia/Jerusalem")).date()
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        today -= timedelta(days=(today.weekday() - 4) % 7)
    season, calculated_week = snapshot_period(client.get("/seasons")["seasons"], today)
    week = args.week if args.week is not None else calculated_week
    directory = tracker.PRODUCTION_TRACKER_ROOT / f"s{season}"
    if not args.dry_run and (directory / f"w{week}.json").exists():
        meta = tracker._read(directory / "meta.json") or {}
        if week in meta.get("weeks", []):
            tracker.write_production_index()
            print(f"Season {season}, week {week} already recorded.")
            return
    country_ids = {code.strip().upper() for code in args.countries.split(",") if code.strip()}
    countries = tracked_countries(client, country_ids)

    print(f"Season {season}, week {week}, {len(countries)} squads", flush=True)
    results = []
    for index, country in enumerate(countries, start=1):
        roster = collect_roster(client, country)
        results.append(roster)
        print(f"[{index}/{len(countries)}] {country['name']}: {len(roster['players'])} players", flush=True)

    if not args.dry_run:
        path = tracker.save_snapshot(
            tracker.PRODUCTION_TRACKER_ROOT, season, week, results, now.isoformat()
        )
        tracker.write_production_index()
        print(f"Wrote {path}", flush=True)


if __name__ == "__main__":
    main()
