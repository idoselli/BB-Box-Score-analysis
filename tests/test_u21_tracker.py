from datetime import datetime, timezone
import json
import tempfile
import unittest
from pathlib import Path

import u21_tracker
import scrape_u21_tracker
import web_tool


class U21TrackerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_root = u21_tracker.LOCAL_TRACKER_ROOT
        u21_tracker.LOCAL_TRACKER_ROOT = Path(self.tempdir.name)

        season_dir = u21_tracker.LOCAL_TRACKER_ROOT / "s99"
        season_dir.mkdir(parents=True)
        (season_dir / "meta.json").write_text(
            json.dumps(
                {
                    "season": 99,
                    "weeks": [1, 2],
                    "countries": [
                        {"countryId": 15, "name": "Israel", "pool": "Pool H"},
                        {"countryId": 20, "name": "Lietuva", "pool": "Pool H"},
                    ],
                    "updatedAt": "2026-07-28T18:36:16.990Z",
                }
            ),
            encoding="utf-8",
        )
        (season_dir / "w1.json").write_text(
            json.dumps(
                {
                    "season": 99,
                    "week": 1,
                    "scrapedAt": "2026-07-01T00:00:00Z",
                    "countries": [
                        {
                            "countryId": 15,
                            "name": "Israel",
                            "pool": "Pool H",
                            "players": [
                                {
                                    "playerId": 100,
                                    "name": "A Player",
                                    "position": "SG",
                                    "dmi": 100000,
                                    "gameShape": 7,
                                    "salary": 10000,
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (season_dir / "w2.json").write_text(
            json.dumps(
                {
                    "season": 99,
                    "week": 2,
                    "scrapedAt": "2026-07-08T00:00:00Z",
                    "countries": [
                        {
                            "countryId": 15,
                            "name": "Israel",
                            "pool": "Pool H",
                            "players": [
                                {
                                    "playerId": 100,
                                    "name": "A Player",
                                    "position": "PG",
                                    "dmi": 125000,
                                    "gameShape": 8,
                                    "salary": 12000,
                                },
                                {
                                    "playerId": 200,
                                    "name": "B Player",
                                    "position": "C",
                                    "dmi": 90000,
                                    "gameShape": 6,
                                    "salary": 9000,
                                },
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        u21_tracker.LOCAL_TRACKER_ROOT = self.old_root
        self.tempdir.cleanup()

    def test_load_country_series_combines_week_snapshots(self):
        series = u21_tracker.load_country_series(99, 15)

        self.assertEqual(series["country"]["name"], "Israel")
        self.assertEqual(series["weeks"], [1, 2])
        self.assertEqual([player["playerId"] for player in series["players"]], [100, 200])
        self.assertEqual(series["players"][0]["position"], "PG")
        self.assertEqual([point["dmi"] for point in series["players"][0]["points"]], [100000, 125000])
        self.assertEqual([point["position"] for point in series["players"][0]["points"]], ["SG", "PG"])

    def test_api_returns_meta_and_country_series(self):
        client = web_tool.app.test_client()

        meta_response = client.get("/api/u21-tracker?season=99")
        self.assertEqual(meta_response.status_code, 200)
        self.assertEqual(meta_response.get_json()["countries"][0]["name"], "Israel")

        country_response = client.get("/api/u21-tracker?season=99&countryId=15")
        self.assertEqual(country_response.status_code, 200)
        body = country_response.get_json()
        self.assertEqual(body["country"]["pool"], "Pool H")
        self.assertEqual(len(body["players"]), 2)

    def test_parse_round_robin_pools(self):
        html = """
        <h2>Round Robin Pools</h2>
        <b>Pool H</b>
        <table>
          <tr class="rptrStandings trEntry">
            <td><a href="/country/15/jnt/overview.aspx">Israel U21</a></td>
          </tr>
          <tr class="rptrStandings trEntry">
            <td><a href="/country/20/jnt/overview.aspx">Lietuva U21</a></td>
          </tr>
        </table>
        Recent Matches
        <b>Pool A</b>
        <tr class="rptrStandings trEntry">
          <td><a href="/country/14/jnt/overview.aspx">England U21</a></td>
        </tr>
        """

        countries = scrape_u21_tracker.parse_round_robin_pools(html)

        self.assertEqual(
            countries,
            [
                {"countryId": 15, "name": "Israel", "pool": "Pool H"},
                {"countryId": 20, "name": "Lietuva", "pool": "Pool H"},
                {"countryId": 14, "name": "England", "pool": "Pool A"},
            ],
        )

    def test_write_week_snapshot_updates_meta(self):
        old_root = scrape_u21_tracker.TRACKER_ROOT
        scrape_u21_tracker.TRACKER_ROOT = Path(self.tempdir.name) / "scrape"
        try:
            payload = {
                "season": 99,
                "week": 3,
                "scrapedAt": "2026-07-15T00:00:00Z",
                "source": "fixture",
                "countries": [
                    {
                        "countryId": 15,
                        "name": "Israel",
                        "pool": "Pool H",
                        "players": [
                            {
                                "playerId": 100,
                                "name": "A Player",
                                "position": "SG",
                                "dmi": 100000,
                                "gameShape": 7,
                                "salary": 10000,
                            }
                        ],
                    }
                ],
            }
            week_path = scrape_u21_tracker.write_week_snapshot(99, 3, payload)
            meta_path = week_path.with_name("meta.json")

            self.assertTrue(week_path.exists())
            self.assertEqual(json.loads(meta_path.read_text(encoding="utf-8"))["weeks"], [3])

            seeded = scrape_u21_tracker.seed_week_zero(payload)
            self.assertEqual(seeded["week"], 0)
            self.assertEqual(seeded["countries"][0]["players"][0]["dmi"], 75000)
            self.assertEqual(seeded["countries"][0]["players"][0]["gameShape"], 5)
        finally:
            scrape_u21_tracker.TRACKER_ROOT = old_root

    def test_normalize_position(self):
        self.assertEqual(scrape_u21_tracker.normalize_position("Point Guard"), "PG")
        self.assertEqual(scrape_u21_tracker.normalize_position("sf"), "SF")
        self.assertIsNone(scrape_u21_tracker.normalize_position(""))

    def test_tracker_season_rolls_to_73_on_august_7(self):
        before_rollover = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
        first_s73_scrape = datetime(2026, 8, 7, 10, 30, tzinfo=timezone.utc)

        self.assertEqual(scrape_u21_tracker.current_tracker_season(before_rollover), 72)
        self.assertEqual(scrape_u21_tracker.current_tracker_season(first_s73_scrape), 73)
        self.assertEqual(scrape_u21_tracker.current_tracker_week(73, first_s73_scrape), 1)


if __name__ == "__main__":
    unittest.main()
