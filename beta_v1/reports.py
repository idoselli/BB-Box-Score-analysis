"""Finished-match analysis using the production public API, without invented events."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any
from uuid import UUID

from .events import read_events, analyze_events
from .api import V1ApiError, V1Client, pages, segment


COUNT_FIELDS = (
    "points", "fieldGoals", "fieldGoalsAttempts", "threePointFieldGoals",
    "threePointFieldGoalsAttempts", "freeThrows", "freeThrowsAttempts",
    "rebounds", "offensiveRebounds", "assists", "turnovers", "steals",
    "blocks", "fouls", "plusMinus", "minutes",
)

POSITIONS = ("pointGuard", "shootingGuard", "smallForward", "powerForward", "center")
UNAVAILABLE = (
    "On/off and lineup-based metrics need starting lineups and complete substitution state, "
    "which the API does not export. Individual effort settings are unavailable; effort "
    "difference is shown instead. Missing historical defender/contest fields are never treated as open shots."
)


def shooting_totals(sides: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not sides:
        return None
    result: dict[str, Any] = {"games": len(sides), "zones": [], "sideZones": [], "players": []}
    def add(target, source):
        for field in ("made", "attempts", "points"):
            target[field] = target.get(field, 0) + (source.get(field) or 0)
    for split in ("open", "contested", "assisted", "unassisted"):
        result[split] = {}
        for side in sides:
            add(result[split], side.get(split) or {})
    for collection, keys in (("zones", ("zone", "side")), ("sideZones", ("zone", "side")), ("players", ("playerId",))):
        groups = {}
        for side in sides:
            for row in side.get(collection) or []:
                key = tuple(row.get(k) for k in keys)
                target = groups.setdefault(key, {k: row.get(k) for k in keys})
                for split in (("shots",) if collection != "players" else ("inside", "midRange", "three", "contested", "defended")):
                    add(target.setdefault(split, {}), row.get(split) or {})
        result[collection] = list(groups.values())
    return result


def percentages(row: dict[str, Any]) -> dict[str, Any]:
    def ratio(numerator, denominator):
        return round(100 * numerator / denominator, 2) if denominator else None
    fg, fga = row["fieldGoals"], row["fieldGoalsAttempts"]
    three, threes = row["threePointFieldGoals"], row["threePointFieldGoalsAttempts"]
    return {"fgPercent": ratio(fg, fga), "threePercent": ratio(three, threes),
            "ftPercent": ratio(row["freeThrows"], row["freeThrowsAttempts"]),
            "efgPercent": ratio(fg + .5 * three, fga),
            "tsPercent": ratio(row["points"], 2 * (fga + .44 * row["freeThrowsAttempts"]))}



class TeamSelectionRequired(ValueError):
    def __init__(self, choices):
        super().__init__("Choose the team to aggregate from the list.")
        self.choices = choices


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


def build_report(client: V1Client, match_ids: list[str], selected_team_id: str = "", *, result_filter: str = "", offense: str = "", defense: str = "", location: str = "", match_type: str = "", include_shooting: bool = True, include_events: bool = True) -> dict[str, Any]:
    if not match_ids:
        raise ValueError("Enter or select at least one match.")
    if len(match_ids) > 30:
        raise ValueError("Select at most 30 matches per report.")
    if result_filter not in {"", "W", "L"} or location not in {"", "home", "away"}:
        raise ValueError("Invalid report filter.")
    match_ids = list(dict.fromkeys(uuid_id(value) for value in match_ids))
    games: list[tuple[dict[str, Any], dict[str, Any]]] = []
    warnings = [UNAVAILABLE]
    skipped = []
    for match_id in match_ids:
        try:
            match = client.get(f"/matches/{segment(match_id)}", {"include": "boxscore"})
            box = match.get("boxScore")
            # Compatibility with servers that omit the optional expansion.
            if "boxScore" not in match:
                box = client.get(f"/matches/{segment(match_id)}/boxscore")
            if not box or match.get("isLive"):
                skipped.append({"matchId": match_id, "reason": "The finished box score is not available."})
                continue
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
        if len(games) == 1 and candidates:
            candidates = candidates[:1]
        if len(candidates) != 1:
            raise TeamSelectionRequired([{"id":key,"name":team_names.get(key,key),"games":team_counts[key]} for key in candidates])
        team_id = candidates[0]

    # Both sides across every selected match share one identity directory.
    # Opponent names must not depend on the selected team's summary rows.
    player_directory = {}
    for _, box in games:
        for side in box.get("teams", []):
            for line in side.get("players", []):
                player = line.get("player") or {}
                pid = str(player.get("id") or "")
                name = " ".join(str(part) for part in (player.get("firstName"), player.get("lastName")) if part).strip()
                if pid and name and name.lower() != "unknown player":
                    player_directory[pid] = {"name": name, "teamId": side.get("teamId")}
    player_totals: dict[str, dict[str, Any]] = {}
    match_rows: list[dict[str, Any]] = []
    strategy_counts: dict[str, Counter[str]] = defaultdict(Counter)
    rating_distributions: dict[str, Counter[str]] = defaultdict(Counter)
    own_shooting = []
    opponent_shooting = []
    position_rows = []
    event_reports = []
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
        ratings = own_box.get("ratings") or {}
        result = "W" if own_score > opponent_score else "L"
        if ((result_filter and result != result_filter)
                or (offense and ratings.get("offenseStrategy") != offense)
                or (defense and ratings.get("defensiveStrategy") != defense)
                or (location and bool(own.get("isHome")) != (location == "home"))
                or (match_type and match.get("type") != match_type)):
            skipped.append({"matchId": match_id, "reason": "Excluded by report filters."})
            continue
        if include_events:
            try:
                event_report = analyze_events(match_id, read_events(client, match_id), match, box, team_id, player_directory)
                event_reports.append(event_report)
                coverage = event_report["defenderCoverage"]
                if coverage["known"] < coverage["shots"]:
                    warnings.append(f"{match_id}: explicit defenders recorded for {coverage['known']} of {coverage['shots']} shots; unmatched shots are excluded from matchup totals.")
            except V1ApiError as exc:
                warnings.append(f"Events unavailable for {match_id}: {exc.code}: {exc}")
        shooting = None
        if include_shooting:
            try:
                shooting = client.get(f"/matches/{segment(match_id)}/shooting")
            except V1ApiError as exc:
                warnings.append(f"Shooting unavailable for {match_id}: {exc.code}: {exc}")
        shooting_sides = (shooting or {}).get("sides") or []
        def shooting_side(side_id, home):
            return next((side for side in shooting_sides if side.get("teamId") == side_id or
                         (side.get("teamId") is None and side.get("teamIndex") == (0 if home else 1))), None)
        shot = shooting_side(team_id, own.get("isHome"))
        opponent_shot = shooting_side(opponent_id, opponent.get("isHome"))
        if shot is not None:
            own_shooting.append(shot)
        if opponent_shot is not None:
            opponent_shooting.append(opponent_shot)
        match_rows.append({
            "matchId": match_id,
            "type": match.get("type"),
            "effortDelta": box.get("effortDelta"),
            "pp100": own_box.get("pp100"),
            "opponentPp100": opponent_box.get("pp100"),
            "shooting": shot,
            "opponentShooting": opponent_shot,
            "playerLines": lines,
            "opponentPlayerLines": opponent_box.get("players") or [],
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
            if key in {"offenseStrategy", "defensiveStrategy", "predictionFocus", "predictionPace", "offensiveRebounding", "defensiveRebounding"}:
                strategy_counts[key][str(value)] += 1
            elif key != "sublevels":
                rating_distributions[key][str(value)] += 1
        for line in lines:
            player = line.get("player") or {}
            player_id = str(player.get("id") or "")
            if not player_id:
                continue
            if not any(line.get(field) for field in COUNT_FIELDS) and line.get("starRating") is None:
                continue
            entry = player_totals.setdefault(player_id, {
                "playerId": player_id,
                "name": player_directory.get(player_id, {}).get("name") or "Unknown player",
                "games": 0,
                "minutesByPosition": {pos: 0 for pos in POSITIONS},
                "positionMinutesGames": 0,
                "missingPositionMinutesGames": 0,
                "positions": set(),
                "starRatingTotal": 0.0,
                "starRatingGames": 0,
                **{field: 0 for field in COUNT_FIELDS},
            })
            entry["games"] += 1
            split = line.get("minutesByPosition")
            valid_split = (isinstance(split, dict) and all(isinstance(split.get(pos), int) and split[pos] >= 0 for pos in POSITIONS)
                           and sum(split[pos] for pos in POSITIONS) == line.get("minutes", 0))
            if valid_split:
                entry["positionMinutesGames"] += 1
                for pos in POSITIONS:
                    entry["minutesByPosition"][pos] += split[pos]
                position_rows.append({"matchId": match_id, "playerId": player_id,
                                      "offense": ratings.get("offenseStrategy"),
                                      "defense": ratings.get("defensiveStrategy"), **split})
            else:
                entry["missingPositionMinutesGames"] += 1
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
        entry.update(percentages(entry))
        entry["perGame"] = {field: entry[field] / entry["games"] for field in COUNT_FIELDS}
        entry["per36"] = {field: 36 * entry[field] / entry["minutes"] if entry["minutes"] else None for field in COUNT_FIELDS if field != "minutes"}
        players.append(entry)
    referenced = {str(e.get(field)) for event_report in event_reports for e in event_report["events"]
                  for field in ("player1Id", "player2Id", "primaryDefenderId", "helpDefenderId") if e.get(field)}
    from .events import ZERO_UUID
    unresolved = sorted(pid for pid in referenced if pid != ZERO_UUID and pid not in player_directory)
    for pid in unresolved[:8]:
        try:
            player = client.get(f"/players/{segment(uuid_id(pid))}")
        except V1ApiError as exc:
            if exc.status in {401,429,503}:
                break
            continue
        label = " ".join(str(part) for part in (player.get("firstName"), player.get("lastName")) if part).strip()
        if label and label.lower() != "unknown player":
            player_directory[pid] = {"name":label,"teamId":(player.get("club") or {}).get("id")}
    for event_report in event_reports:
        for event in event_report["events"] + event_report["shots"]:
            for field,label in (("player1Id","player1Name"),("player2Id","player2Name"),("primaryDefenderId","defenderName"),("helpDefenderId","helpDefenderName")):
                pid = str(event.get(field) or "")
                event[label] = player_directory.get(pid, {}).get("name") or ("Unknown player" if pid and pid != ZERO_UUID else "")
        for row in event_report["matchups"]:
            row["shooter"] = player_directory.get(row["shooterId"],{}).get("name") or "Unknown player"
            row["defender"] = player_directory.get(row["defenderId"],{}).get("name") or "Unknown player"
    for entry in players:
        entry["name"] = player_directory.get(entry["playerId"],{}).get("name") or "Unknown player"
    remaining = sum(pid not in player_directory for pid in unresolved)
    if remaining:
        warnings.append(f"Names unavailable for {remaining} event participants; shown as Unknown player with IDs retained only in exports and tooltips.")
    players.sort(key=lambda entry: (-entry["minutes"], entry["name"]))
    match_rows.sort(key=lambda row: row["scheduledAt"], reverse=True)
    return {
        "world": "v1",
        "submittedMatches": len(match_ids),
        "playerNames": {pid: row["name"] for pid, row in player_directory.items()},
        "teamId": team_id,
        "teamName": team_names.get(team_id, team_id),
        "teamChoices": [{"id": key, "name": value} for key, value in team_names.items()],
        "warnings": list(dict.fromkeys(warnings)),
        "shooting": shooting_totals(own_shooting),
        "opponentShooting": shooting_totals(opponent_shooting),
        "positionMinutes": position_rows,
        "eventReports": event_reports,
        "events": [e for r in event_reports for e in r["events"]],
        "shotLog": [e for r in event_reports for e in r["shots"]],
        "matchups": [dict(row, matchId=r["matchId"]) for r in event_reports for row in r["matchups"]],
        "eventCoverageGames": len(event_reports),
        "totals": _totals([row["totals"] for row in match_rows]),
        "opponentTotals": _totals([row["opponentTotals"] for row in match_rows]),
        "matches": match_rows,
        "players": players,
        "strategyCounts": {key: dict(counts) for key, counts in strategy_counts.items()},
        "ratingDistributions": {key: dict(counts) for key, counts in rating_distributions.items()},
        "skipped": skipped,
        "usedMatches": len(match_rows),
        "wins": sum(row["result"] == "W" for row in match_rows),
        "losses": sum(row["result"] == "L" for row in match_rows),
    }
