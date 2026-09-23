import unittest

from bb_site import (
    BBSiteClient,
    parse_game_log_html,
    parse_israel_u21_standings_games,
    parse_national_roster_players,
    parse_position_cell,
)


class GameLogParserTests(unittest.TestCase):
    def test_parse_israel_u21_standings_games_groups_and_deduplicates(self):
        html = """
        <b>World Cup - Pool A</b>
        <span id="cphContent_rptrPools_NTRR_0_rptrRecentMatches_0_rm_0_lblMatchString_0">
          <a href="/country/15/jnt/overview.aspx">Israel U21</a> vs.
          <a href="/country/12/jnt/overview.aspx">Hellas U21</a>
        </span>
        <a id="cphContent_rptrPools_NTRR_0_rptrRecentMatches_0_rm_0_hlLiveMatch_0"
           href="/match/86288/reportmatch.aspx">ראה שידור חי</a>
        <span id="cphContent_rptrPools_NTRR_0_rptrRecentMatches_0_rm_1_lblMatchString_1">France U21 vs. Italia U21</span>
        <a id="cphContent_rptrPools_NTRR_0_rptrRecentMatches_0_rm_1_hlLiveMatch_1"
           href="/match/86260/reportmatch.aspx">View Live!</a>
        <a id="cphContent_rptrPools_NTRR_0_rptrRecentMatches_0_rm_2_hlLiveMatch_2"
           href="/match/86260/reportmatch.aspx">Duplicate</a>
        <b>World Cup - Pool B</b>
        <span id="cphContent_rptrPools_NTRR_1_rptrRecentMatches_1_rm_0_lblMatchString_0">Srbija U21 vs. China U21</span>
        <a id="cphContent_rptrPools_NTRR_1_rptrRecentMatches_1_rm_0_hlLiveMatch_0"
           href="/match/not-a-number/reportmatch.aspx">Malformed</a>
        <a id="unrelated_hlLiveMatch_0" href="/match/999/reportmatch.aspx">Unrelated</a>
        """

        pools = parse_israel_u21_standings_games(html)

        self.assertEqual(
            pools,
            [
                {
                    "id": "0",
                    "label": "World Cup - Pool A",
                    "games": [
                        {"matchid": "86288", "label": "Israel U21 vs. Hellas U21"},
                        {"matchid": "86260", "label": "France U21 vs. Italia U21"},
                    ],
                },
                {"id": "1", "label": "World Cup - Pool B", "games": []},
            ],
        )

    def test_national_roster_parser_excludes_bookmarks_and_active_bids(self):
        html = """
        <a id="cphContent_Repeater1_HyperLink1_0" href="../../../player/100/overview.aspx">Roster Player</a>
        <a id="bbBookmarks_Player_0" href="/player/200/overview.aspx">Bookmarked Player</a>
        <a id="bbActiveBids_hlName" href="/player/300/overview.aspx">Auction Player</a>
        """

        players = parse_national_roster_players(html)

        self.assertEqual([(player.player_id, player.name) for player in players], [(100, "Roster Player")])

    def test_parse_game_log_row_with_rating_column(self):
        html = """
        <table>
          <tr>
            <td>5/9/2026</td><td>SG</td><td>49</td><td>1</td><td>2</td>
            <td>3</td><td>4</td><td>5</td><td>6</td><td>7</td><td>8</td>
            <td>9</td><td>10</td><td>11</td><td>7.5</td><td>League</td>
          </tr>
        </table>
        """

        rows = parse_game_log_html(html)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].date, "5/9/2026")
        self.assertEqual(rows[0].position, "SG")
        self.assertEqual(rows[0].minutes, 49)
        self.assertEqual(rows[0].game_type, "League")

    def test_parse_game_position_from_icon_attributes(self):
        self.assertEqual(parse_position_cell('<img src="/img/pos_pf.gif" alt="Power Forward">'), "PF")
        self.assertEqual(parse_position_cell('<img title="Small Forward" src="/img/sf.png">'), "SF")

    def test_parse_game_position_from_hebrew_text(self):
        self.assertEqual(parse_position_cell("פג"), "PG")
        self.assertEqual(parse_position_cell("שג"), "SG")
        self.assertEqual(parse_position_cell("ספ"), "SF")
        self.assertEqual(parse_position_cell("פפ"), "PF")
        self.assertEqual(parse_position_cell("ס"), "C")
        self.assertEqual(parse_position_cell("רכז"), "PG")
        self.assertEqual(parse_position_cell("קלעי"), "SG")
        self.assertEqual(parse_position_cell("סמול פורוורד"), "SF")
        self.assertEqual(parse_position_cell("פאוור פורוורד"), "PF")
        self.assertEqual(parse_position_cell("סנטר"), "C")

    def test_season_postback_rejects_wrong_returned_season(self):
        html = """
        <select name="ctl00$cphContent$ddlSeasons">
          <option value="71" selected>Season 71</option>
          <option value="72">Season 72</option>
        </select>
        """

        class FakeResponse:
            text = html

            def raise_for_status(self):
                return None

        class FakeSession:
            headers = {}

            def get(self, *args, **kwargs):
                return FakeResponse()

            def post(self, *args, **kwargs):
                return FakeResponse()

        client = BBSiteClient("u", "p")
        client.session = FakeSession()

        with self.assertRaisesRegex(ValueError, "returned season 71"):
            client.fetch_player_game_log(1, 72)


if __name__ == "__main__":
    unittest.main()
