"""Aggregation helpers for U21/NT weekly-minutes analyzers.

Ported from bb_fantasy `aggregateGameLogs` / overview week totals.
Kept separate from CoachParrot `u21_training.aggregate_minutes`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bb_site import GameLogEntry
from u21_training import get_game_week, get_season_start_date, is_counting_game


def current_week_for_season(season: int, now: datetime | None = None) -> int | None:
    now = now or datetime.now(timezone.utc)
    season_start = get_season_start_date(season)
    diff_days = (now - season_start).days
    if diff_days < 0 or diff_days >= 98:
        return None
    return diff_days // 7 + 1


def overview_for_games(
    games: list[GameLogEntry],
    *,
    season: int,
    current_week: int | None,
) -> dict[str, Any]:
    week_minutes_by_position: dict[str, int] = {}
    season_minutes_by_position: dict[str, int] = {}
    week_total = 0
    season_total = 0

    for game in games:
        if not is_counting_game(game.game_type):
            continue
        week = get_game_week(game.date, season)
        if week is None:
            continue
        if game.position:
            season_minutes_by_position[game.position] = (
                season_minutes_by_position.get(game.position, 0) + game.minutes
            )
        season_total += game.minutes
        if current_week is not None and week == current_week:
            if game.position:
                week_minutes_by_position[game.position] = (
                    week_minutes_by_position.get(game.position, 0) + game.minutes
                )
            week_total += game.minutes

    return {
        "weekMinutesByPosition": week_minutes_by_position,
        "seasonMinutesByPosition": season_minutes_by_position,
        "weekTotal": week_total,
        "seasonTotal": season_total,
    }


def aggregate_game_logs(season_logs: list[dict[str, Any]]) -> dict[str, Any]:
    minutes_by_position: dict[str, int] = {}
    minutes_by_season: dict[int, int] = {}
    games_by_season: dict[int, int] = {}
    minutes_by_season_week_position: dict[int, dict[int, dict[str, int]]] = {}
    minutes_by_season_position: dict[int, dict[str, int]] = {}
    minutes_outside_window: dict[int, int] = {}

    available_seasons = {int(item["season"]) for item in season_logs}

    for item in season_logs:
        season = int(item["season"])
        games: list[GameLogEntry] = item["games"]
        games_by_season[season] = len(games)
        minutes_by_season_week_position.setdefault(season, {})
        minutes_by_season_position.setdefault(season, {})
        minutes_outside_window.setdefault(season, 0)

    for item in season_logs:
        season = int(item["season"])
        games: list[GameLogEntry] = item["games"]
        season_minutes = 0

        for game in games:
            if not is_counting_game(game.game_type):
                continue

            week = get_game_week(game.date, season)
            if week is not None:
                season_minutes += game.minutes
                if game.position:
                    minutes_by_position[game.position] = (
                        minutes_by_position.get(game.position, 0) + game.minutes
                    )
                    minutes_by_season_position[season][game.position] = (
                        minutes_by_season_position[season].get(game.position, 0) + game.minutes
                    )
                    week_map = minutes_by_season_week_position[season].setdefault(week, {})
                    week_map[game.position] = week_map.get(game.position, 0) + game.minutes
                continue

            prev_week = get_game_week(game.date, season - 1)
            if prev_week is not None:
                if (season - 1) in available_seasons:
                    if game.position:
                        minutes_by_position[game.position] = (
                            minutes_by_position.get(game.position, 0) + game.minutes
                        )
                        minutes_by_season_position[season - 1][game.position] = (
                            minutes_by_season_position[season - 1].get(game.position, 0)
                            + game.minutes
                        )
                        week_map = minutes_by_season_week_position[season - 1].setdefault(
                            prev_week, {}
                        )
                        week_map[game.position] = week_map.get(game.position, 0) + game.minutes
                else:
                    season_minutes += game.minutes
                    if game.position:
                        minutes_by_position[game.position] = (
                            minutes_by_position.get(game.position, 0) + game.minutes
                        )
                        minutes_by_season_position[season][game.position] = (
                            minutes_by_season_position[season].get(game.position, 0) + game.minutes
                        )
                        week_map = minutes_by_season_week_position[season].setdefault(0, {})
                        week_map[game.position] = week_map.get(game.position, 0) + game.minutes
            else:
                minutes_outside_window[season] += game.minutes
                season_minutes += game.minutes

        minutes_by_season[season] = season_minutes

    return {
        "minutesByPosition": minutes_by_position,
        "minutesBySeason": {str(k): v for k, v in minutes_by_season.items()},
        "gamesBySeason": {str(k): v for k, v in games_by_season.items()},
        "minutesBySeasonWeekPosition": {
            str(season): {
                str(week): positions
                for week, positions in weeks.items()
            }
            for season, weeks in minutes_by_season_week_position.items()
        },
        "minutesBySeasonPosition": {
            str(season): positions for season, positions in minutes_by_season_position.items()
        },
        "minutesOutsideWindow": {str(k): v for k, v in minutes_outside_window.items()},
    }
