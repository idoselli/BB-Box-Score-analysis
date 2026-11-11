"""Production contract regressions: cursor feeds, coverage, filters and shooting totals."""
import unittest
from unittest.mock import patch

import web_tool
from beta_v1 import reports
from beta_v1.api import API_BASE, V1ApiError
from beta_v1.auth import AUTHORIZE_URL
from beta_v1.events import analyze_events, read_events
from test_beta_v1 import FakeClient, MATCH_ID, TEAM_ID, OTHER_ID, PLAYER_ID


class ProductionReportTests(unittest.TestCase):
    def fixtures(self):
        split = dict.fromkeys(reports.POSITIONS, 0)
        split.update(pointGuard=20, shootingGuard=10)
        line = {'player': {'id': PLAYER_ID, 'firstName': 'Test', 'lastName': 'Guard'},
                'minutes': 30, 'minutesByPosition': split, 'points': 5, 'fieldGoals': 2,
                'fieldGoalsAttempts': 4, 'threePointFieldGoals': 1, 'threePointFieldGoalsAttempts': 2}
        box = {'matchId': MATCH_ID, 'effortDelta': -1, 'teams': [
            {'teamId': TEAM_ID, 'players': [line], 'ratings': {'offenseStrategy': 'Motion', 'sublevels': {'outsideScoring': 'High'}, 'predictionFocusCorrect': False}, 'pp100': {'pointGuard': 98.5}},
            {'teamId': OTHER_ID, 'players': [], 'ratings': {}}]}
        match = {'id': MATCH_ID, 'boxScore': box, 'teams': [
            {'teamId': TEAM_ID, 'name': 'Team', 'isHome': False, 'score': 5},
            {'teamId': OTHER_ID, 'name': 'Opponent', 'isHome': True, 'score': 3}]}
        fake = FakeClient({f'/matches/{MATCH_ID}': match,
                           f'/matches/{MATCH_ID}/shooting': {'sides': []},
                           f'/matches/{MATCH_ID}/events': {'events': [], 'totalEvents': 0, 'nextCursor': None}})
        return fake, match, box, line

    def test_export_zip_and_combined_csv_preserve_nested_values_and_escape_formulas(self):
        import io
        import zipfile
        fake, _, _, line = self.fixtures()
        line['player']['firstName'] = '=malicious'
        report = reports.build_report(fake, [MATCH_ID], TEAM_ID)
        client = web_tool.app.test_client()
        response = client.post('/beta/export-multi', json={'format': 'csv_zip', 'report': report})
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            self.assertIn('events.csv', archive.namelist())
            players = archive.read('players.csv').decode('utf-8-sig')
            self.assertIn("'=malicious", players)
            self.assertIn('minutesByPosition.pointGuard', players)
        response = client.post('/beta/export-multi', json={'format': 'csv_combined', 'report': report})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'minutesByPosition.pointGuard', response.data)

    def test_production_hosts(self):
        self.assertEqual(API_BASE, 'https://next-api.buzzerbeater.com/v1')
        self.assertEqual(AUTHORIZE_URL, 'https://play.buzzerbeater.com/oauth/authorize')

    def test_expansion_position_splits_rates_and_home_effort(self):
        fake, _, _, _ = self.fixtures()
        result = reports.build_report(fake, [MATCH_ID, MATCH_ID], TEAM_ID)
        self.assertEqual(result['usedMatches'], 1)
        self.assertEqual(result['players'][0]['minutesByPosition']['shootingGuard'], 10)
        self.assertEqual(result['players'][0]['efgPercent'], 62.5)
        self.assertEqual(result['matches'][0]['effortDelta'], -1)
        self.assertNotIn(f'/matches/{MATCH_ID}/boxscore', [path for path, _ in fake.calls])
        self.assertNotIn('sublevels', result['ratingDistributions'])
        self.assertEqual(result['ratingDistributions']['predictionFocusCorrect'], {'False': 1})

    def test_filters_run_before_advanced_reads(self):
        fake, _, _, _ = self.fixtures()
        with self.assertRaises(ValueError):
            reports.build_report(fake, [MATCH_ID], TEAM_ID, result_filter='L')
        self.assertEqual(len(fake.calls), 1)

    def test_missing_splits_are_not_guessed_from_position(self):
        fake, _, _, line = self.fixtures()
        line['minutesByPosition'] = None
        line['position'] = 'PointGuard'
        p = reports.build_report(fake, [MATCH_ID], TEAM_ID)['players'][0]
        self.assertEqual(p['minutesByPosition']['pointGuard'], 0)
        self.assertEqual(p['missingPositionMinutesGames'], 1)

    def test_denied_advanced_reads_keep_boxscore(self):
        fake, _, _, _ = self.fixtures()
        original = fake.get
        def get(path, params=None):
            if path.endswith(('/shooting', '/events')):
                raise V1ApiError(403, 'SupporterRequired', 'Supporter required')
            return original(path, params)
        fake.get = get
        result = reports.build_report(fake, [MATCH_ID], TEAM_ID)
        self.assertEqual(result['usedMatches'], 1)
        self.assertIsNone(result['shooting'])
        self.assertEqual(result['eventCoverageGames'], 0)
        self.assertTrue(any('SupporterRequired' in w for w in result['warnings']))

    def test_shooting_zones_not_double_counted_and_weighted_totals(self):
        side = {'zones': [{'zone': 'Baseline', 'shots': {'made': 1, 'attempts': 2, 'points': 2}}],
                'sideZones': [{'zone': 'Baseline', 'side': 'Left', 'shots': {'made': 1, 'attempts': 2, 'points': 2}}]}
        total = reports.shooting_totals([side, side])
        self.assertEqual(total['zones'][0]['shots']['attempts'], 4)
        self.assertEqual(total['sideZones'][0]['shots']['attempts'], 4)
        self.assertIsNone(reports.shooting_totals([]))

    def test_real_report_renders_with_new_fields(self):
        fake, _, _, _ = self.fixtures()
        with patch('beta_v1.routes._connection', return_value=(fake, {}, '')), patch('beta_v1.routes.tracker._read', return_value={'teams': [{'countryId': 'IL', 'name': 'Israel'}]}):
            response = web_tool.app.test_client().post('/beta/multi-match', data={'match_ids': MATCH_ID})
        self.assertEqual(response.status_code, 200)
        for label in [b'Tactic Position Minutes', b'Play-by-play result', b'Defended shot log', b'62.5']:
            self.assertIn(label, response.data)


class PublicEventTests(unittest.TestCase):
    def test_cursor_pages_preserve_sequence(self):
        fake = FakeClient({f'/matches/{MATCH_ID}/events': lambda params: {
            'totalEvents': 3, 'nextCursor': 2 if params['cursor'] == 0 else None,
            'events': [{'sequenceIndex': i} for i in ([0, 1] if params['cursor'] == 0 else [2])]}})
        self.assertEqual(len(read_events(fake, MATCH_ID)), 3)
        self.assertEqual([params['cursor'] for _, params in fake.calls], [0, 2])

    def test_bad_pagination_is_rejected(self):
        fake = FakeClient({f'/matches/{MATCH_ID}/events': {'events': [], 'totalEvents': 1, 'nextCursor': 0}})
        with self.assertRaises(V1ApiError):
            read_events(fake, MATCH_ID)
        fake.responses[f'/matches/{MATCH_ID}/events'] = {'events': [], 'totalEvents': 1, 'nextCursor': None}
        with self.assertRaises(V1ApiError):
            read_events(fake, MATCH_ID)

    def test_foul_misses_and_explicit_defenders_and_preplay_clutch_margin(self):
        _, match, box, _ = ProductionReportTests().fixtures()
        base = {'eventType': 'Shot', 'player1Id': PLAYER_ID, 'player2Id': OTHER_ID, 'period': 4, 'clock': 100, 'homePoints': 0, 'awayPoints': 0, 'shotType': 'WingThree'}
        rows = [dict(base, sequenceIndex=0, shotResult='ShotMissedAssistFoul'),
                dict(base, sequenceIndex=1, shotResult='ShotMadeAssist', primaryDefenderId=OTHER_ID, awayPoints=3)]
        result = analyze_events(MATCH_ID, rows, match, box, TEAM_ID)
        self.assertFalse(result['shots'][0]['countsAsAttempt'])
        self.assertEqual(result['shots'][1]['points'], 3)
        self.assertEqual(len(result['matchups']), 1)
        self.assertEqual(result['defenderCoverage'], {'known': 1, 'shots': 2})
        self.assertTrue(result['shots'][1]['clutch'])
        self.assertEqual(len(result['ownShots']), 2)


if __name__ == '__main__':
    unittest.main()
