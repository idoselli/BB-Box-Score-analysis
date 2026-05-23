from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re
from typing import Any
from urllib.parse import urljoin

import requests


BB_BASE = "https://buzzerbeater.com"
BB_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

POSITION_LABELS = {
    "pg": "PG",
    "point guard": "PG",
    "פג": "PG",
    "רכז": "PG",
    "sg": "SG",
    "shooting guard": "SG",
    "שג": "SG",
    "קלע": "SG",
    "קלעי": "SG",
    "sf": "SF",
    "small forward": "SF",
    "ספ": "SF",
    "סמול פורוורד": "SF",
    "פורוורד קטן": "SF",
    "pf": "PF",
    "power forward": "PF",
    "פפ": "PF",
    "פאוור פורוורד": "PF",
    "פורוורד גדול": "PF",
    "c": "C",
    "center": "C",
    "centre": "C",
    "ס": "C",
    "סנטר": "C",
}


@dataclass(frozen=True)
class RosterPlayer:
    player_id: int
    name: str


@dataclass(frozen=True)
class GameLogEntry:
    date: str
    position: str
    minutes: int
    game_type: str


def _hidden_field(html: str, name: str) -> str:
    patterns = [
        rf'name=["\']{re.escape(name)}["\'][^>]*value=["\']([^"\']*)["\']',
        rf'value=["\']([^"\']*)["\'][^>]*name=["\']{re.escape(name)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.I)
        if match:
            return unescape(match.group(1))
    return ""


def _plain_text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ")).strip()


def _parse_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_position_cell(cell_html: str) -> str:
    candidates = [_plain_text(cell_html)]
    candidates.extend(
        unescape(match.group(1))
        for match in re.finditer(r'(?:alt|title)=["\']([^"\']+)["\']', cell_html, re.I)
    )
    candidates.extend(
        unescape(match.group(1))
        for match in re.finditer(r'(?:src|class)=["\']([^"\']+)["\']', cell_html, re.I)
    )

    for candidate in candidates:
        cleaned = " ".join(re.sub(r"[_\-/\.]+", " ", candidate).strip().casefold().split())
        for label, code in POSITION_LABELS.items():
            if re.search(rf"(^|\b){re.escape(label)}(\b|$)", cleaned):
                return code
    return ""


def _selected_season_from_html(html: str) -> int | None:
    select = re.search(
        r"<select[^>]*(?:id|name)=['\"][^'\"]*ddlSeasons[^'\"]*['\"][^>]*>([\s\S]*?)</select>",
        html,
        re.I,
    )
    if not select:
        return None
    selected = re.search(r"<option[^>]*selected[^>]*value=['\"](\d+)['\"]", select.group(1), re.I)
    if not selected:
        selected = re.search(r"<option[^>]*value=['\"](\d+)['\"][^>]*selected", select.group(1), re.I)
    if not selected:
        return None
    return int(selected.group(1))


def parse_game_log_html(html: str) -> list[GameLogEntry]:
    rows = re.findall(r"<tr[^>]*>[\s\S]*?</tr>", html, re.I)
    games: list[GameLogEntry] = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>([\s\S]*?)</td>", row, re.I)
        if len(cells) < 14:
            continue
        cols = [_plain_text(cell) for cell in cells]
        if not re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", cols[0] or ""):
            continue

        has_rating = len(cells) >= 16
        games.append(
            GameLogEntry(
                date=cols[0],
                position=parse_position_cell(cells[1]),
                minutes=_parse_int(cols[2]),
                game_type=cols[15] if has_rating else cols[14],
            )
        )
    return games


class BBSiteClient:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": BB_UA, "Accept": "text/html,*/*;q=0.9"})

    def login(self) -> None:
        login_url = f"{BB_BASE}/login.aspx"
        response = self.session.get(login_url, timeout=30)
        response.raise_for_status()
        html = response.text
        viewstate = _hidden_field(html, "__VIEWSTATE")
        if not viewstate:
            raise ValueError("Could not read BB login form state.")

        payload = {
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            "__VIEWSTATE": viewstate,
            "__VIEWSTATEGENERATOR": _hidden_field(html, "__VIEWSTATEGENERATOR"),
            "__EVENTVALIDATION": _hidden_field(html, "__EVENTVALIDATION"),
            "ctl00$cphContent$txtUserName": self.username,
            "ctl00$cphContent$txtPassword": self.password,
            "ctl00$cphContent$btnLoginUser": "Login",
        }
        post = self.session.post(login_url, data=payload, headers={"Referer": login_url}, timeout=30)
        post.raise_for_status()
        post_text = _plain_text(post.text)
        if "too many failed logins" in post_text.casefold():
            raise ValueError("BB site login is temporarily locked after too many failed attempts.")
        if "cphContent_txtUserName" in post.text or re.search(r"\bLogin Username or Email\b", post_text, re.I):
            raise ValueError("BB site login failed. Check username/password.")

    def fetch_u21_roster(self, country_id: str | int) -> tuple[str, list[RosterPlayer]]:
        url = f"{BB_BASE}/country/{country_id}/jnt/players.aspx"
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        html = response.text
        self._ensure_not_login_wall(html, "roster page")

        h1 = re.search(r"<h1[^>]*>([^<]+)</h1>", html, re.I)
        team_name = unescape(h1.group(1)).replace("\xa0", " ").strip() if h1 else f"Country {country_id} U21"

        seen: set[int] = set()
        players: list[RosterPlayer] = []
        for match in re.finditer(
            r'href=["\'][^"\']*/player/(\d+)/overview\.aspx["\'][^>]*>([^<]+)</a>',
            html,
            re.I,
        ):
            player_id = int(match.group(1))
            name = unescape(match.group(2)).replace("\xa0", " ").strip()
            if not name or "season average" in name.casefold() or player_id in seen:
                continue
            seen.add(player_id)
            players.append(RosterPlayer(player_id=player_id, name=name))
        return team_name, players

    def fetch_player_game_log(self, player_id: int, season: int) -> list[GameLogEntry]:
        url = f"{BB_BASE}/player/{player_id}/overview.aspx"
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        html = response.text
        self._ensure_not_login_wall(html, f"player {player_id} overview")

        selected = _selected_season_from_html(html)
        if selected == season:
            return parse_game_log_html(html)

        payload: dict[str, Any] = {
            "__EVENTTARGET": "ctl00$cphContent$ddlSeasons",
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            "__VIEWSTATE": _hidden_field(html, "__VIEWSTATE"),
            "__VIEWSTATEGENERATOR": _hidden_field(html, "__VIEWSTATEGENERATOR"),
            "__EVENTVALIDATION": _hidden_field(html, "__EVENTVALIDATION"),
            "ctl00$cphContent$ddlSeasons": str(season),
        }
        post = self.session.post(url, data=payload, headers={"Referer": urljoin(BB_BASE, url)}, timeout=30)
        post.raise_for_status()
        self._ensure_not_login_wall(post.text, f"player {player_id} season {season}")
        returned_season = _selected_season_from_html(post.text)
        if returned_season is not None and returned_season != season:
            raise ValueError(f"BB returned season {returned_season} instead of requested season {season}.")
        return parse_game_log_html(post.text)

    @staticmethod
    def _ensure_not_login_wall(html: str, context: str) -> None:
        text = _plain_text(html)
        if "cphContent_txtUserName" in html or re.search(r"\bLogin Username or Email\b", text, re.I):
            raise ValueError(f"{context} returned a login page.")
        if "Oops! Something went wrong" in text:
            raise ValueError(f"{context} returned a BB error page.")
