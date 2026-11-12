"""Public play facts plus role/lineup reconstruction validated against box scores."""
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


def analyze_events(match_id: str, rows: list[dict[str, Any]], match: dict, box: dict, team_id: str, player_directory: dict | None = None) -> dict:
    players = dict(player_directory or {})
    for side in box.get("teams", []):
        for line in side.get("players", []):
            p = line.get("player") or {}
            pid = p.get("id")
            if pid not in players:
                players[pid] = {"teamId": side.get("teamId"), "name": " ".join(filter(None, [p.get("firstName"), p.get("lastName")]))}
    types = Counter()
    shots = []
    matchups = {}
    previous_home = previous_away = 0
    from .pbp_catalog import apply_sentence_facts
    from .reconstruction import identities
    role_players = identities(box)
    for raw in rows:
        apply_sentence_facts(raw, role_players)
        e = dict(raw, matchId=match_id)
        for key, label in (("player1Id", "player1Name"), ("player2Id", "player2Name"), ("primaryDefenderId", "defenderName")):
            e[label] = players.get(e.get(key), {}).get("name") or ("Unknown player" if e.get(key) and e.get(key) != ZERO_UUID else "")
        e["playerTeamId"] = next((side.get("teamId") for side in box.get("teams", [])
                                  if any((line.get("player") or {}).get("id") == e.get("player1Id") for line in side.get("players", []))), None)
        if e["playerTeamId"] is None and e.get("teamIndex") in (0, 1):
            e["playerTeamId"] = next((side.get("teamId") for side in match.get("teams", [])
                                      if bool(side.get("isHome")) == (e["teamIndex"] == 0)), None)
        e["helpDefenderName"] = players.get(e.get("helpDefenderId"), {}).get("name") or ("Unknown player" if e.get("helpDefenderId") and e.get("helpDefenderId") != ZERO_UUID else "")
        e["clutch"] = (e.get("period", 0) >= 4 and 0 <= e.get("clock", -1) <= 300 and abs(previous_home - previous_away) <= 5)
        previous_home, previous_away = e.get("homePoints", previous_home), e.get("awayPoints", previous_away)
        if e.get("eventType") == "Shot" and not e.get("isCommentary"):
            e["made"] = e.get("shotResult") in MADE
            e["countsAsAttempt"] = e.get("shotResult") not in FOUL_MISSES | {None, "None"}
            e["points"] = (3 if e.get("shotType") in THREES else 2) if e["made"] else 0
            shots.append(e)
        types[str(e.get("eventType"))] += 1
        raw.update(e)
    from .reconstruction import infer_roles, reconstruct
    from .commentary_roles import describe_shot, describe_event
    infer_roles(rows, box)
    shots = [e for e in rows if e.get("eventType") == "Shot" and not e.get("isCommentary")]
    matchups = {}
    for e in shots:
        defender = e.get("primaryDefenderId") or e.get("inferredDefenderId")
        if defender == ZERO_UUID:
            defender = e.get("inferredDefenderId")
        e["resolvedDefenderId"] = defender
        e["defenderName"] = players.get(defender, {}).get("name") or ("Unknown player" if defender else "")
        e["passerName"] = players.get(e.get("passerId"), {}).get("name") or ""
        e["helpDefenderName"] = players.get(e.get("helpDefenderId") or e.get("inferredHelpDefenderId"), {}).get("name") or ""
        describe_shot(e)
        if defender and e.get("countsAsAttempt"):
            key = (e.get("player1Id"), defender)
            entry = matchups.setdefault(key, {"shooterId":key[0],"shooter":e["player1Name"],"defenderId":defender,
                                               "defender":e["defenderName"],"attempts":0,"made":0,"points":0})
            entry["attempts"] += 1
            entry["made"] += int(e["made"])
            entry["points"] += e["points"]
    for e in rows:
        if e.get('eventType')!='Shot' or e.get('isCommentary'):
            describe_event(e)
    reconstruction = reconstruct(rows, match, box)
    return {"matchId": match_id, "events": rows, "shots": shots,
            "matchups": list(matchups.values()), "eventTypes": dict(types),
            "reconstruction": reconstruction,
            "ownShots": [e for e in shots if e["playerTeamId"] == team_id],
            "defenderCoverage": {"known": sum(bool(e.get("resolvedDefenderId")) for e in shots),
                                "apiKnown":sum(e.get("defenderSource")=="api" for e in shots),
                                "inferred":sum(bool(e.get("inferredDefenderId")) for e in shots),
                                "open":sum(e.get("defenseState")=="open" for e in shots),
                                "unknown":sum(e.get("defenseState")=="unknown" for e in shots),"shots":len(shots)}}
