import unittest

from bb_site import BBSiteClient, parse_game_log_html, parse_position_cell


class GameLogParserTests(unittest.TestCase):
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
