import unittest
from types import SimpleNamespace
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
        self.assertIn(b"/static/nika-logo.png", response.data)
        self.assertIn(b"NIKA box score tool logo", response.data)
        self.assertIn(b"PBP Result", response.data)
        self.assertIn(b"U21 squad analysis", response.data)
        self.assertIn(b"Beta", response.data)
        self.assertIn(b"Analyzer Password", response.data)
        self.assertIn(b'id="u21LockedFields" class="u21-locked-fields locked"', response.data)

    def test_pbp_result_mode_uses_pbp_result_loader(self):
        client = web_tool.app.test_client()
        result = {
            "matchid": "123",
            "home": {
                "name": "Home Five",
                "points": 91,
                "is_winner": True,
                "players": [{"name": "Home Guard", "pts": 24, "ast": 7, "reb": 4}],
            },
            "away": {
                "name": "Away Five",
                "points": 88,
                "is_winner": False,
                "players": [{"name": "Away Big", "pts": 18, "ast": 2, "reb": 11}],
            },
            "period_scores": [
                {"label": "End Q1", "home": 22, "away": 20},
                {"label": "End Q2", "home": 45, "away": 42},
            ],
            "source_detail": "Read directly from pbp.aspx team score fields.",
        }

        with patch.object(web_tool, "load_pbp_result", return_value=result) as pbp_loader:
            with patch.object(web_tool, "generate_report", side_effect=AssertionError("wrong path")):
                response = client.post(
                    "/report",
                    data={
                        "mode": "pbp_result",
                        "username": "u",
                        "password": "code",
                        "matchid": "123",
                    },
                )

        self.assertEqual(response.status_code, 200)
        pbp_loader.assert_called_once_with("123", "u", "code")
        self.assertNotIn(b"youtube-nocookie", response.data)
        self.assertNotIn(b"Click to watch video and see results", response.data)
        self.assertNotIn(b'id="pbpResultContent" hidden', response.data)
        self.assertNotIn(b"window.setTimeout", response.data)
        self.assertIn(b'id="pbpResultContent"', response.data)
        self.assertIn(b"Source: BBAPI pbp.aspx", response.data)
        self.assertIn(b"Home Five", response.data)
        self.assertIn(b"91 : 88", response.data)
        self.assertIn(b"Home Guard", response.data)
        self.assertIn(b"Away Big", response.data)
        self.assertIn(b"PTS", response.data)
        self.assertIn(b"AST", response.data)
        self.assertIn(b"REB", response.data)
        self.assertIn(b"Score By Period", response.data)
        self.assertIn(b"End Q1", response.data)

    def test_pbp_result_can_read_structured_scores(self):
        payload = """
        <bbapi version="1">
          <match id="123">
            <awayTeam id="2">
              <teamName>Away Five</teamName>
              <score partials="20,22,25,21">88</score>
            </awayTeam>
            <homeTeam id="1">
              <teamName>Home Five</teamName>
              <score partials="22,23,24,22">91</score>
            </homeTeam>
            <events />
          </match>
        </bbapi>
        """

        result = web_tool.extract_pbp_result_from_xml("123", payload)

        self.assertIsNotNone(result)
        self.assertEqual(result["home"]["name"], "Home Five")
        self.assertEqual(result["home"]["points"], 91)
        self.assertEqual(result["home"]["players"], [])
        self.assertEqual(result["away"]["name"], "Away Five")
        self.assertEqual(result["away"]["points"], 88)
        self.assertEqual(
            result["period_scores"],
            [
                {"label": "End Q1", "home": 22, "away": 20},
                {"label": "End Q2", "home": 45, "away": 42},
                {"label": "End Q3", "home": 69, "away": 67},
                {"label": "End Q4", "home": 91, "away": 88},
            ],
        )

    def test_cumulative_period_scores_labels_overtime(self):
        rows = web_tool.cumulative_period_scores([10, 10, 10, 10, 7], [9, 11, 8, 12, 5])

        self.assertEqual(rows[-1], {"label": "End OT1", "home": 47, "away": 45})

    def test_pbp_result_reads_period_scores_from_event_stream(self):
        payload = """
        <bbapi version="1">
          <match id="123">
            <awayTeam id="2"><teamName>Away Five</teamName></awayTeam>
            <homeTeam id="1"><teamName>Home Five</teamName></homeTeam>
            <events>
              <event seq="1" quarter="1" clock="0:00">
                <score away="11" home="23" />
                <text>End of period.</text>
              </event>
              <event seq="2" quarter="2" clock="0:00">
                <score away="28" home="43" />
                <text>End of period.</text>
              </event>
              <event seq="3" quarter="4" clock="0:00">
                <score away="57" home="81" />
                <text>~~GAME OVER~~</text>
              </event>
            </events>
          </match>
        </bbapi>
        """

        result = web_tool.extract_pbp_result_from_xml("123", payload)

        self.assertIsNotNone(result)
        self.assertEqual(result["home"]["points"], 81)
        self.assertEqual(result["away"]["points"], 57)
        self.assertEqual(
            result["period_scores"],
            [
                {"label": "End Q1", "home": 23, "away": 11},
                {"label": "End Q2", "home": 43, "away": 28},
                {"label": "End Q4", "home": 81, "away": 57},
            ],
        )

    def test_pbp_payload_unwraps_nested_report_string_container(self):
        payload = """
        <bbapi version="1">
          <match>
            <HomeTeam><ID>1</ID><Name>Home</Name></HomeTeam>
            <AwayTeam><ID>2</ID><Name>Away</Name></AwayTeam>
            <ReportString>abc</ReportString>
          </match>
        </bbapi>
        """

        unwrapped = web_tool.pbp_payload_xml(payload)

        self.assertIn("<ReportString>abc</ReportString>", unwrapped)
        self.assertNotIn("<bbapi", unwrapped)

    def test_player_stat_rows_uses_points_assists_and_total_rebounds(self):
        class FakeFullStats:
            def __init__(self, stats):
                self.stats = stats

            def player_stats(self):
                return self.stats

        player = SimpleNamespace(
            id=7,
            name="Boxscore Hero",
            stats=SimpleNamespace(full=FakeFullStats({"pts": 20, "ast": 5, "tr": 9, "mins": 34})),
        )
        unused = SimpleNamespace(
            id=8,
            name="Bench Zero",
            stats=SimpleNamespace(full=FakeFullStats({"pts": 0, "ast": 0, "tr": 0, "mins": 0})),
        )
        team = SimpleNamespace(players=[player, unused])

        rows = web_tool.player_stat_rows(team)

        self.assertEqual(rows, [{"id": 7, "name": "Boxscore Hero", "pts": 20, "ast": 5, "reb": 9, "mins": 34}])

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
