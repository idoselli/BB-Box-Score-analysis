"""Public ordered play facts. Never infer defenders from player2 or replay lineups."""
from __future__ import annotations

from collections import Counter
from typing import Any

from .api import V1ApiError, segment

MADE = {"ShotMade", "ShotMadeAssist", "Goaltending"}
FOUL_MISSES = {"ShotMissedFoul", "ShotMissedAssistFoul"}
THREES = {"GenericThree", "StraightOnThree", "WingThree", "CornerThree", "VeryLong", "HalfCourtShot"}
ZERO_UUID = "00000000-0000-0000-0000-000000000000"


def read_events(client, match_id: str) -> list[dict[str, Any]]:
    cursor = 0
    rows = []
    seen = set()
    while True:
        if cursor in seen or len(rows) >= 20000:
            raise V1ApiError(502, "InvalidResponse", "Event pagination did not terminate.")
        seen.add(cursor)
        page = client.get(f"/matches/{segment(match_id)}/events", {"cursor": cursor})
        batch = page.get("events")
        if not isinstance(batch, list) or any(not isinstance(row, dict) for row in batch):
            raise V1ApiError(502, "InvalidResponse", "Invalid event page.")
        rows.extend(batch)
        next_cursor = page.get("nextCursor")
        if next_cursor is None:
            total = page.get("totalEvents")
            indices = [row.get("sequenceIndex") for row in rows]
            if ((total is not None and total != len(rows)) or
                    any(not isinstance(index, int) for index in indices) or
                    indices != sorted(set(indices))):
                raise V1ApiError(502, "InvalidResponse", "Event feed is incomplete or out of order.")
            return rows
        if not isinstance(next_cursor, int) or next_cursor <= cursor:
            raise V1ApiError(502, "InvalidResponse", "Invalid event cursor.")
        cursor = next_cursor


def analyze_events(match_id: str, rows: list[dict[str, Any]], match: dict, box: dict, team_id: str) -> dict:
    players = {}
    for side in box.get("teams", []):
        for line in side.get("players", []):
            p = line.get("player") or {}
            players[p.get("id")] = {"teamId": side.get("teamId"), "name": " ".join(filter(None, [p.get("firstName"), p.get("lastName")]))}
    types = Counter()
    shots = []
    matchups = {}
    previous_home = previous_away = 0
    for raw in rows:
        e = dict(raw, matchId=match_id)
        for key, label in (("player1Id", "player1Name"), ("player2Id", "player2Name"), ("primaryDefenderId", "defenderName")):
            e[label] = players.get(e.get(key), {}).get("name") or (e.get(key) if e.get(key) != ZERO_UUID else "")
        e["playerTeamId"] = players.get(e.get("player1Id"), {}).get("teamId")
        e["clutch"] = (e.get("period", 0) >= 4 and 0 <= e.get("clock", -1) <= 300 and abs(previous_home - previous_away) <= 5)
        previous_home, previous_away = e.get("homePoints", previous_home), e.get("awayPoints", previous_away)
        if e.get("eventType") == "Shot" and not e.get("isCommentary"):
            e["made"] = e.get("shotResult") in MADE
            e["countsAsAttempt"] = e.get("shotResult") not in FOUL_MISSES | {None, "None"}
            e["points"] = (3 if e.get("shotType") in THREES else 2) if e["made"] else 0
            shots.append(e)
            defender = e.get("primaryDefenderId")
            if e["countsAsAttempt"] and defender and defender != ZERO_UUID:
                key = (e.get("player1Id"), defender)
                group = matchups.setdefault(key, {"shooterId": key[0], "shooter": e["player1Name"], "defenderId": defender, "defender": e["defenderName"], "attempts": 0, "made": 0, "points": 0})
                group["attempts"] += 1
                group["made"] += int(e["made"])
                group["points"] += e["points"]
        types[str(e.get("eventType"))] += 1
        raw.update(e)
    return {"matchId": match_id, "events": rows, "shots": shots,
            "matchups": list(matchups.values()), "eventTypes": dict(types),
            "ownShots": [e for e in shots if e["playerTeamId"] == team_id],
            "defenderCoverage": {"known": sum(bool(e.get("primaryDefenderId") and e["primaryDefenderId"] != ZERO_UUID) for e in shots), "shots": len(shots)}}
