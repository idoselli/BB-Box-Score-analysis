"""All new-world pages and APIs live below /beta."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any
from uuid import UUID

from flask import Blueprint, abort, jsonify, make_response, redirect, render_template, request, url_for

from . import auth, demo, market, reports, tracker
from .api import V1ApiError, V1Client, segment


beta_bp = Blueprint("beta_v1", __name__, url_prefix="/beta", template_folder="templates")


def _publication_enabled() -> bool:
    return os.environ.get("BB_V1_EXCEPTION_APPROVED") == "true"


def _tracker_root() -> Path:
    return tracker.TRACKER_ROOT if _publication_enabled() and tracker.seasons_available() else demo.DEMO_ROOT / "u21-tracker"


def _market_path() -> Path:
    return market.MARKET_PATH if _publication_enabled() and market.MARKET_PATH.exists() else demo.DEMO_ROOT / "market" / "players.json"


def _connection(required: set[str] | None = None) -> tuple[V1Client | None, dict[str, Any] | None, str]:
    try:
        pair = auth.current_session()
    except Exception:
        return None, None, "Beta sign-in is temporarily unavailable."
    if not pair:
        return None, None, "Sign in with your API token on the beta home page to use this feature."
    client, record = pair
    granted = set(record.get("scopes", []))
    if required and not required <= granted:
        return None, record, "This account needs a token or OAuth grant with the required access scopes."
    return client, record, ""


def _api_error(exc: Exception) -> tuple[str, int]:
    if isinstance(exc, V1ApiError):
        if exc.status == 429 and exc.reset_at:
            return f"API limit reached. Try again after the reset at Unix time {exc.reset_at}.", 429
        return str(exc), exc.status if 400 <= exc.status < 600 else 502
    return str(exc), 400


@beta_bp.get("/")
def home():
    return _home_response()


def _home_response(error: str = ""):
    _, record, _ = _connection()
    login_csrf = secrets.token_urlsafe(32)
    response = make_response(render_template("beta/home.html", connected=record is not None, me=(record or {}).get("me", {}), csrf=(record or {}).get("csrf", ""), configured=auth.configured(), token_signin_available=auth.token_signin_available(), login_csrf=login_csrf, error=error))
    response.set_cookie("bb_beta_login_csrf", login_csrf, max_age=600, path="/beta", httponly=True, secure=auth.cookie_secure(), samesite="Strict")
    return response


@beta_bp.post("/token/sign-in")
def token_sign_in():
    cookie_csrf = request.cookies.get("bb_beta_login_csrf", "")
    form_csrf = request.form.get("login_csrf", "")
    if not cookie_csrf or not secrets.compare_digest(cookie_csrf, form_csrf):
        abort(403)
    try:
        old_sid = auth.sid_from_request()
        sid, _ = auth.sign_in_with_token(request.form.get("api_token", ""))
    except (RuntimeError, ValueError, V1ApiError) as exc:
        message = "BuzzerBeater rejected this API token." if isinstance(exc, V1ApiError) and exc.status in {401, 403} else str(exc)
        return _home_response(message), 400
    response = make_response(redirect(url_for("beta_v1.home")))
    if old_sid and old_sid != sid:
        auth.delete_session(old_sid)
    response.set_cookie("bb_beta_sid", sid, max_age=86400, path="/beta", httponly=True, secure=auth.cookie_secure(), samesite="Lax")
    response.delete_cookie("bb_beta_login_csrf", path="/beta")
    return response


@beta_bp.after_request
def no_store_beta(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@beta_bp.get("/oauth/start")
def oauth_start():
    feature = request.args.get("feature", "public")
    try:
        url, state = auth.start_authorization(feature)
    except (RuntimeError, ValueError) as exc:
        return render_template("beta/message.html", title="Sign-in unavailable", message=str(exc)), 503
    response = make_response(redirect(url))
    response.set_cookie("bb_beta_oauth_state", state, max_age=600, path="/beta", httponly=True, secure=auth.cookie_secure(), samesite="Lax")
    return response


@beta_bp.get("/oauth/callback")
def oauth_callback():
    state = request.args.get("state", "")
    if not state or state != request.cookies.get("bb_beta_oauth_state"):
        abort(400, "The sign-in state did not match this browser.")
    if request.args.get("error"):
        return render_template("beta/message.html", title="Sign-in cancelled", message="BuzzerBeater did not grant access."), 403
    code = request.args.get("code", "")
    if not code:
        abort(400, "The sign-in response had no code.")
    try:
        old_sid = auth.sid_from_request()
        sid, _, feature = auth.exchange_code(code, state)
    except (ValueError, V1ApiError) as exc:
        return render_template("beta/message.html", title="Sign-in failed", message=str(exc)), 400
    target = {"market": "beta_v1.market_page", "training": "beta_v1.training_page"}.get(feature, "beta_v1.home")
    response = make_response(redirect(url_for(target)))
    if old_sid and old_sid != sid:
        auth.delete_session(old_sid)
    response.set_cookie("bb_beta_sid", sid, max_age=90 * 86400, path="/beta", httponly=True, secure=auth.cookie_secure(), samesite="Lax")
    response.delete_cookie("bb_beta_oauth_state", path="/beta")
    return response


@beta_bp.post("/oauth/logout")
def oauth_logout():
    _, record, _ = _connection()
    if record:
        if request.form.get("csrf") != record.get("csrf"):
            abort(403)
        auth.revoke(record)
    response = make_response(redirect(url_for("beta_v1.home")))
    response.delete_cookie("bb_beta_sid", path="/beta")
    return response


@beta_bp.get("/u21-tracker")
def tracker_page():
    root = _tracker_root()
    seasons = tracker.seasons_available(root)
    try:
        season = int(request.args.get("season", seasons[0] if seasons else 0))
    except ValueError:
        season = 0
    meta = tracker._read(root / f"s{season}" / "meta.json") if season else None
    country_id = request.args.get("countryId") or ((meta or {}).get("countries") or [{}])[0].get("countryId", "")
    data = tracker.series(season, country_id, root=root) if meta and country_id else None
    return render_template("beta/tracker.html", seasons=seasons, season=season, meta=meta, country_id=country_id, data=data, publication_enabled=_publication_enabled())


@beta_bp.get("/api/u21-tracker")
def tracker_api():
    root = _tracker_root()
    try:
        season = int(request.args.get("season", ""))
    except ValueError:
        return jsonify({"error": "Season must be a number."}), 400
    meta = tracker._read(root / f"s{season}" / "meta.json")
    if not meta:
        return jsonify({"error": "No beta snapshot for that season."}), 404
    country_id = request.args.get("countryId")
    return jsonify(tracker.series(season, country_id, root=root) if country_id else meta)


@beta_bp.route("/multi-match", methods=["GET", "POST"])
def multi_match_page():
    client, record, connection_message = _connection({"Public"})
    report = None
    error = ""
    fields = {key: request.form.get(key, "") for key in ("match_ids", "team_id", "schedule_team_id", "season", "count", "national_country_id", "national_other_code", "national_kind")}
    national_choices = (tracker._read(tracker.TRACKER_ROOT / "team-map.json") or {}).get("teams", [])
    if request.method == "POST":
        if not client:
            error = connection_message
        else:
            try:
                season = int(fields["season"]) if fields["season"].strip() else None
                selected_team = fields["team_id"].strip()
                country_code = fields["national_other_code"].strip().upper() or fields["national_country_id"].strip()
                if country_code:
                    desired_kind = fields["national_kind"] or "JuniorNationalTeam"
                    if desired_kind not in {"JuniorNationalTeam", "SeniorNationalTeam"}:
                        raise ValueError("Choose a valid national-team level.")
                    national_teams = client.get(f"/countries/{segment(country_code)}/national-teams").get("teams", [])
                    national = next((item for item in national_teams if item.get("kind") == desired_kind), None)
                    if not national:
                        raise ValueError("No national team of that level was found for this country code.")
                    source_team = str(national["id"])
                    ids = reports.schedule_ids(client, source_team, season, int(fields["count"] or "10"))
                    selected_team = selected_team or source_team
                elif fields["schedule_team_id"].strip():
                    source_team = fields["schedule_team_id"].strip()
                    ids = reports.schedule_ids(client, source_team, season, int(fields["count"] or "10"))
                    selected_team = selected_team or source_team
                else:
                    ids = reports.parse_ids(fields["match_ids"])
                report = reports.build_report(client, ids, selected_team)
            except Exception as exc:
                error, _ = _api_error(exc)
    return render_template("beta/multi.html", report=report, error=error, fields=fields, national_choices=national_choices, connected=client is not None, connection_message=connection_message)


@beta_bp.route("/national-training", methods=["GET", "POST"])
def training_page():
    client, record, connection_message = _connection({"Public"})
    data = None
    error = ""
    teams = (record or {}).get("me", {}).get("teams", [])
    team_id = request.values.get("team_id", "")
    needed_feature = "training"
    if client and team_id:
        team = next((item for item in teams if item.get("id") == team_id), None)
        if not team:
            error = "Choose a team you manage from the list."
        else:
            try:
                if team["kind"] in {"JuniorNationalTeam", "SeniorNationalTeam"}:
                    needed_feature = "national"
                    if "National" not in record.get("scopes", []):
                        error = "Allow National access to view the squad's private training history."
                    else:
                        data = {"team": team, "roster": client.get(f"/national-teams/{segment(team_id)}/roster"), "history": client.get(f"/national-teams/{segment(team_id)}/training/history", {"limit": 30})}
                elif team["kind"] == "ManagedTeam":
                    if "Team" not in record.get("scopes", []):
                        error = "Allow Team access to view your club's training history."
                    else:
                        data = {"team": team, "roster": client.get(f"/teams/{segment(team_id)}/roster"), "history": client.get(f"/teams/{segment(team_id)}/training/history", {"limit": 30})}
                else:
                    error = "This team type has no training endpoint."
            except Exception as exc:
                error, _ = _api_error(exc)
    return render_template("beta/training.html", data=data, error=error, teams=teams, team_id=team_id, needed_feature=needed_feature, connected=client is not None, connection_message=connection_message)


@beta_bp.route("/market", methods=["GET", "POST"])
def market_page():
    client, record, connection_message = _connection({"Public", "Market"})
    error = ""
    listings: list[dict[str, Any]] = []
    if client and request.method == "POST":
        try:
            params: dict[str, Any] = {"OrderBy": "Salary", "Sort": "Desc", "Offset": 0, "Limit": 30}
            if request.form.get("min_salary", "").strip():
                params["MinSalary"] = max(0, int(request.form["min_salary"]))
            listings = client.get("/market/players", params).get("players", [])
        except Exception as exc:
            error, _ = _api_error(exc)
    archive = market._read(_market_path()) or {}
    records = sorted((archive.get("players") or {}).values(), key=lambda row: -(row.get("salary") or 0))
    return render_template("beta/market.html", listings=listings, archive=records[:100], archive_count=len(records), archive_enabled=_publication_enabled(), archive_demo=bool(archive.get("demo")), error=error, connected=client is not None, connection_message=connection_message)


@beta_bp.get("/market/<player_id>")
def market_auction(player_id: str):
    client, _, connection_message = _connection({"Public", "Market"})
    if not client:
        return render_template("beta/message.html", title="Connect Market", message=connection_message, feature="market"), 403
    try:
        UUID(player_id)
        auction = client.get(f"/market/players/{segment(player_id)}/auction")
    except Exception as exc:
        message, status = _api_error(exc)
        return render_template("beta/message.html", title="Auction unavailable", message=message), status
    return render_template("beta/auction.html", auction=auction)


@beta_bp.get("/api/market/archive")
def market_archive_api():
    archive = market._read(_market_path())
    if not archive:
        return jsonify({"error": "No beta market archive yet."}), 404
    return jsonify(archive)


@beta_bp.get("/market/archive/<player_id>")
def market_archive_player(player_id: str):
    try:
        UUID(player_id)
    except ValueError:
        abort(404)
    archive = market._read(_market_path()) or {}
    player = (archive.get("players") or {}).get(player_id)
    if not player:
        abort(404)
    return render_template("beta/archive_player.html", player=player, demo=bool(archive.get("demo")))
