from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

from bb_site import GameLogEntry, RosterPlayer
from coachparrot_model import (
    DEFAULT_POTENTIAL,
    POSITION_PRESETS,
    SKILLS,
    TrainingAction,
    bb_height_to_cm,
    listed_salary,
    nearest_height_cm,
    normalize_position,
    profile_dict,
    replay_training,
    solve_start_profile,
)


POSITIONS = ("PG", "SG", "SF", "PF", "C")
TIE_PRIORITY = {"C": 0, "PG": 1, "SG": 2, "SF": 3, "PF": 4}
SEASON_72_START = datetime(2026, 5, 2, tzinfo=timezone.utc)
SEASON_DURATION_DAYS = 98
TRAINING_THRESHOLD_MINUTES = 46
NON_COUNTING_EXACT = {"bbm", "bbb", "national team", "private"}
SKILL_LABELS = {
    4: ("inept", "#30139F"),
    5: ("mediocre", "#700BA2"),
    6: ("average", "#910B9D"),
    7: ("respectable", "#AD0B88"),
    8: ("strong", "#B70B5A"),
    9: ("proficient", "#9C0B32"),
    10: ("prominent", "#A70B00"),
    11: ("prolific", "#BD2600"),
    12: ("sensational", "#CB3100"),
    13: ("tremendous", "#D93C00"),
    14: ("wondrous", "#DB6E04"),
    15: ("marvelous", "#E5A64B"),
    16: ("prodigious", "#AC860A"),
    17: ("stupendous", "#8E9800"),
    18: ("phenomenal", "#498E00"),
    19: ("colossal", "#0EAE28"),
}
SKILL_DISPLAY_ORDER = (("JS", "JR"), ("OD", "HA"), ("DR", "PA"), ("IS", "ID"), ("RB", "SB"))


@dataclass(frozen=True)
class PlayerMetadata:
    player_id: int
    first_name: str = ""
    last_name: str = ""
    age: int | None = None
    height: int | None = None
    salary: int | None = None
    best_position: str = "SG"
    potential: int | None = None
    game_shape: int | None = None
    dmi: int | None = None


@dataclass(frozen=True)
class InferredAction:
    season: int
    week: int
    action: TrainingAction


def get_season_start_date(season: int) -> datetime:
    return SEASON_72_START - timedelta(days=(72 - season) * SEASON_DURATION_DAYS)


def _game_week_for_date(game_date: datetime, season: int) -> int | None:
    diff_days = (game_date - get_season_start_date(season)).days
    if diff_days < 0 or diff_days >= SEASON_DURATION_DAYS:
        return None
    return diff_days // 7 + 1


def get_game_week(date_str: str, season: int) -> int | None:
    parts = (date_str or "").split("/")
    if len(parts) == 3:
        try:
            first, second, year = [int(part) for part in parts]
        except ValueError:
            first = second = year = 0
        if first and second and year:
            candidates = [(first, second)]
            if first <= 12 and second <= 12 and first != second:
                candidates.append((second, first))
            elif first > 12 >= second:
                candidates = [(second, first)]
            for month, day in candidates:
                try:
                    week = _game_week_for_date(datetime(year, month, day, tzinfo=timezone.utc), season)
                except ValueError:
                    week = None
                if week is not None:
                    return week

    try:
        game_date = datetime.strptime(date_str, "%m/%d/%Y").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            game_date = datetime.strptime(date_str, "%-m/%-d/%Y").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return _game_week_for_date(game_date, season)


def age_for_season(current_age: int | None, current_season: int, season: int) -> int | None:
    if current_age is None:
        return None
    return current_age - (current_season - season)


def is_counting_game(game_type: str) -> bool:
    value = " ".join((game_type or "").strip().casefold().split())
    if not value:
        return True
    if value in NON_COUNTING_EXACT:
        return False
    if "national" in value or value in {"nt", "u21 nt", "u21 national team"}:
        return False
    return True


def target_seasons_for_player(current_age: int | None, current_season: int) -> list[int]:
    if current_age is None:
        return [current_season - i for i in range(3, -1, -1)]
    seasons = {
        current_season - (current_age - target_age)
        for target_age in (18, 19, 20, 21)
        if 0 < current_season - (current_age - target_age) <= current_season
    }
    seasons.add(current_season)
    return sorted(seasons)


def aggregate_minutes(
    logs_by_season: dict[int, list[GameLogEntry]]
) -> tuple[dict[int, dict[int, dict[str, int]]], list[dict[str, Any]]]:
    available = set(logs_by_season)
    minutes: dict[int, dict[int, dict[str, int]]] = {season: {} for season in available}
    ignored: list[dict[str, Any]] = []

    for season, games in logs_by_season.items():
        for game in games:
            if not is_counting_game(game.game_type):
                ignored.append(
                    {
                        "season": season,
                        "date": game.date,
                        "position": game.position,
                        "minutes": game.minutes,
                        "game_type": game.game_type,
                        "reason": "non-counting game type",
                    }
                )
                continue

            target_season = season
            week = get_game_week(game.date, season)
            if week is None:
                prev_week = get_game_week(game.date, season - 1)
                if prev_week is not None and (season - 1) in available:
                    target_season = season - 1
                    week = prev_week
                else:
                    ignored.append(
                        {
                            "season": season,
                            "date": game.date,
                            "position": game.position,
                            "minutes": game.minutes,
                            "game_type": game.game_type,
                            "reason": "outside selected season windows",
                        }
                    )
                    continue

            pos = (game.position or "").strip().upper()
            if pos not in POSITIONS:
                ignored.append(
                    {
                        "season": season,
                        "date": game.date,
                        "position": game.position,
                        "minutes": game.minutes,
                        "game_type": game.game_type,
                        "reason": "unknown game-log position",
                    }
                )
                continue
            week_map = minutes.setdefault(target_season, {}).setdefault(week, {})
            week_map[pos] = week_map.get(pos, 0) + game.minutes

    return minutes, ignored


def selected_training_position(position_minutes: dict[str, int]) -> str | None:
    candidates = [
        (pos, mins)
        for pos, mins in position_minutes.items()
        if pos in POSITIONS and mins >= TRAINING_THRESHOLD_MINUTES
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (-item[1], TIE_PRIORITY[item[0]]))[0][0]


def skill_display_rows(skills: dict[str, float]) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = []
    for left, right in SKILL_DISPLAY_ORDER:
        row: list[dict[str, Any]] = []
        for skill in (left, right):
            value = float(skills.get(skill, 0.0))
            rounded = max(1, round(value))
            label, color = SKILL_LABELS.get(rounded, ("legendary", "#0EB366") if rounded >= 20 else ("", "#1f2933"))
            row.append(
                {
                    "skill": skill,
                    "value": value,
                    "rounded": rounded,
                    "label": label,
                    "color": color,
                }
            )
        rows.append(row)
    return rows


def _actions_for_position(position: str, age: int) -> list[TrainingAction]:
    if position in {"SF", "PF"}:
        if age in {18, 19}:
            return [TrainingAction("DR for 34", age)]
        if age in {20, 21}:
            return [TrainingAction("DR for 34", age, 0.5), TrainingAction("JS for 34", age, 0.5)]
    if position == "PG":
        if age == 18:
            return [TrainingAction("DR for 12", age)]
        if age in {19, 20}:
            return [TrainingAction("OD for 1", age)]
        if age == 21:
            return [TrainingAction("OD for 1", age, 0.5), TrainingAction("PA for 1", age, 0.5)]
    if position == "SG":
        if age in {18, 19}:
            return [TrainingAction("DR for 12", age)]
        if age in {20, 21}:
            return [TrainingAction("JR for 2", age)]
    if position == "C":
        if age == 18:
            return [TrainingAction("ID for 5", age)]
        if age == 19:
            return [TrainingAction("IS for 5", age)]
    return []


def _assign_center_20_21(count: int) -> list[str]:
    base = count // 3
    remainder = count % 3
    names = ["ID for 5"] * base + ["IS for 5"] * base + ["RB for 45"] * base
    if remainder >= 1:
        names.append("ID for 5")
    if remainder >= 2:
        names.append("IS for 5")
    return names


def infer_training(
    minutes_by_season_week_position: dict[int, dict[int, dict[str, int]]],
    *,
    current_age: int | None,
    current_season: int,
) -> tuple[list[InferredAction], list[dict[str, Any]], dict[str, int]]:
    weekly_rows: list[dict[str, Any]] = []
    c_deferred_indexes: list[int] = []
    counts_by_position = {pos: 0 for pos in POSITIONS}

    for season in sorted(minutes_by_season_week_position):
        age = age_for_season(current_age, current_season, season)
        for week in sorted(minutes_by_season_week_position[season]):
            pos_minutes = minutes_by_season_week_position[season][week]
            selected = selected_training_position(pos_minutes)
            if selected:
                counts_by_position[selected] += 1

            row = {
                "season": season,
                "week": week,
                "age": age,
                "position_minutes": {pos: pos_minutes.get(pos, 0) for pos in POSITIONS},
                "selected_position": selected,
                "training": ".",
                "actions": [],
            }
            if selected and age is not None:
                if selected == "C" and age in {20, 21}:
                    c_deferred_indexes.append(len(weekly_rows))
                else:
                    row["actions"] = _actions_for_position(selected, age)
            weekly_rows.append(row)

    center_assignments = _assign_center_20_21(len(c_deferred_indexes))
    for row_index, training_name in zip(c_deferred_indexes, center_assignments):
        age = weekly_rows[row_index]["age"]
        weekly_rows[row_index]["actions"] = [TrainingAction(training_name, int(age))]

    inferred: list[InferredAction] = []
    for row in weekly_rows:
        actions = row["actions"]
        if actions:
            row["training"] = " + ".join(
                action.name if action.fraction == 1 else f"{action.fraction:g} {action.name}"
                for action in actions
            )
            for action in actions:
                inferred.append(InferredAction(row["season"], row["week"], action))

    return inferred, weekly_rows, counts_by_position


def estimate_player(
    roster_player: RosterPlayer,
    metadata: PlayerMetadata,
    logs_by_season: dict[int, list[GameLogEntry]],
    *,
    current_season: int,
) -> dict[str, Any]:
    warnings: list[str] = []
    if metadata.potential is None:
        warnings.append(f"Potential missing; defaulted to {DEFAULT_POTENTIAL}.")
    if metadata.salary is None:
        warnings.append("Salary missing; profile is not salary-anchored.")
    if metadata.age is None:
        warnings.append("Age missing; used last four seasons as training window.")

    height_cm = nearest_height_cm(bb_height_to_cm(metadata.height))
    potential = metadata.potential if metadata.potential is not None else DEFAULT_POTENTIAL
    best_pos = normalize_position(metadata.best_position)
    base_profile = list(POSITION_PRESETS[best_pos])

    minutes_map, ignored_games = aggregate_minutes(logs_by_season)
    inferred, weekly_rows, counts_by_position = infer_training(
        minutes_map,
        current_age=metadata.age,
        current_season=current_season,
    )
    if not weekly_rows:
        warnings.append("No club-game minutes found in selected age window.")

    pre_actions = [item.action for item in inferred if item.season < current_season]
    current_actions = [item.action for item in inferred if item.season == current_season]
    pre_profile = replay_training(base_profile, pre_actions, height_cm=height_cm, potential=potential)
    start_profile, modeled_current_salary, residual = solve_start_profile(
        pre_profile,
        current_actions,
        current_salary=metadata.salary,
        best_pos=best_pos,
        height_cm=height_cm,
        potential=potential,
    )

    if residual is not None and metadata.salary:
        if abs(residual) > max(250, metadata.salary * 0.1):
            warnings.append(f"Poor salary fit: residual {residual:+.0f}.")

    current_season_training = [
        {"week": row["week"], "training": row["training"]}
        for row in weekly_rows
        if row["season"] == current_season and row["training"] != "."
    ]
    training_summary_by_age: list[dict[str, Any]] = []
    ages = sorted({row["age"] for row in weekly_rows if row["age"] is not None})
    for age in ages:
        age_rows = [row for row in weekly_rows if row["age"] == age]
        counts = {pos: 0 for pos in POSITIONS}
        trainings: list[dict[str, Any]] = []
        for row in age_rows:
            selected = row.get("selected_position")
            if selected in counts:
                counts[selected] += 1
            if row["training"] != ".":
                trainings.append({"season": row["season"], "week": row["week"], "training": row["training"]})
        training_summary_by_age.append(
            {
                "age": age,
                "weeks": len(age_rows),
                "counts_by_position": counts,
                "trainings": trainings,
            }
        )
    start_skills = profile_dict(start_profile)

    return {
        "player_id": roster_player.player_id,
        "name": roster_player.name,
        "age": metadata.age,
        "height": metadata.height,
        "height_cm_used": height_cm,
        "salary": metadata.salary,
        "best_position": best_pos,
        "potential": potential,
        "game_shape": metadata.game_shape,
        "dmi": metadata.dmi,
        "estimated_start_skills": start_skills,
        "estimated_start_skill_rows": skill_display_rows(start_skills),
        "estimated_current_salary": round(modeled_current_salary) if modeled_current_salary is not None else None,
        "salary_residual": round(residual) if residual is not None else None,
        "start_best_position_salary": round(listed_salary(start_profile, best_pos)),
        "training_counts_by_position": counts_by_position,
        "training_summary_by_age": training_summary_by_age,
        "current_season_training": current_season_training,
        "weekly_rows": weekly_rows,
        "ignored_games": ignored_games,
        "warnings": warnings,
    }
