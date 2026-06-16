import unittest
from unittest.mock import patch

import web_tool
from bb_site import GameLogEntry, RosterPlayer


class FakeBBApi:
    def __init__(self, username, password):
        self.logged_in = True

    def seasons(self):
        return [{"id": "72", "label": "Season 72", "current": True}]

    def player_info(self, player_id):
        return {
            "player_id": player_id,
            "first_name": "Olegas",
            "last_name": "Sergadejevas",
            "age": 21,
            "height": 79,
            "salary": 41048,
            "best_position": "SG",
            "potential": 8,
            "game_shape": 8,
            "dmi": 123456,
        }


class FakeBBSiteClient:
    def __init__(self, username, password):
        self.username = username
        self.password = password

    def login(self):
        return None

    def fetch_u21_roster(self, country_id):
        return "Lietuva U21", [RosterPlayer(54410032, "Olegas Sergadejevas")]

    def fetch_player_game_log(self, player_id, season):
        return {
            71: [GameLogEntry("2/7/2026", "SG", 48, "League")],
            72: [
                GameLogEntry("5/9/2026", "PG", 48, "League"),
                GameLogEntry("5/10/2026", "C", 60, "National Team"),
            ],
        }.get(season, [])


class U21ModeFlaskTests(unittest.TestCase):
    def test_form_renders_new_mode(self):
        client = web_tool.app.test_client()
        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"U21 squad analysis", response.data)
        self.assertIn(b"Beta", response.data)
        self.assertIn(b"Analyzer Password", response.data)
        self.assertIn(b'id="u21LockedFields" class="u21-locked-fields locked"', response.data)

    def test_u21_unlock_requires_configured_password(self):
        client = web_tool.app.test_client()
        with patch.dict(web_tool.os.environ, {}, clear=True):
            response = client.post("/u21-analyzer-unlock", json={"password": "anything"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Analyzer password is incorrect or not configured.")

    def test_u21_unlock_rejects_wrong_password(self):
        client = web_tool.app.test_client()
        with patch.dict(web_tool.os.environ, {"U21_ANALYZER_PASSWORD": "correct"}, clear=True):
            response = client.post("/u21-analyzer-unlock", json={"password": "wrong"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Analyzer password is incorrect or not configured.")

    def test_u21_unlock_accepts_configured_password(self):
        client = web_tool.app.test_client()
        with patch.dict(web_tool.os.environ, {"U21_ANALYZER_PASSWORD": "correct"}, clear=True):
            response = client.post("/u21-analyzer-unlock", json={"password": "correct"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True})

    def test_local_menu_defaults_to_current_season(self):
        seasons = web_tool.load_local_national_options()["seasons"]

        self.assertEqual(seasons[0]["id"], "72")
        self.assertTrue(seasons[0]["current"])

    def test_missing_u21_inputs_return_clear_errors(self):
        client = web_tool.app.test_client()
        response = client.post(
            "/report",
            data={"mode": "u21_training", "username": "u", "password": "p"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"BB site password is required", response.data)

        response = client.post(
            "/report",
            data={
                "mode": "u21_training",
                "username": "u",
                "password": "p",
                "bb_site_password": "site",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Choose a country U21 team", response.data)

    def test_mocked_roster_logs_build_estimator_report(self):
        old_api = web_tool.BBApi
        old_site = web_tool.BBSiteClient
        web_tool.BBApi = FakeBBApi
        web_tool.BBSiteClient = FakeBBSiteClient
        try:
            report = web_tool.build_u21_training_report("u", "code", "site", "1104", "72", nt_strength="strong")
        finally:
            web_tool.BBApi = old_api
            web_tool.BBSiteClient = old_site

        self.assertEqual(report["team_name"], "Lietuva U21")
        self.assertEqual(report["nt_strength"], "strong")
        self.assertEqual(report["training_multiplier"], 1.5)
        self.assertEqual(len(report["players"]), 1)
        player = report["players"][0]
        self.assertEqual(player["training_counts_by_position"]["SG"], 1)
        self.assertEqual(player["training_counts_by_position"]["PG"], 1)
        self.assertEqual(player["training_summary_by_age"][-1]["age"], 21)
        self.assertEqual(player["current_season_training"][0]["training"], "0.5 OD for 1 + 0.5 PA for 1")
        self.assertEqual(player["modeled_start_salary"], player["salary"])
        self.assertEqual(player["start_best_position_salary"], player["salary"])
        self.assertEqual(len(player["ignored_games"]), 1)

    def test_mocked_u21_route_renders_report(self):
        old_api = web_tool.BBApi
        old_site = web_tool.BBSiteClient
        web_tool.BBApi = FakeBBApi
        web_tool.BBSiteClient = FakeBBSiteClient
        try:
            response = web_tool.app.test_client().post(
                "/report",
                data={
                    "mode": "u21_training",
                    "username": "u",
                    "password": "code",
                    "bb_site_password": "site",
                    "estimator_country_id": "1104",
                    "estimator_season": "72",
                    "estimator_nt_strength": "strong",
                },
            )
        finally:
            web_tool.BBApi = old_api
            web_tool.BBSiteClient = old_site

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Olegas Sergadejevas", response.data)
        self.assertIn(b"Coach Level</div><div class=\"v\">7", response.data)
        self.assertIn(b"NT Strength</div><div class=\"v\">Strong", response.data)
        self.assertIn(b"Modeled Start Salary", response.data)
        self.assertIn(b"tremendous", response.data)
        self.assertIn(b"0.5 OD for 1 + 0.5 PA for 1", response.data)


if __name__ == "__main__":
    unittest.main()
