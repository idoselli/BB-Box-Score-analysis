"""Box-score-only multi-match aggregation for the beta world."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any
from uuid import UUID

from .api import V1ApiError, V1Client, pages, segment


COUNT_FIELDS = (
    "points", "fieldGoals", "fieldGoalsAttempts", "threePointFieldGoals",
    "threePointFieldGoalsAttempts", "freeThrows", "freeThrowsAttempts",
    "rebounds", "offensiveRebounds", "assists", "turnovers", "steals",
    "blocks", "fouls", "plusMinus", "minutes",
)

UNAVAILABLE = (
    "Play-by-play, shot maps, defended shots, on/off, matchups, clutch analysis, "
    "effort, GDP, and minutes split by position are not exposed by the v1 API. "
    "This report uses box-score totals only."
)


def uuid_id(value: str) -> str:
    try:
        return str(UUID(str(value).strip()))
    except (ValueError, AttributeError) as exc:
        raise ValueError("Enter a valid new-world UUID.") from exc


def parse_ids(text: str, *, max_ids: int = 30) -> list[str]:
    ids = []
    for raw in text.replace(",", " ").split():
        match_id = uuid_id(raw)
        if match_id not in ids:
            ids.append(match_id)
    if len(ids) > max_ids:
        raise ValueError(f"Select at most {max_ids} matches per report.")
    return ids


def schedule_ids(client: V1Client, team_id: str, season: int | None, count: int = 10) -> list[str]:
    if count < 1 or count > 30:
        raise ValueError("Choose between 1 and 30 schedule matches.")
    params = {"season": season} if season is not None else {}
    rows = pages(client, f"/teams/{segment(uuid_id(team_id))}/schedule", "matches", params=params, max_items=300)
    finished = [
        row for row in rows
        if row.get("finishedAt") and all(side.get("score") is not None for side in row.get("teams", []))
    ]
    finished.sort(key=lambda row: row.get("scheduledAt", ""), reverse=True)
    return [uuid_id(row["id"]) for row in finished[:count]]


def _side_key(side: dict[str, Any]) -> str:
    return str(side.get("teamId") or "")


def _totals(lines: list[dict[str, Any]]) -> dict[str, int]:
    return {field: sum(int(line.get(field) or 0) for line in lines) for field in COUNT_FIELDS}


def build_report(client: V1Client, match_ids: list[str], selected_team_id: str = "") -> dict[str, Any]:
    if not match_ids:
        raise ValueError("Enter or select at least one match.")
    games: list[tuple[dict[str, Any], dict[str, Any]]] = []
    warnings = [UNAVAILABLE]
    skipped = []
    for match_id in match_ids:
        try:
            match = client.get(f"/matches/{segment(match_id)}")
            box = client.get(f"/matches/{segment(match_id)}/boxscore")
        except V1ApiError as exc:
            skipped.append({"matchId": match_id, "reason": str(exc)})
            continue
        games.append((match, box))
    if not games:
        raise ValueError("No completed box scores were available for the selected matches.")

    team_counts: dict[str, int] = defaultdict(int)
    team_names: dict[str, str] = {}
    for match, _ in games:
        for side in match.get("teams", []):
            team_id = _side_key(side)
            if team_id:
                team_counts[team_id] += 1
                team_names[team_id] = str(side.get("name") or team_id)
    if selected_team_id:
        team_id = uuid_id(selected_team_id)
        if team_id not in team_counts:
            raise ValueError("The selected team is not present in these matches.")
    else:
        max_count = max(team_counts.values(), default=0)
        candidates = [key for key, count in team_counts.items() if count == max_count]
        if len(candidates) != 1:
            raise ValueError("More than one team appears equally often. Enter the team UUID to aggregate.")
        team_id = candidates[0]

    player_totals: dict[str, dict[str, Any]] = {}
    match_rows: list[dict[str, Any]] = []
    strategy_counts: dict[str, Counter[str]] = defaultdict(Counter)
    rating_distributions: dict[str, Counter[str]] = defaultdict(Counter)
    for match, box in games:
        match_id = str(match.get("id") or box.get("matchId") or "")
        sides = {str(side.get("teamId")): side for side in match.get("teams", []) if side.get("teamId")}
        box_sides = {str(side.get("teamId")): side for side in box.get("teams", []) if side.get("teamId")}
        own, own_box = sides.get(team_id), box_sides.get(team_id)
        if not own or not own_box:
            skipped.append({"matchId": match_id, "reason": "Selected team missing from match or box score."})
            continue
        opponents = [(key, value) for key, value in sides.items() if key != team_id]
        if len(opponents) != 1:
            skipped.append({"matchId": match_id, "reason": "Could not identify the opponent."})
            continue
        opponent_id, opponent = opponents[0]
        opponent_box = box_sides.get(opponent_id, {})
        own_score = own.get("score")
        opponent_score = opponent.get("score")
        lines = own_box.get("players") or []
        if own_score is None or opponent_score is None:
            skipped.append({"matchId": match_id, "reason": "The match is not complete."})
            continue
        match_rows.append({
            "matchId": match_id,
            "scheduledAt": match.get("scheduledAt", ""),
            "team": team_names.get(team_id, team_id),
            "opponent": opponent.get("name") or opponent_id,
            "home": own.get("isHome"),
            "score": f"{own_score}–{opponent_score}",
            "result": "W" if own_score > opponent_score else "L",
            "periodScores": own.get("periodScores") or [],
            "opponentPeriodScores": opponent.get("periodScores") or [],
            "totals": _totals(lines),
            "opponentTotals": _totals(opponent_box.get("players") or []),
            "ratings": own_box.get("ratings") or {},
            "opponentRatings": opponent_box.get("ratings") or {},
        })
        for key, value in (own_box.get("ratings") or {}).items():
            if value is None:
                continue
            if key in {"offenseStrategy", "defensiveStrategy"}:
                strategy_counts[key][str(value)] += 1
            else:
                rating_distributions[key][str(value)] += 1
        for line in lines:
            player = line.get("player") or {}
            player_id = str(player.get("id") or "")
            if not player_id:
                continue
            entry = player_totals.setdefault(player_id, {
                "playerId": player_id,
                "name": " ".join(part for part in (player.get("firstName"), player.get("lastName")) if part) or player_id,
                "games": 0,
                "positions": set(),
                "starRatingTotal": 0.0,
                "starRatingGames": 0,
                **{field: 0 for field in COUNT_FIELDS},
            })
            entry["games"] += 1
            if line.get("position"):
                entry["positions"].add(str(line["position"]))
            if line.get("starRating") is not None:
                entry["starRatingTotal"] += float(line["starRating"])
                entry["starRatingGames"] += 1
            for field in COUNT_FIELDS:
                entry[field] += int(line.get(field) or 0)
    if not match_rows:
        raise ValueError("No matches included a completed box score for that team.")
    players = []
    for entry in player_totals.values():
        star_games = entry.pop("starRatingGames")
        star_total = entry.pop("starRatingTotal")
        entry["averageStarRating"] = round(star_total / star_games, 2) if star_games else None
        entry["positions"] = sorted(entry["positions"])
        players.append(entry)
    players.sort(key=lambda entry: (-entry["minutes"], entry["name"]))
    match_rows.sort(key=lambda row: row["scheduledAt"], reverse=True)
    return {
        "world": "v1",
        "teamId": team_id,
        "teamName": team_names.get(team_id, team_id),
        "warnings": warnings,
        "matches": match_rows,
        "players": players,
        "strategyCounts": {key: dict(counts) for key, counts in strategy_counts.items()},
        "ratingDistributions": {key: dict(counts) for key, counts in rating_distributions.items()},
        "skipped": skipped,
        "usedMatches": len(match_rows),
        "wins": sum(row["result"] == "W" for row in match_rows),
        "losses": sum(row["result"] == "L" for row in match_rows),
    }
