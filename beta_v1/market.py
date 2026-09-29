"""Salary-ranked market snapshots for the owner-run, exception-gated collector."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .api import V1ApiError, V1Client, segment
from .tracker import ROOT, _pause, _read, _write


MARKET_PATH = ROOT / "data" / "v1" / "market" / "players.json"


def _date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def collect(client: V1Client, *, now: datetime | None = None, path: Path = MARKET_PATH) -> tuple[bool, dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    archive = _read(path) or {"world": "v1", "players": {}, "reveals": []}
    previous = archive.get("lastSuccess")
    if previous and now - _date(previous) < timedelta(hours=72):
        return False, archive
    reveals = [stamp for stamp in archive.get("reveals", []) if now - _date(stamp) < timedelta(days=30)]
    recent_day = sum(now - _date(stamp) < timedelta(days=1) for stamp in reveals)
    budget = min(13, 20 - recent_day, 150 - len(reveals))
    listings = []
    for offset in range(0, 150, 30):
        page = client.get("/market/players", {"OrderBy": "Salary", "Sort": "Desc", "Offset": offset, "Limit": 30})
        batch = page.get("players", [])
        listings.extend(batch)
        if len(batch) < 30:
            break
        _pause()
    records = archive.setdefault("players", {})
    for listing in listings:
        if budget <= 0:
            break
        player = listing.get("player") or {}
        player_id = str(player.get("id") or "")
        auction_id = str(listing.get("auctionId") or "")
        if not player_id or not auction_id or _date(listing["endsAt"]) <= now:
            continue
        if records.get(player_id, {}).get("auctionId") == auction_id:
            continue
        _pause()
        try:
            auction = client.get(f"/market/players/{segment(player_id)}/auction")
        except V1ApiError as exc:
            if exc.status == 429 and exc.code == "PublicApiListedSkillsExceeded":
                break
            if exc.status in (403, 404):
                continue
            raise
        skills = auction.get("skills")
        if not auction.get("isOpen") or not skills:
            continue
        records[player_id] = {
            "playerId": player_id,
            "name": " ".join(part for part in (player.get("firstName"), player.get("lastName")) if part),
            "countryId": player.get("countryId"),
            "age": player.get("age"),
            "position": player.get("bestPosition"),
            "salary": player.get("salary"),
            "dmi": player.get("dmi"),
            "potential": player.get("potential"),
            "auctionId": auction_id,
            "currentPrice": auction.get("currentPrice"),
            "observedAt": now.isoformat(),
            "skillsVisibleUntil": auction.get("skillsVisibleUntil"),
            "lastKnownSkills": skills,
        }
        reveals.append(now.isoformat())
        budget -= 1
        # A later API error must not lose skill reveals already spent this run.
        archive["reveals"] = reveals
        _write(path, archive)
    archive["reveals"] = reveals
    archive["lastSuccess"] = now.isoformat()
    archive["collector"] = "salary-descending; current auctions only; maximum 13 new reveals per run"
    _write(path, archive)
    return True, archive
