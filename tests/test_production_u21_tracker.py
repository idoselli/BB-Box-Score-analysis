from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from beta_v1 import tracker
from collect_u21_tracker import collect_roster, snapshot_period, tracked_countries
from web_tool import app


class ProductionU21TrackerTests(unittest.TestCase):
    def test_week_two_and_rollover_follow_friday_calendar(self):
        seasons = [
            {"number": 74, "startDate": "2026-11-21", "endDate": "2027-02-26"},
            {"number": 75, "startDate": "2027-02-27", "endDate": None},
        ]
        for day, period in [
            (date(2026, 11, 20), (74, 1)),
            (date(2026, 11, 24), (74, 2)),
            (date(2026, 11, 27), (74, 2)),
            (date(2026, 12, 4), (74, 3)),
            (date(2027, 2, 26), (75, 1)),
            (date(2027, 3, 5), (75, 2)),
        ]:
            with self.subTest(day=day):
                self.assertEqual(snapshot_period(seasons, day), period)

    def test_country_selection_includes_europe_and_requested_extras(self):
        client = Mock()
        client.get.return_value = {"countries": [
            {"id": "DE", "name": "Germany", "confederation": "Europe"},
            {"id": "GB-WLS", "name": "Wales", "confederation": "Europe"},
            {"id": "CA", "name": "Canada", "confederation": "Americas"},
            *({"id": code, "name": code} for code in ("IL", "US", "CN", "HK", "TW")),
        ]}
        codes = {country["id"] for country in tracked_countries(client, set())}
        self.assertEqual(codes, {"DE", "GB-WLS", "IL", "US", "CN", "HK", "TW"})

    def test_roster_figures_reach_the_existing_page_and_api(self):
        team_id = "22222222-2222-4222-8222-222222222222"
        player_id = "44444444-4444-4444-8444-444444444444"
        client = Mock()
        client.get.side_effect = [
            {"teams": [
                {"id": "senior", "kind": "SeniorNationalTeam"},
                {"id": team_id, "kind": "JuniorNationalTeam"},
            ]},
            {"teamId": team_id, "players": [{
                "id": player_id, "firstName": "Test", "lastName": "Guard",
                "dmi": 123456, "bestPosition": "PointGuard", "gameShape": 8,
                "salary": 10000, "potential": 9,
            }]},
        ]
        with patch("collect_u21_tracker.time.sleep"):
            squad = collect_roster(client, {"id": "IL", "name": "Israel"})
        self.assertEqual([call.args[0] for call in client.get.call_args_list], [
            "/countries/IL/national-teams", f"/national-teams/{team_id}/roster",
        ])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(tracker, "PRODUCTION_TRACKER_ROOT", root), patch.dict("os.environ", {"VERCEL": ""}):
                tracker.save_snapshot(root, 74, 2, [squad], "2026-11-27T11:30:00+00:00")
                tracker.write_production_index()
                browser = app.test_client()
                page = browser.get("/beta/u21-tracker")
                api = browser.get("/beta/api/u21-tracker?season=74&countryId=IL")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Test Guard", page.data)
        self.assertEqual(api.json["weeks"], [2])
        self.assertEqual(api.json["players"][0]["playerId"], player_id)
        self.assertEqual(api.json["players"][0]["points"][0]["dmi"], 123456)

    def test_vercel_reads_published_snapshots_without_a_new_build(self):
        team = {"countryId": "IL", "name": "Israel", "teamId": "team"}
        documents = {
            "index.json": {"seasons": [74]},
            "s74/meta.json": {"season": 74, "weeks": [2], "countries": [team]},
            "s74/w2.json": {"countries": [{**team, "players": [
                {"playerId": "player", "name": "Test Guard", "dmi": 123456},
            ]}]},
        }

        def response(url, timeout):
            relative = url.removeprefix(tracker.PRODUCTION_SNAPSHOT_URL + "/")
            return Mock(ok=True, json=Mock(return_value=documents[relative]))

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(tracker, "PRODUCTION_TRACKER_ROOT", Path(directory)), \
                 patch.dict("os.environ", {"VERCEL": "1"}), \
                 patch.object(tracker.requests, "get", side_effect=response) as request:
                api = app.test_client().get("/beta/api/u21-tracker?season=74&countryId=IL")
        self.assertEqual(api.status_code, 200)
        self.assertEqual(api.json["players"][0]["points"][0]["dmi"], 123456)
        self.assertEqual(request.call_count, 3)
