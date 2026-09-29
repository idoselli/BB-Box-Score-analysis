import json
import re
import tempfile
import unittest
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import web_tool
from beta_v1 import auth, demo, market, reports, tracker
from beta_v1.api import V1ApiError, V1Client


MATCH_ID = "11111111-1111-4111-8111-111111111111"
TEAM_ID = "22222222-2222-4222-8222-222222222222"
OTHER_ID = "33333333-3333-4333-8333-333333333333"
PLAYER_ID = "44444444-4444-4444-8444-444444444444"


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        value = self.responses[path]
        return value(params) if callable(value) else value


class BetaRoutesTests(unittest.TestCase):
    def test_beta_is_separate_from_legacy_routes(self):
        client = web_tool.app.test_client()
        home = client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn(b'/beta/', home.data)
        self.assertIn(b'Multi Match Team Aggregate', home.data)
        for path in ("/beta/", "/beta/u21-tracker", "/beta/multi-match", "/beta/national-training", "/beta/market"):
            self.assertEqual(client.get(path).status_code, 200, path)
        self.assertEqual(client.get("/api/u21-tracker?season=98765").status_code, 404)
        self.assertEqual(client.get("/beta/api/u21-tracker?season=98765").status_code, 404)
        with patch.dict("os.environ", {"BB_V1_EXCEPTION_APPROVED": "false"}):
            archive = client.get("/beta/api/market/archive")
            self.assertEqual(archive.status_code, 200)
            self.assertTrue(archive.json["demo"])
            sample = client.get("/beta/api/u21-tracker?season=1&countryId=DEMO-01")
            self.assertEqual(sample.status_code, 200)
            self.assertTrue(sample.json["demo"])
            self.assertIn(b"simulated", client.get("/beta/u21-tracker").data)
        self.assertIn(b'legacy-beta-theme.css', home.data)
        self.assertIn(b'BuzzerBeater \xc2\xb7 Current tool', home.data)

    def test_demo_player_line_and_illustrative_week(self):
        with patch.dict("os.environ", {"BB_V1_EXCEPTION_APPROVED": "false"}):
            response = web_tool.app.test_client().get("/beta/u21-tracker?season=1&countryId=DEMO-01")
        self.assertIn(b'id="player-filter"', response.data)
        self.assertIn(b"Dashed segments include illustrative DMI", response.data)
        self.assertIn(b"not a historical measurement", response.data)
        data = tracker.series(1, "DEMO-01", root=demo.DEMO_ROOT / "u21-tracker")
        self.assertEqual(len(data["players"]), 12)
        for player in data["players"]:
            self.assertEqual(player["points"][0]["dmi"], round(player["points"][1]["dmi"] * 0.9))
            self.assertIsNone(player["points"][0]["salary"])
            self.assertTrue(player["points"][0]["syntheticDmi"])

    def test_personal_token_sign_in_scope_and_sign_out(self):
        class TokenClient:
            def __init__(self, token):
                self.token = token

            def get(self, path, params=None):
                self.assert_token()
                if path == "/me":
                    return {"username": "Beta Manager", "scopes": ["Public", "Market"], "teams": []}
                raise AssertionError(path)

            def assert_token(self):
                if self.token != "test-personal-token":
                    raise AssertionError("Unexpected token")

        client = web_tool.app.test_client()
        with patch.object(auth, "V1Client", TokenClient), patch.dict("os.environ", {"BB_V1_REDIS_URL": "", "BB_V1_TOKEN_ENCRYPTION_KEY": "", "BB_V1_ALLOW_INMEMORY_TOKEN_LOGIN": "true"}):
            home = client.get("/beta/")
            self.assertIn(b"Sign in with API token", home.data)
            csrf = re.search(rb'name="login_csrf" value="([^"]+)"', home.data).group(1).decode()
            response = client.post("/beta/token/sign-in", data={"login_csrf": csrf, "api_token": "test-personal-token"}, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Signed in as Beta Manager", response.data)
            self.assertNotIn(b"test-personal-token", response.data)
            self.assertNotIn("test-personal-token", response.headers.get("Set-Cookie", ""))
            sid_cookie = client.get_cookie("bb_beta_sid", path="/beta")
            with web_tool.app.test_request_context("/beta/", headers={"Cookie": f"bb_beta_sid={sid_cookie.value}"}):
                pair = auth.current_session()
                self.assertEqual(pair[1]["scopes"], ["Public", "Market"])
                csrf_logout = pair[1]["csrf"]
            logout = client.post("/beta/oauth/logout", data={"csrf": csrf_logout}, follow_redirects=True)
            self.assertIn(b"Sign in with API token", logout.data)

    def test_national_schedule_selects_the_national_team_for_aggregation(self):
        fake = FakeClient({"/countries/IL/national-teams": {"teams": [{"id": TEAM_ID, "kind": "JuniorNationalTeam"}]}})
        report = {"teamName": "Israel U21", "usedMatches": 1, "wins": 1, "losses": 0, "warnings": [], "skipped": [], "matches": [], "players": []}
        with patch("beta_v1.routes._connection", return_value=(fake, {}, "")), patch("beta_v1.routes.reports.schedule_ids", return_value=[MATCH_ID]) as schedule, patch("beta_v1.routes.reports.build_report", return_value=report) as build:
            response = web_tool.app.test_client().post("/beta/multi-match", data={"national_country_id": "IL", "national_kind": "JuniorNationalTeam", "season": "1", "count": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Israel U21", response.data)
        schedule.assert_called_once_with(fake, TEAM_ID, 1, 1)
        build.assert_called_once_with(fake, [MATCH_ID], TEAM_ID)

    def test_coach_view_renders_private_skills_and_training_conditions(self):
        team = {"id": TEAM_ID, "name": "Club", "kind": "ManagedTeam"}
        player = {"id": PLAYER_ID, "firstName": "Test", "lastName": "Guard", "age": 19, "bestPosition": "PointGuard", "dmi": 100, "gameShape": 8, "skills": {"jumpShot": {"level": 10}}}
        session = {"trainedAt": "2026-09-29T00:00:00Z", "type": "OneOnOne", "efficiencyPercent": 90, "positions": ["PointGuard"], "conditions": {"coachLevel": "Strong", "coachSpecialty": None, "youthTrainerLevel": None, "gymLevel": 2, "trainingCourtLevel": 1, "isOffseason": False}, "participants": [{"player": player, "minutes": 48, "trainingMinutes": 48, "hasFullMinutes": True}], "skillChanges": [], "breakthroughs": []}
        fake = FakeClient({f"/teams/{TEAM_ID}/roster": {"players": [player]}, f"/teams/{TEAM_ID}/training/history": {"sessions": [session]}})
        with patch("beta_v1.routes._connection", return_value=(fake, {"me": {"teams": [team]}, "scopes": ["Public", "Team"]}, "")):
            response = web_tool.app.test_client().get(f"/beta/national-training?team_id={TEAM_ID}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"View private skills", response.data)
        self.assertIn(b"jumpShot: 10", response.data)
        self.assertIn(b"Training court: 1", response.data)


class BetaReportTests(unittest.TestCase):
    def test_boxscore_totals_and_unavailable_warning(self):
        match = {"id": MATCH_ID, "scheduledAt": "2026-09-20T12:00:00Z", "teams": [
            {"teamId": TEAM_ID, "name": "A", "isHome": True, "score": 83, "periodScores": [20, 20, 20, 23]},
            {"teamId": OTHER_ID, "name": "B", "isHome": False, "score": 70, "periodScores": [18, 17, 18, 17]},
        ]}
        line = {"player": {"id": PLAYER_ID, "firstName": "Test", "lastName": "Guard"}, "position": "PointGuard", "minutes": 30, "points": 20, "fieldGoals": 8, "fieldGoalsAttempts": 15, "rebounds": 4, "offensiveRebounds": 1, "assists": 6, "plusMinus": 9, "starRating": 6.5}
        box = {"matchId": MATCH_ID, "teams": [
            {"teamId": TEAM_ID, "ratings": {"offenseStrategy": "Motion", "outsideScoring": "Strong"}, "players": [line]},
            {"teamId": OTHER_ID, "ratings": {}, "players": []},
        ]}
        client = FakeClient({f"/matches/{MATCH_ID}": match, f"/matches/{MATCH_ID}/boxscore": box})
        result = reports.build_report(client, [MATCH_ID], TEAM_ID)
        self.assertEqual(result["teamId"], TEAM_ID)
        self.assertEqual(result["players"][0]["points"], 20)
        self.assertEqual(result["players"][0]["minutes"], 30)
        self.assertEqual(result["matches"][0]["ratings"]["offenseStrategy"], "Motion")
        self.assertEqual(result["strategyCounts"]["offenseStrategy"], {"Motion": 1})
        self.assertEqual(result["ratingDistributions"]["outsideScoring"], {"Strong": 1})
        self.assertIn("Play-by-play", result["warnings"][0])
        self.assertNotIn("events", result)

    def test_schedule_pages_and_completed_filter(self):
        rows = [{"id": f"{i:08x}-1111-4111-8111-111111111111", "scheduledAt": f"2026-09-{(i % 28) + 1:02d}T00:00:00Z", "finishedAt": "2026-09-29T00:00:00Z", "teams": [{"score": 1}, {"score": 2}]} for i in range(33)]
        rows[-1]["finishedAt"] = None
        client = FakeClient({f"/teams/{TEAM_ID}/schedule": lambda params: {"matches": rows[params["offset"]:params["offset"] + params["limit"]]}})
        result = reports.schedule_ids(client, TEAM_ID, 1, 10)
        self.assertEqual(len(result), 10)
        self.assertEqual([call[1]["offset"] for call in client.calls], [0, 30])


class BetaCollectorTests(unittest.TestCase):
    def test_market_archive_keeps_last_skills_without_following_old_players(self):
        now = datetime(2026, 9, 29, tzinfo=timezone.utc)
        listing = {"auctionId": MATCH_ID, "endsAt": "2026-09-30T00:00:00Z", "player": {"id": PLAYER_ID, "firstName": "Test", "lastName": "Guard", "salary": 40000}}
        client = FakeClient({"/market/players": {"players": [listing]}, f"/market/players/{PLAYER_ID}/auction": {"isOpen": True, "skills": {"jumpShot": {"level": 10, "change": "Improved"}}, "currentPrice": 5000, "skillsVisibleUntil": "2026-09-30T00:00:00Z"}})
        with tempfile.TemporaryDirectory() as directory, patch.object(market, "_pause"):
            path = Path(directory) / "players.json"
            changed, archive = market.collect(client, now=now, path=path)
            self.assertTrue(changed)
            self.assertEqual(archive["players"][PLAYER_ID]["lastKnownSkills"]["jumpShot"]["level"], 10)
            client.calls.clear()
            changed, _ = market.collect(client, now=now, path=path)
            self.assertFalse(changed)
            self.assertEqual(client.calls, [])
            client.calls.clear()
            changed, _ = market.collect(client, now=now.replace(day=2, month=10), path=path)
            self.assertTrue(changed)
            self.assertEqual([call[0] for call in client.calls], ["/market/players"])
            self.assertNotIn("bbpat_", path.read_text(encoding="utf-8"))

    def test_market_reveals_at_most_thirteen_new_players(self):
        now = datetime(2026, 9, 29, tzinfo=timezone.utc)
        listings = []
        responses = {}
        for index in range(14):
            player_id = f"{index + 1:08x}-4444-4444-8444-444444444444"
            listings.append({"auctionId": MATCH_ID, "endsAt": "2026-09-30T00:00:00Z", "player": {"id": player_id, "salary": 40000 - index}})
            responses[f"/market/players/{player_id}/auction"] = {"isOpen": True, "skills": {"jumpShot": {"level": 10}}}
        responses["/market/players"] = {"players": listings}
        with tempfile.TemporaryDirectory() as directory, patch.object(market, "_pause"):
            archive_path = Path(directory) / "players.json"
            _, archive = market.collect(FakeClient(responses), now=now, path=archive_path)
        self.assertEqual(len(archive["reveals"]), 13)
        self.assertEqual(len(archive["players"]), 13)

    def test_tracker_uses_new_string_ids_and_season_dates(self):
        responses = {
            "/countries": {"countries": [{"id": "IL"}]},
            "/countries/IL/national-teams": {"teams": [{"id": TEAM_ID, "name": "Israel U21", "kind": "JuniorNationalTeam"}]},
            "/seasons": {"seasons": [{"number": 1, "startDate": "2026-09-01", "endDate": "2026-12-31"}]},
            f"/national-teams/{TEAM_ID}/roster": {"players": [{"id": PLAYER_ID, "firstName": "Test", "lastName": "Guard", "bestPosition": "PointGuard", "dmi": 100000, "gameShape": 8, "salary": 10000, "potential": 9}]},
        }
        client = FakeClient(responses)
        with tempfile.TemporaryDirectory() as directory, patch.object(tracker, "TRACKER_ROOT", Path(directory)), patch.object(tracker, "tracked_names", return_value=[{"countryId": 15, "name": "Israel"}]), patch.object(tracker, "_pause"):
            path = tracker.collect(client, today=datetime(2026, 9, 29, tzinfo=timezone.utc).date())
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(snapshot["season"], 1)
            self.assertEqual(snapshot["week"], 5)
            self.assertEqual(snapshot["countries"][0]["countryId"], "IL")
            self.assertNotIn("legacyCountryId", snapshot["countries"][0])
            self.assertEqual(snapshot["countries"][0]["players"][0]["playerId"], PLAYER_ID)


class BetaAuthTests(unittest.TestCase):
    def test_pkce_uses_only_requested_lowercase_scopes(self):
        class FakeRedis:
            def set(self, *args, **kwargs):
                pass

        settings = {"BB_V1_CLIENT_ID": "bbc_test", "BB_V1_CLIENT_SECRET": "bbcs_test", "BB_V1_REDIS_URL": "redis://test", "BB_V1_TOKEN_ENCRYPTION_KEY": "test"}
        with patch.dict("os.environ", settings), patch.object(auth, "_redis", return_value=FakeRedis()), patch.object(auth, "load_session", return_value=None), web_tool.app.test_request_context("/beta/oauth/start"):
            url, state = auth.start_authorization("training")
        query = parse_qs(urlparse(url).query)
        self.assertEqual(set(query["scope"][0].split()), {"public", "team"})
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertTrue(state)

    def test_refresh_rotates_once_for_concurrent_old_token(self):
        stored = {"access_token": "old", "refresh_token": "refresh-old", "expires_at": 0}

        class FakeRedis:
            def lock(self, *args, **kwargs):
                return nullcontext()

        class Response:
            ok = True

            def json(self):
                return {"access_token": "new", "refresh_token": "refresh-new", "expires_in": 3600}

        def save(_, record):
            stored.update(record)

        with patch.dict("os.environ", {"BB_V1_CLIENT_ID": "bbc_test", "BB_V1_CLIENT_SECRET": "bbcs_test"}), patch.object(auth, "_redis", return_value=FakeRedis()), patch.object(auth, "load_session", side_effect=lambda _: dict(stored)), patch.object(auth, "save_session", side_effect=save), patch.object(auth.requests, "post", return_value=Response()) as post:
            self.assertEqual(auth.refresh_session("sid", "old", force=True), "new")
            self.assertEqual(auth.refresh_session("sid", "old", force=True), "new")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(stored["refresh_token"], "refresh-new")


class BetaApiTests(unittest.TestCase):
    def test_long_rate_limit_is_reported_without_short_retries(self):
        class Response:
            ok = False
            status_code = 429
            headers = {"Retry-After": "60", "X-RateLimit-Reset": "9999999999"}

            def json(self):
                return {"error": {"code": "RateLimited", "description": "Wait for reset."}}

        class Session:
            def __init__(self):
                self.headers = {}
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                return Response()

        session = Session()
        with self.assertRaises(V1ApiError) as raised:
            V1Client("test", session=session).get("/countries")
        self.assertEqual(session.calls, 1)
        self.assertEqual(raised.exception.retry_after, 60)


if __name__ == "__main__":
    unittest.main()
