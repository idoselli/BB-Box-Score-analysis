"""Clearly labeled, deterministic sample data for public beta previews."""

from __future__ import annotations

import json
import random
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5


ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = ROOT / "data" / "v1" / "demo"
LEGACY_COUNTRIES = ROOT / "data" / "u21-tracker" / "s73" / "meta.json"
FIRST = ("Alex", "Ben", "Chris", "Daniel", "Eli", "Finn", "Gabriel", "Hugo", "Ivan", "Jonah", "Kai", "Luca")
LAST = ("Rivera", "Morgan", "Chen", "Silva", "Keller", "Novak", "Patel", "Brown", "Rossi", "Lee", "Carter", "Meyer")
POSITIONS = ("PointGuard", "ShootingGuard", "SmallForward", "PowerForward", "Center")


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def generate() -> None:
    """Use names of legacy countries, but no beta API response or player data."""
    countries = json.loads(LEGACY_COUNTRIES.read_text(encoding="utf-8"))["countries"]
    rng = random.Random(21021)
    weeks = {1: [], 2: []}
    meta_countries = []
    for index, country in enumerate(countries):
        country_id = f"DEMO-{index + 1:02d}"
        team_id = str(uuid5(NAMESPACE_URL, f"bbinsider-demo-team-{index}"))
        meta_countries.append({"name": country["name"], "countryId": country_id, "teamId": team_id})
        roster = []
        for player_index in range(12):
            dmi = rng.randrange(8_000, 95_000, 500)
            player_id = str(uuid5(NAMESPACE_URL, f"bbinsider-demo-player-{index}-{player_index}"))
            roster.append({
                "playerId": player_id,
                "name": f"{FIRST[player_index]} {LAST[(index + player_index) % len(LAST)]}",
                "position": POSITIONS[player_index % len(POSITIONS)],
                "dmi": dmi,
                "gameShape": rng.randint(5, 9),
                "salary": rng.randrange(2_000, 22_000, 250),
                "potential": rng.randint(4, 10),
            })
        common = {"name": country["name"], "countryId": country_id, "teamId": team_id, "teamName": f"{country['name']} U21 (demo)"}
        weeks[2].append({**common, "players": roster})
        weeks[1].append({**common, "players": [{**player, "dmi": round(player["dmi"] * 0.9), "gameShape": None, "salary": None, "potential": None} for player in roster]})
    directory = DEMO_ROOT / "u21-tracker" / "s1"
    _write(directory / "w1.json", {"world": "v1-demo", "season": 1, "week": 1, "syntheticDmi": True, "demo": True, "countries": weeks[1]})
    _write(directory / "w2.json", {"world": "v1-demo", "season": 1, "week": 2, "demo": True, "countries": weeks[2]})
    _write(directory / "meta.json", {"world": "v1-demo", "season": 1, "weeks": [1, 2], "syntheticWeeks": [1], "demo": True, "updatedAt": "Demo data", "countries": meta_countries})
    market_players = {}
    for index in range(13):
        player_id = str(uuid5(NAMESPACE_URL, f"bbinsider-demo-market-{index}"))
        market_players[player_id] = {
            "playerId": player_id,
            "name": f"{FIRST[index % len(FIRST)]} {LAST[(index + 3) % len(LAST)]}",
            "countryId": "DEMO",
            "age": 20 + index % 10,
            "position": POSITIONS[index % len(POSITIONS)],
            "salary": 400_000 - index * 21_000,
            "dmi": 1_100_000 - index * 54_000,
            "potential": 5 + index % 5,
            "auctionId": str(uuid5(NAMESPACE_URL, f"bbinsider-demo-auction-{index}")),
            "currentPrice": 600_000 - index * 25_000,
            "observedAt": "2026-09-29T12:00:00Z",
            "skillsVisibleUntil": "2026-10-06T12:00:00Z",
            "lastKnownSkills": {"jumpShot": {"level": 12 + index % 6, "change": "Unchanged"}, "outsideDefense": {"level": 10 + index % 7, "change": "Unchanged"}},
        }
    _write(DEMO_ROOT / "market" / "players.json", {"world": "v1-demo", "demo": True, "players": market_players, "lastSuccess": None})


if __name__ == "__main__":
    generate()
