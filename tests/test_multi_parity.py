"""Aggregate parity checks using API facts, including opponent/unknown identities."""
import unittest
from copy import deepcopy
from unittest.mock import patch

from beta_v1.events import analyze_events
from beta_v1.multi_view import presentation, render_report
from beta_v1.reports import build_report
import test_new_site
from test_beta_v1 import MATCH_ID, TEAM_ID, OTHER_ID, PLAYER_ID

OPPONENT_PLAYER = '0196861a-a33e-71f0-be2a-e63d57e331fe'


class MultiParityTests(unittest.TestCase):
    def report(self):
        fake, match, box, line = test_new_site.ProductionReportTests().fixtures()
        box['teams'][1]['players'] = [{'player':{'id':OPPONENT_PLAYER,'firstName':'Opponent','lastName':'Center'},
                                       'minutes':48,'fieldGoalsAttempts':1}]
        shot = {'sequenceIndex':0,'eventType':'Shot','period':4,'clock':120,'homePoints':0,'awayPoints':0,
                'player1Id':OPPONENT_PLAYER,'player2Id':PLAYER_ID,'primaryDefenderId':PLAYER_ID,
                'shotType':'Layup','shotResult':'ShotMissed','contestLevel':'Contested'}
        fake.responses[f'/matches/{MATCH_ID}/events'] = {'events':[shot], 'nextCursor':None,'totalEvents':1}
        return build_report(fake,[MATCH_ID],TEAM_ID)

    def test_missing_event_name_is_recovered_once_via_public_player(self):
        fake, match, box, line = test_new_site.ProductionReportTests().fixtures()
        e = {'sequenceIndex':0,'eventType':'Shot','period':1,'clock':300,'homePoints':0,'awayPoints':0,
             'player1Id':PLAYER_ID,'player2Id':OPPONENT_PLAYER,'shotType':'Layup','shotResult':'ShotMissed'}
        fake.responses[f'/matches/{MATCH_ID}/events'] = {'events':[e],'nextCursor':None,'totalEvents':1}
        fake.responses[f'/players/{OPPONENT_PLAYER}'] = {'firstName':'Recovered','lastName':'Player'}
        report = build_report(fake,[MATCH_ID],TEAM_ID)
        self.assertEqual(report['events'][0]['player2Name'],'Recovered Player')
        self.assertEqual(sum(path==f'/players/{OPPONENT_PLAYER}' for path,_ in fake.calls),1)

    def test_ambiguous_common_team_uses_named_chooser(self):
        import web_tool
        fake, match, box, line = test_new_site.ProductionReportTests().fixtures()
        second_id = '99999999-1111-4111-8111-111111111111'
        second = deepcopy(match)
        second['id'] = second_id
        fake.responses[f'/matches/{second_id}'] = second
        with patch('beta_v1.routes._connection',return_value=(fake,{},'')), patch('beta_v1.routes.tracker._read',return_value={'teams':[{'countryId':'IL','name':'Israel'}]}):
            response = web_tool.app.test_client().post('/beta/multi-match',data={'match_ids':MATCH_ID+' '+second_id})
        self.assertEqual(response.status_code,200)
        self.assertIn(b'Choose a team',response.data)
        self.assertIn('Team · 2 games'.encode(),response.data)
        self.assertIn('Opponent · 2 games'.encode(),response.data)

    def test_equal_names_keep_separate_dashboard_identities(self):
        report = self.report()
        duplicate = deepcopy(report['matches'][0]['playerLines'][0])
        duplicate['player']['id'] = OPPONENT_PLAYER
        report['matches'][0]['playerLines'].append(duplicate)
        report['matches'][0]['opponentPlayerLines'] = []
        view = presentation(report)
        rows = view['nba_dashboard']['players']
        self.assertEqual(len(rows),2)
        self.assertNotEqual(rows[0]['name'],rows[1]['name'])
        self.assertEqual({row['playerId'] for row in rows},{PLAYER_ID,OPPONENT_PLAYER})

    def test_opponents_and_events_have_names_from_both_sides(self):
        report = self.report()
        self.assertEqual(report['playerNames'][OPPONENT_PLAYER],'Opponent Center')
        self.assertEqual(report['events'][0]['player1Name'],'Opponent Center')
        self.assertEqual(report['events'][0]['defenderName'],'Test Guard')
        view = presentation(report)
        self.assertEqual(view['defended_shots']['events'][0]['shooter'],'Opponent Center')
        self.assertEqual(view['defense'][0]['defendedTotal'],{'a':1,'m':0})

    def test_unresolved_ids_are_never_display_names(self):
        report = self.report()
        event = deepcopy(report['events'][0])
        event['player2Id'] = 'unknown-opaque-id'
        box = {'teams':[]}
        result = analyze_events(MATCH_ID,[event],{'teams':[]},box,TEAM_ID,{PLAYER_ID:{'name':'Test Guard'}})
        self.assertEqual(result['events'][0]['player2Name'],'Unknown player')
        self.assertEqual(result['events'][0]['player2Id'],'unknown-opaque-id')

    def test_grouped_role_minutes_omit_zero_entries(self):
        report = self.report()
        view = presentation(report)
        outside = next(g for g in view['tactic_minutes'] if g['key']=='outside')
        self.assertEqual(outside['positions'][0]['players'][0]['mins'],20)
        self.assertEqual(outside['positions'][1]['players'][0]['mins'],10)
        self.assertEqual(outside['positions'][2]['players'],[])
        self.assertTrue(all(p['mins']>0 for g in view['tactic_minutes'] for pos in g['positions'] for p in pos['players']))

    def test_absent_defender_never_becomes_open_or_defended(self):
        report = self.report()
        for e in report['eventReports'][0]['shots']:
            e.pop('primaryDefenderId',None)
            e.pop('contestLevel',None)
            e.pop('resolvedDefenderId',None)
            e.pop('defenderSource',None)
            e.pop('inferredDefenderId',None)
            e.pop('defenseState',None)
        view = presentation(report)
        self.assertIsNone(view['matchup'][0]['openTotal'])
        self.assertIsNone(view['matchup'][0]['teamOn'])
        self.assertIsNone(view['defense'][0]['defendedTotal'])
        self.assertEqual(view['defended_shots']['events'],[])

    def test_offense_attempts_exclude_missed_shooting_fouls(self):
        report = self.report()
        shot = dict(report['eventReports'][0]['shots'][0],player1Id=PLAYER_ID,shotType='WingThree',
                    countsAsAttempt=True,made=True,shotResult='ShotMadeAssist',points=3)
        foul = dict(shot,countsAsAttempt=False,made=False,shotResult='ShotMissedFoul',points=0)
        report['eventReports'][0]['shots'] = [shot,foul]
        view = presentation(report)
        self.assertEqual(view['offense']['players'][0]['total'],{'a':1,'m':1,'mi':0,'b':0})
        self.assertEqual(view['matchup'][0]['withPass']['a']+view['matchup'][0]['withoutPass']['a'],1)

    def test_clutch_free_throw_points_and_fg_are_separate(self):
        report = self.report()
        report['eventReports'][0]['shots'] = [dict(report['eventReports'][0]['shots'][0],player1Id=PLAYER_ID,
                    shotType='Layup',countsAsAttempt=True,made=True,shotResult='ShotMade',points=2)]
        report['eventReports'][0]['events'] = [{'eventType':'FreeThrow','player1Id':PLAYER_ID,'clutch':True,'shotResult':'FreeThrowMade'}]
        view = presentation(report)
        row = view['nba_dashboard']['players'][0]
        self.assertEqual(row['clutch']['pts'],3)
        self.assertEqual(row['clutch']['fga'],1)

    def test_production_report_uses_legacy_structure_and_escapes_labels(self):
        import web_tool
        report = self.report()
        report['playerNames'][PLAYER_ID] = '<img src=x onerror=alert(1)>'
        with web_tool.app.test_request_context('/beta/multi-match'):
            html = render_report(report,{},'Manager')
        for label in ['Tactic Position Minutes','Player Matchup Overview','Player Defense Overview','NBA-Style Dashboard','Detections &amp; Suggestions','Offense Shot Profile By Player']:
            self.assertIn(label,html)
        self.assertNotIn('<img src=x onerror=alert(1)>',html)
        self.assertIn('/static/new-multi-report.css',html)
        self.assertIn('/static/legacy-beta-theme.css',html)
        self.assertNotIn('name="password"',html)
        self.assertIn('/beta/export-multi',html)

    def mixed_onoff_report(self):
        report=self.report()
        second=deepcopy(report['matches'][0]);second['matchId']='99999999-1111-4111-8111-111111111111'
        report['matches'].append(second);report['usedMatches']=2
        r={'status':'validated','positionsValidated':False,'timingValidated':False,
           'players':{PLAYER_ID:{'seconds':1790,'teamOn':{'m':4,'a':10},'teamOff':{'m':2,'a':5},
                                 'teamDefOn':{'m':3,'a':8},'teamDefOff':{'m':1,'a':4}}}}
        report['eventReports'][0]['reconstruction']=r
        report['eventReports'].append({'matchId':second['matchId'],'reconstruction':{'status':'unavailable'}})
        return report

    def test_one_invalid_match_preserves_explicitly_partial_onoff(self):
        report=self.mixed_onoff_report();view=presentation(report)
        offense=view['matchup'][0];defense=view['defense'][0]
        self.assertEqual(offense['teamOn'],{'m':4,'a':10})
        self.assertEqual(offense['teamOff'],{'m':2,'a':5})
        self.assertEqual(defense['teamDefOn'],{'m':3,'a':8})
        self.assertEqual(defense['teamDefOff'],{'m':1,'a':4})
        for row in (offense,defense):
            self.assertEqual((row['onoff_games'],row['onoff_total']),(1,2))
            self.assertFalse(row['lineup_valid'])
            self.assertEqual(row['onoff_missing'],[report['matches'][1]['matchId']])
        nba=view['nba_dashboard']['players']
        self.assertEqual([r['onoff_games'] for r in nba],[1,0])
        self.assertEqual(nba[1]['team_def_on'],{'m':0,'a':0})

    def test_unconfirmed_clock_timing_retains_official_minutes(self):
        report=self.mixed_onoff_report();view=presentation(report)
        self.assertEqual(view['nba_dashboard']['players'][0]['mins'],report['matches'][0]['playerLines'][0]['minutes'])
        self.assertEqual(view['player_summary'][0]['mins'],report['players'][0]['minutes'])

    def test_no_valid_matches_keeps_onoff_unavailable_with_zero_coverage(self):
        view=presentation(self.report())
        self.assertIsNone(view['matchup'][0]['teamOn'])
        self.assertEqual(view['matchup'][0]['onoff_games'],0)
        self.assertEqual(view['matchup'][0]['onoff_total'],1)


if __name__=='__main__':
    unittest.main()
