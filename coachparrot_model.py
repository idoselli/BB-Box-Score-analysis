from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite, log


SKILLS = ("JS", "JR", "OD", "HA", "DR", "PA", "IS", "ID", "RB", "SB")
POSITIONS = ("PG", "SG", "SF", "PF", "C")

COACH_LEVEL = 7
DEFAULT_POTENTIAL = 8

SALARY_COEFF = {
    "PG": (1.033, 1.038, 1.075, 1.08, 1.04, 1.16, 1.0, 1.0, 1.04, 1.0),
    "SG": (1.125, 1.133, 1.14, 1.0, 1.0, 1.0, 1.0, 1.0, 1.07, 1.0),
    "SF": (1.17, 1.097, 1.06, 1.0, 1.0, 1.0, 1.0, 1.065, 1.099, 1.0),
    "PF": (1.085, 1.0, 1.0, 1.0, 1.0, 1.0, 1.125, 1.115, 1.11, 1.05),
    "C": (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.16, 1.125, 1.12, 1.06),
}
SALARY_MULT = {pos: 300.0 for pos in POSITIONS}
SALARY_NORMAL_A = 0.955792
SALARY_NORMAL_B = 0.029019
SALARY_MONSTER_A = 1.183107
SALARY_MONSTER_B = 0.046917

AGE_FACTOR = {
    18: 1.0,
    19: 0.95,
    20: 0.88,
    21: 0.78,
    22: 0.70,
    23: 0.60,
    24: 0.51,
    25: 0.42,
    26: 0.35,
    27: 0.27,
    28: 0.21,
    29: 0.16,
    30: 0.11,
    31: 0.07,
    32: 0.05,
    33: 0.03,
    34: 0.02,
    35: 0.01,
    36: 0.0,
}
COACH_FACTOR = {7: 1.06, 6: 1.03, 5: 1.0, 4: 0.97, 3: 0.94, 2: 0.91, 1: 0.88}
ELASTIC_BASE = 0.91
CROSS_BASE = 0.925
POTENTIAL_CAP_FACTOR = 1 / 3

TRAINING_WEIGHTS = {
    "DR for 34": (0.2, 0.0, 0.0, 0.4, 0.5, 0.0, 0.2, 0.0, 0.0, 0.0),
    "JS for 34": (0.4, 0.05, 0.0, 0.0, 0.0, 0.0, 0.2, 0.0, 0.0, 0.0),
    "ID for 5": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.5, 0.0, 0.1),
    "IS for 5": (0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.05, 0.0, 0.0),
    "RB for 45": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.05, 0.5, 0.0),
    "DR for 12": (0.4, 0.0, 0.0, 0.4, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0),
    "OD for 1": (0.0, 0.0, 0.5, 0.05, 0.05, 0.0, 0.0, 0.1, 0.0, 0.0),
    "PA for 1": (0.0, 0.0, 0.0, 0.16, 0.16, 0.6, 0.0, 0.0, 0.0, 0.0),
    "JR for 2": (0.2, 0.4, 0.0, 0.05, 0.05, 0.0, 0.0, 0.0, 0.0, 0.0),
}
TRAINING_HEIGHT_COLUMN = {
    "JS for 34": 1,
    "JR for 2": 2,
    "OD for 1": 3,
    "DR for 12": 5,
    "DR for 34": 5,
    "PA for 1": 6,
    "IS for 5": 7,
    "ID for 5": 8,
    "RB for 45": 9,
}
HEIGHT_ROWS_CM = (175, 178, 180, 183, 185, 188, 190, 193, 196, 198, 201, 203, 206, 208, 211, 213, 216, 218, 221, 224, 226, 229)
ELASTIC_MATRIX = (
    (0, 1, 0, 1, 1, 0, 0, 0, 0, 0),
    (1, 0, 0, 1, 1, 0, 0, 0, 0, 0),
    (0, 0, 0, 1, 1, 0, 0, 1, 0, 0),
    (0, 0, 1, 0, 1, 0, 0, 0, 0, 0),
    (1, 0, 0, 1, 0, 0, 0, 0, 0, 0),
    (0, 0, 0, 1, 1, 0, 0, 0, 0, 0),
    (1, 0, 0, 0, 0, 0, 0, 1, 0, 0),
    (0, 0, 0, 0, 0, 0, 1, 0, 0, 1),
    (0, 0, 0, 0, 0, 0, 1, 1, 0, 0),
    (0, 0, 0, 0, 0, 0, 0, 1, 1, 0),
)
ELASTIC_DENOM = (3, 3, 3, 2, 2, 2, 2, 2, 2, 2)

POSITION_PRESETS = {
    "PG": (6, 5, 6, 7, 6, 7, 4, 1, 1, 1),
    "SG": (7, 7, 6, 5, 5, 5, 4, 1, 1, 1),
    "SF": (6, 6, 6, 5, 5, 5, 5, 1, 1, 1),
    "PF": (2, 2, 2, 2, 2, 2, 6, 6, 7, 5),
    "C": (2, 2, 2, 2, 2, 2, 7, 7, 7, 6),
}


@dataclass(frozen=True)
class TrainingAction:
    name: str
    age: int
    fraction: float = 1.0


def normalize_position(position: str | None) -> str:
    value = (position or "").strip().upper()
    return value if value in POSITIONS else "SG"


def normalize_profile(profile: dict[str, float] | list[float] | tuple[float, ...]) -> list[float]:
    if isinstance(profile, dict):
        return [float(profile.get(skill, 0.0)) for skill in SKILLS]
    return [float(value) for value in profile]


def profile_dict(profile: list[float] | tuple[float, ...], digits: int = 2) -> dict[str, float]:
    return {skill: round(float(profile[index]), digits) for index, skill in enumerate(SKILLS)}


def bb_height_to_cm(height: int | None) -> int:
    if not height:
        return 201
    # BBAPI uses inches; CoachParrot uses centimetres.
    if height < 120:
        return round(height * 2.54)
    return int(height)


def nearest_height_cm(height_cm: int) -> int:
    return min(HEIGHT_ROWS_CM, key=lambda value: abs(value - height_cm))


def height_factor(training_name: str, height_cm: int) -> float:
    idx = HEIGHT_ROWS_CM.index(nearest_height_cm(height_cm))
    column = TRAINING_HEIGHT_COLUMN[training_name]
    if column in {1, 5, 6}:
        return 0.9975273768433653
    if column in {2, 3, 4}:
        return 1.5 - 0.05 * idx
    return 0.5 + 0.05 * idx


def virtual_salary(profile: dict[str, float] | list[float] | tuple[float, ...], position: str) -> float:
    values = normalize_profile(profile)
    pos = normalize_position(position)
    return exp(sum(log(SALARY_COEFF[pos][i]) * values[i] for i in range(len(SKILLS)))) * SALARY_MULT[pos]


def listed_salary(profile: dict[str, float] | list[float] | tuple[float, ...], position: str) -> float:
    virtual = virtual_salary(profile, position)
    return virtual * min(
        SALARY_NORMAL_A - SALARY_NORMAL_B * log(virtual),
        SALARY_MONSTER_A - SALARY_MONSTER_B * log(virtual),
    )


def best_position(profile: dict[str, float] | list[float] | tuple[float, ...]) -> str:
    salaries = {pos: virtual_salary(profile, pos) for pos in POSITIONS}
    return max(salaries, key=salaries.get)


def train_week(
    profile: dict[str, float] | list[float] | tuple[float, ...],
    action: TrainingAction,
    *,
    height_cm: int,
    potential: int = DEFAULT_POTENTIAL,
    coach_level: int = COACH_LEVEL,
) -> list[float]:
    values = normalize_profile(profile)
    if action.name not in TRAINING_WEIGHTS or action.fraction <= 0:
        return values

    max_skill = max(values)
    avg_skill = sum(values) / len(values)
    age_multiplier = AGE_FACTOR.get(action.age, 0.0)
    coach_multiplier = COACH_FACTOR.get(coach_level, COACH_FACTOR[COACH_LEVEL])
    h_factor = height_factor(action.name, height_cm)
    out = list(values)

    for i, base_weight in enumerate(TRAINING_WEIGHTS[action.name]):
        if base_weight <= 0:
            continue
        weighted = sum(values[j] * ELASTIC_MATRIX[i][j] for j in range(len(SKILLS)))
        elastic = ELASTIC_BASE ** (values[i] - weighted / ELASTIC_DENOM[i])
        cross = CROSS_BASE ** (values[i] - avg_skill) if values[i] == max_skill else 1.0
        pot = 1.0 if potential >= max_skill else POTENTIAL_CAP_FACTOR
        out[i] += (
            base_weight
            * action.fraction
            * age_multiplier
            * h_factor
            * elastic
            * cross
            * pot
            * coach_multiplier
        )
    return out


def replay_training(
    profile: dict[str, float] | list[float] | tuple[float, ...],
    actions: list[TrainingAction],
    *,
    height_cm: int,
    potential: int = DEFAULT_POTENTIAL,
    coach_level: int = COACH_LEVEL,
) -> list[float]:
    out = normalize_profile(profile)
    for action in actions:
        out = train_week(out, action, height_cm=height_cm, potential=potential, coach_level=coach_level)
    return out


def solve_start_profile(
    pre_current_profile: list[float],
    current_actions: list[TrainingAction],
    *,
    current_salary: int | None,
    best_pos: str,
    height_cm: int,
    potential: int,
) -> tuple[list[float], float | None, float | None]:
    if not current_salary or current_salary <= 0:
        return pre_current_profile, None, None

    pos = normalize_position(best_pos)

    def modeled(offset: float) -> float:
        start = [value + offset for value in pre_current_profile]
        current = replay_training(start, current_actions, height_cm=height_cm, potential=potential)
        return listed_salary(current, pos)

    lo, hi = -8.0, 18.0
    best_offset = 0.0
    best_gap = abs(modeled(0.0) - current_salary)
    for candidate in (lo, hi):
        gap = abs(modeled(candidate) - current_salary)
        if gap < best_gap:
            best_offset, best_gap = candidate, gap

    if modeled(lo) <= current_salary <= modeled(hi):
        for _ in range(64):
            mid = (lo + hi) / 2
            if modeled(mid) < current_salary:
                lo = mid
            else:
                hi = mid
        best_offset = (lo + hi) / 2

    start_profile = [value + best_offset for value in pre_current_profile]
    residual = current_salary - modeled(best_offset)
    if not isfinite(residual):
        residual = None
    return start_profile, modeled(best_offset), residual
