#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any

import requests

from bb_site import BB_BASE, BB_UA, BBSiteClient
from bbapi import BBApi
from minutes_agg import current_week_for_season


ROOT = Path(__file__).resolve().parent
TRACKER_ROOT = ROOT / "data" / "u21-tracker"
STANDINGS_URL = "https://buzzerbeater.com/world/standings.aspx?teamid=1015"
TRACKER_SEASON_73_START = datetime(2026, 8, 7, tzinfo=timezone.utc)
TRACKER_SEASON_DURATION_DAYS = 98


def load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value


def plain_text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ")).strip()


def parse_round_robin_pools(html: str) -> list[dict[str, Any]]:
    start = re.search(r"Round Robin Pools", html, re.I)
    chunk = html[start.start() :] if start else html
    countries: list[dict[str, Any]] = []
    seen: set[int] = set()
    pool_re = re.compile(
        r"<b>\s*(Pool\s+[A-Z0-9]+)\s*</b>([\s\S]*?)(?=<b>\s*Pool\s+[A-Z0-9]+\s*</b>|$)",
        re.I,
    )
    row_re = re.compile(r"<tr[^>]*rptrStandings[^>]*trEntry[^>]*>[\s\S]*?</tr>", re.I)
    link_re = re.compile(
        r'href=["\']/country/(\d+)/jnt/overview\.aspx["\'][^>]*>\s*([^<]+?)\s*</a>',
        re.I,
    )

    for pool_match in pool_re.finditer(chunk):
        pool = plain_text(pool_match.group(1))
        body = re.split(r"Recent Matches", pool_match.group(2), flags=re.I)[0]
        rows = row_re.findall(body)
        search_in = "\n".join(rows) if rows else body
        for link_match in link_re.finditer(search_in):
            country_id = int(link_match.group(1))
            if country_id in seen:
                continue
            name = plain_text(link_match.group(2))
            name = re.sub(r"\s+U21\s*$", "", name, flags=re.I).strip()
            countries.append({"countryId": country_id, "name": name, "pool": pool})
            seen.add(country_id)
    return countries


def fetch_round_robin_countries() -> list[dict[str, Any]]:
    response = requests.get(
        STANDINGS_URL,
        headers={"User-Agent": BB_UA, "Accept": "text/html,*/*;q=0.9"},
        timeout=30,
    )
    response.raise_for_status()
    countries = parse_round_robin_pools(response.text)
    if not countries:
        raise ValueError("No U21 Round Robin pool countries were parsed from the standings page.")
    return countries


def tracker_season_start(season: int) -> datetime:
    return TRACKER_SEASON_73_START + timedelta(
        days=(season - 73) * TRACKER_SEASON_DURATION_DAYS
    )


def current_tracker_season(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    if now < TRACKER_SEASON_73_START:
        return 72
    days_since_s73 = (now - TRACKER_SEASON_73_START).days
    return 73 + days_since_s73 // TRACKER_SEASON_DURATION_DAYS


def current_tracker_week(season: int, now: datetime | None = None) -> int | None:
    now = now or datetime.now(timezone.utc)
    diff_days = (now - tracker_season_start(season)).days
    if diff_days < 0 or diff_days >= TRACKER_SEASON_DURATION_DAYS:
        return None
    return diff_days // 7 + 1


def tracker_dir(season: int) -> Path:
    return TRACKER_ROOT / f"s{season}"


def write_week_snapshot(season: int, week: int, payload: dict[str, Any]) -> Path:
    directory = tracker_dir(season)
    directory.mkdir(parents=True, exist_ok=True)
    week_path = directory / f"w{week}.json"
    week_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    weeks = sorted(
        int(path.stem[1:])
        for path in directory.glob("w*.json")
        if path.stem[1:].isdigit()
    )
    countries = [
        {"countryId": item["countryId"], "name": item["name"], "pool": item["pool"]}
        for item in payload.get("countries", [])
    ]

    meta_path = directory / "meta.json"
    if meta_path.exists():
        try:
            previous = json.loads(meta_path.read_text(encoding="utf-8"))
            by_id = {int(item["countryId"]): item for item in previous.get("countries", [])}
            for country in countries:
                by_id[int(country["countryId"])] = country
            countries = sorted(by_id.values(), key=lambda item: str(item["name"]).casefold())
        except (OSError, ValueError, TypeError):
            countries = sorted(countries, key=lambda item: str(item["name"]).casefold())
    else:
        countries = sorted(countries, key=lambda item: str(item["name"]).casefold())

    meta = {
        "season": season,
        "weeks": weeks,
        "countries": countries,
        "updatedAt": payload["scrapedAt"],
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return week_path


def seed_week_zero(payload: dict[str, Any]) -> dict[str, Any]:
    seeded = json.loads(json.dumps(payload))
    seeded["week"] = 0
    seeded["synthetic"] = True
    seeded["note"] = "One-time seed: DMI -25%, game shape -2 from current week scrape"
    for country in seeded.get("countries", []):
        for player in country.get("players", []):
            if player.get("dmi") is not None:
                player["dmi"] = max(0, round(int(player["dmi"]) * 0.75))
            if player.get("gameShape") is not None:
                player["gameShape"] = max(0, int(player["gameShape"]) - 2)
    return seeded


def env_value(name: str, fallback: str = "") -> str:
    return os.environ.get(name, fallback).strip()


def scrape_country(
    country: dict[str, Any],
    *,
    site: BBSiteClient,
    api: BBApi,
) -> dict[str, Any]:
    try:
        _, roster = site.fetch_u21_roster(country["countryId"])
    except Exception as exc:
        return {**country, "players": [], "error": str(exc)}

    players: list[dict[str, Any]] = []
    for roster_player in roster:
        try:
            info = api.player_info(roster_player.player_id)
            first_name = str(info.get("first_name") or "").strip()
            last_name = str(info.get("last_name") or "").strip()
            api_name = " ".join(part for part in [first_name, last_name] if part)
            players.append(
                {
                    "playerId": int(info.get("player_id") or roster_player.player_id),
                    "name": api_name or roster_player.name,
                    "dmi": info.get("dmi"),
                    "gameShape": info.get("game_shape"),
                    "salary": info.get("salary"),
                }
            )
        except Exception:
            players.append(
                {
                    "playerId": roster_player.player_id,
                    "name": roster_player.name,
                    "dmi": None,
                    "gameShape": None,
                    "salary": None,
                }
            )
    return {**country, "players": players}


def build_snapshot(
    *,
    season: int,
    week: int,
    countries: list[dict[str, Any]],
    username: str,
    bbapi_code: str,
    site_password: str,
) -> dict[str, Any]:
    site = BBSiteClient(username, site_password)
    site.login()
    api = BBApi(username, bbapi_code)
    if not getattr(api, "logged_in", False):
        raise ValueError("BBAPI login failed.")

    country_results: list[dict[str, Any]] = []
    for index, country in enumerate(countries, start=1):
        print(f"[{index}/{len(countries)}] {country['name']} ({country['pool']})", flush=True)
        country_results.append(scrape_country(country, site=site, api=api))
        time.sleep(0.08)

    return {
        "season": season,
        "week": week,
        "scrapedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": STANDINGS_URL,
        "countries": sorted(country_results, key=lambda item: str(item["name"]).casefold()),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape U21 tracker weekly snapshots.")
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument("--seed-week0", action="store_true")
    parser.add_argument("--max-countries", type=int, default=None)
    parser.add_argument("--countries", default="")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    season = args.season or (
        int(env_value("CURRENT_SEASON")) if env_value("CURRENT_SEASON") else current_tracker_season()
    )
    week = args.week if args.week is not None else current_tracker_week(season)
    if week is None:
        week = current_week_for_season(season)
    if week is None:
        raise ValueError(f"Could not determine current week for season {season}.")

    username = env_value("BBAPI_LOGIN") or env_value("BB_LOGIN")
    bbapi_code = env_value("BBAPI_CODE")
    site_password = env_value("BB_PASSWORD")
    if not username or not bbapi_code or not site_password:
        raise ValueError("BBAPI_LOGIN, BBAPI_CODE, and BB_PASSWORD are required.")

    countries = fetch_round_robin_countries()
    if args.countries:
        allowed = {int(value.strip()) for value in args.countries.split(",") if value.strip().isdigit()}
        countries = [country for country in countries if int(country["countryId"]) in allowed]
    if args.max_countries and args.max_countries > 0:
        countries = countries[: args.max_countries]
    if not countries:
        raise ValueError("No countries selected for scraping.")

    print(f"Season {season}, week {week}, countries {len(countries)}", flush=True)
    payload = build_snapshot(
        season=season,
        week=week,
        countries=countries,
        username=username,
        bbapi_code=bbapi_code,
        site_password=site_password,
    )
    week_path = write_week_snapshot(season, week, payload)
    print(f"Wrote {week_path}", flush=True)

    if args.seed_week0:
        week0_path = write_week_snapshot(season, 0, seed_week_zero(payload))
        print(f"Wrote {week0_path}", flush=True)


if __name__ == "__main__":
    main()
