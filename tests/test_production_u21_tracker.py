from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from beta_v1 import tracker
from beta_v1.api import V1Client
from collect_u21_tracker import collect_roster, snapshot_period, tracked_countries
from web_tool import app


class ProductionU21TrackerTests(unittest.TestCase):
    def test_collector_can_recover_a_dropped_api_connection(self):
        session = Mock(headers={})
        session.get.side_effect = [
            requests.ConnectionError("remote end closed connection"),
            Mock(ok=True, headers={}, json=Mock(return_value={"players": []})),
        ]
        client = V1Client("test", session=session, retry_network_errors=True)
        with patch("beta_v1.api.time.sleep") as sleep:
            self.assertEqual(client.get("/national-teams/team/roster"), {"players": []})
        self.assertEqual(session.get.call_count, 2)
        sleep.assert_called_once_with(1)

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
            {"id": "N1", "name": "Nations of Europe", "confederation": "Europe"},
            {"id": "CA", "name": "Canada", "confederation": "Americas"},
            *({"id": code, "name": code} for code in ("IL", "US", "CN", "HK", "TW")),
        ]}
        codes = {country["id"] for country in tracked_countries(client, set())}
        self.assertEqual(codes, {"DE", "GB-WLS", "IL", "US", "CN", "HK", "TW"})

    def test_incomplete_api_calendar_uses_confirmed_friday_anchor(self):
        seasons = [{"number": 73, "startDate": "2026-08-08", "endDate": "2026-11-14"}]
        with patch("builtins.print"):
            self.assertEqual(snapshot_period(seasons, date(2026, 11, 27)), (74, 2))
            self.assertEqual(snapshot_period(seasons, date(2027, 2, 19)), (74, 14))
            self.assertEqual(snapshot_period(seasons, date(2027, 2, 26)), (75, 1))

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
            }, {
                "id": "55555555-5555-4555-8555-555555555555",
                "firstName": "Zed", "lastName": "Center", "dmi": 234567,
                "bestPosition": "Center",
            }]},
        ]
        squad = collect_roster(client, {"id": "IL", "name": "Israel"})
        self.assertEqual([call.args[0] for call in client.get.call_args_list], [
            "/countries/IL/national-teams", f"/national-teams/{team_id}/roster",
        ])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(tracker, "PRODUCTION_TRACKER_ROOT", root), patch.dict("os.environ", {"VERCEL": ""}):
                empty_squad = {"countryId": "FR", "name": "France", "teamId": "france", "players": []}
                tracker.save_snapshot(root, 74, 2, [squad, empty_squad], "2026-11-27T11:30:00+00:00")
                tracker.write_production_index()
                browser = app.test_client()
                page = browser.get("/beta/u21-tracker")
                empty_page = browser.get("/beta/u21-tracker?season=74&countryId=FR")
                compared = browser.get("/beta/u21-tracker?season=74&countryId=IL&compareCountryId=FR")
                duplicate = browser.get("/beta/u21-tracker?season=74&countryId=IL&compareCountryId=IL")
                api = browser.get("/beta/api/u21-tracker?season=74&countryId=IL")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Test Guard", page.data)
        self.assertIn(b"123,456", page.data)
        self.assertIn(b"10,000", page.data)
        self.assertIn(b'data-position="PG"', page.data)
        roster = page.data.split(b'<table class="tracker-table"', 1)[1]
        self.assertIn(b'aria-sort="descending"', roster)
        self.assertIn(b'data-sort-value="234567"', roster)
        self.assertLess(roster.index(b"Zed Center"), roster.index(b"Test Guard"))
        self.assertIn(b"No players appeared in the recorded squad.", empty_page.data)
        self.assertIn(b'id="tracker-squad-2"', compared.data)
        self.assertNotIn(b'id="tracker-squad-2"', duplicate.data)
        self.assertEqual(api.json["weeks"], [2])
        self.assertEqual(api.json["players"][0]["playerId"], player_id)
        self.assertEqual(api.json["players"][0]["points"][0]["dmi"], 123456)

    def test_vercel_reads_published_snapshots_without_a_new_build(self):
        team = {"countryId": "IL", "name": "Israel", "teamId": "team"}
        other = {"countryId": "US", "name": "USA", "teamId": "other"}
        documents = {
            "index.json": {"seasons": [74]},
            "s74/meta.json": {"season": 74, "weeks": [2], "countries": [team, other]},
            "s74/w2.json": {"countries": [{**team, "players": [
                {"playerId": "player", "name": "Test Guard", "dmi": 123456},
            ]}, {**other, "players": [
                {"playerId": "opponent", "name": "Test Center", "dmi": 234567},
            ]}]},
        }

        def response(url, timeout):
            relative = url.removeprefix(tracker.PRODUCTION_SNAPSHOT_URL + "/")
            return Mock(ok=True, json=Mock(return_value=documents[relative]))

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(tracker, "PRODUCTION_TRACKER_ROOT", Path(directory)), \
                 patch.dict("os.environ", {"VERCEL": "1"}), \
                 patch.object(tracker.requests, "get", side_effect=response) as request:
                page = app.test_client().get("/beta/u21-tracker?season=74&countryId=IL&compareCountryId=US")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Test Guard", page.data)
        self.assertIn(b"Test Center", page.data)
        self.assertEqual(request.call_count, 3)
