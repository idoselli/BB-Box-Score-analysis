import unittest

from bb_site import GameLogEntry, parse_available_seasons_from_html, parse_injury_days_from_html
from minutes_agg import aggregate_game_logs, overview_for_games


class MinutesAggTests(unittest.TestCase):
    def test_overview_counts_current_week_only(self):
        games = [
            GameLogEntry("5/3/2026", "SG", 40, "League"),  # S72 W1
            GameLogEntry("5/10/2026", "PG", 20, "League"),  # S72 W2
            GameLogEntry("5/3/2026", "SG", 10, "BBM"),
        ]
        overview = overview_for_games(games, season=72, current_week=1)
        self.assertEqual(overview["weekTotal"], 40)
        self.assertEqual(overview["seasonTotal"], 60)
        self.assertEqual(overview["weekMinutesByPosition"]["SG"], 40)
        self.assertEqual(overview["seasonMinutesByPosition"]["PG"], 20)

    def test_aggregate_assigns_preseason_to_w0_when_prev_missing(self):
        # 4/25/2026 is before S72 start (5/2/2026) and in S71 W14 window.
        games = [GameLogEntry("4/25/2026", "C", 30, "Friendly")]
        agg = aggregate_game_logs([{"season": 72, "games": games}])
        self.assertEqual(agg["minutesBySeasonWeekPosition"]["72"]["0"]["C"], 30)

    def test_parse_injury_and_seasons(self):
        injury_html = "Injury! Expected return in 3-6 days."
        self.assertEqual(parse_injury_days_from_html(injury_html), "3-6")
        seasons_html = """
        <select name="ctl00$cphContent$ddlSeasons">
          <option value="57">Season 57</option>
          <option value="72" selected>Season 72</option>
        </select>
        """
        self.assertEqual(parse_available_seasons_from_html(seasons_html), [57, 72])


if __name__ == "__main__":
    unittest.main()
