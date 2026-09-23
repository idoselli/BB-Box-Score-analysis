import csv
import io
import json
import unittest
from unittest.mock import patch
import zipfile

import web_tool


def sample_report():
    return {
        "team_name": "Maccabi תל אביב",
        "submitted_matches": 2,
        "used_matches": 1,
        "skipped_matches": 1,
        "wins": 1,
        "losses": 0,
        "warnings": ["One match was skipped"],
        "matches": [
            {
                "matchid": "123",
                "home_team": "Maccabi",
                "away_team": "Visitors",
                "result": "W",
                "selected_tactics": {"offense": "Motion", "gdp": {"focus": "inside"}},
            }
        ],
        "selected_team_key": "maccabi",
        "input_matchids": ["123", "bad"],
        "return_state": {"multi_source": "manual", "team_schedule_types": ["league"]},
        "tactic_minutes": [
            {
                "key": "inside",
                "label": "Inside",
                "positions": [
                    {"key": "pg", "label": "PG", "players": [{"name": "Guard", "mins": 31.5}]},
                    {"key": "sg", "label": "SG", "players": []},
                ],
            }
        ],
        "player_summary": [{"name": "=FORMULA", "gp": 1, "mins": 31.5, "pts": 20}],
        "matchup": [{"name": "Guard", "defended": {"a": 5, "m": 2}}],
        "defense": [{"name": "Guard", "defendedTotal": {"a": 4, "m": 1}}],
        "offense": {
            "shot_types": ["101"],
            "players": [{"name": "Guard", "counts": {"101": {"a": 3, "m": 2}}, "total": {"a": 3, "m": 2}}],
        },
        "defended_shots": {
            "players": ["Guard"],
            "shot_types": ["101"],
            "results": ["0", "1"],
            "events": [{"matchid": "123", "defender": "Guard", "result": "1"}],
        },
        "nba_dashboard": {
            "players": [{"matchid": "123", "name": "Guard", "pts": 20}],
            "team_rows": [{"matchid": "123", "team": {"pts": 80}, "opponent": {"pts": 70}}],
        },
    }


class MultiMatchExportTests(unittest.TestCase):
    def setUp(self):
        self.client = web_tool.app.test_client()

    def test_multi_report_template_exposes_all_export_options(self):
        self.assertIn('data-export-format="json"', web_tool.MULTI_REPORT_HTML)
        self.assertIn('data-export-format="csv_zip"', web_tool.MULTI_REPORT_HTML)
        self.assertIn('data-export-format="csv_combined"', web_tool.MULTI_REPORT_HTML)
        self.assertIn('fetch("/export-multi"', web_tool.MULTI_REPORT_HTML)
        self.assertIn("JSON.stringify({ format, report: data })", web_tool.MULTI_REPORT_HTML)

    def test_json_export_returns_complete_report(self):
        report = sample_report()
        response = self.client.post("/export-multi", json={"format": "json", "report": report})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/json")
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertEqual(json.loads(response.data), report)

    def test_csv_package_contains_all_datasets_and_escapes_formulas(self):
        response = self.client.post(
            "/export-multi", json={"format": "csv_zip", "report": sample_report()}
        )

        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {
                    "report_metadata.csv",
                    "warnings.csv",
                    "matches.csv",
                    "player_summary.csv",
                    "matchup.csv",
                    "defense.csv",
                    "offense_players.csv",
                    "defended_shots.csv",
                    "tactic_minutes.csv",
                    "nba_players.csv",
                    "nba_team_rows.csv",
                },
            )
            player_rows = list(
                csv.DictReader(io.StringIO(archive.read("player_summary.csv").decode("utf-8-sig")))
            )
            self.assertEqual(player_rows[0]["name"], "'=FORMULA")
            tactic_rows = list(
                csv.DictReader(io.StringIO(archive.read("tactic_minutes.csv").decode("utf-8-sig")))
            )
            self.assertEqual(len(tactic_rows), 2)
            self.assertEqual(tactic_rows[1]["position_label"], "SG")

    def test_combined_csv_is_long_form_and_preserves_nested_values(self):
        response = self.client.post(
            "/export-multi", json={"format": "csv_combined", "report": sample_report()}
        )

        self.assertEqual(response.status_code, 200)
        rows = list(csv.DictReader(io.StringIO(response.data.decode("utf-8-sig"))))
        self.assertEqual(
            list(rows[0]), ["section", "record_index", "record_label", "field", "value"]
        )
        formula = next(
            row for row in rows if row["section"] == "player_summary" and row["field"] == "name"
        )
        self.assertEqual(formula["record_index"], "0")
        self.assertEqual(formula["record_label"], "'=FORMULA")
        self.assertEqual(formula["value"], "'=FORMULA")
        nested = next(
            row
            for row in rows
            if row["section"] == "nba_dashboard" and row["field"] == "team_rows.team.pts"
        )
        self.assertEqual(nested["value"], "80")

    def test_export_rejects_invalid_requests(self):
        invalid_format = self.client.post(
            "/export-multi", json={"format": "pdf", "report": sample_report()}
        )
        missing_report = self.client.post("/export-multi", json={"format": "json"})
        malformed = self.client.post("/export-multi", data="not json", content_type="text/plain")
        malformed_report = sample_report()
        malformed_report["matches"] = "not-a-list"
        wrong_shape = self.client.post(
            "/export-multi", json={"format": "json", "report": malformed_report}
        )

        self.assertEqual(invalid_format.status_code, 400)
        self.assertEqual(missing_report.status_code, 400)
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(wrong_shape.status_code, 400)

    def test_export_rejects_oversized_request(self):
        with patch.object(web_tool, "MAX_MULTI_EXPORT_BYTES", 1):
            response = self.client.post(
                "/export-multi", json={"format": "json", "report": sample_report()}
            )
        self.assertEqual(response.status_code, 413)


if __name__ == "__main__":
    unittest.main()
