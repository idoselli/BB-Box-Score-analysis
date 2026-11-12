"""Event-role semantics supplied by the owner; independent box-score reconciliation."""
import unittest
from copy import deepcopy

from beta_v1.events import analyze_events
from beta_v1.reconstruction import infer_roles, identities
from beta_v1.commentary_roles import sentence_roles


def fixture():
    teams=['home','away'];sides=[]
    for team in teams:
        players=[]
        for index in range(6):
            minutes=42 if team=='home' and index==0 else 6 if team=='home' and index==5 else 48 if index<5 else 0
            pos='pointGuard' if index in {0,5} else ('shootingGuard','smallForward','powerForward','center')[index-1]
            split=dict.fromkeys(('pointGuard','shootingGuard','smallForward','powerForward','center'),0);split[pos]=minutes
            players.append({'player':{'id':team+str(index),'firstName':team.title(),'lastName':str(index)},
                'minutes':minutes,'minutesByPosition':split,'position':'PointGuard' if minutes else None,
                'plusMinus':2 if team=='home' and index==0 else -2 if team=='home' and index==5 else 0,
                'assists':1 if team=='away' and index==1 else 0,'turnovers':1 if team=='home' and index==5 else 0,
                'fieldGoalsAttempts':1 if index==0 else 0,'fieldGoals':1 if index==0 else 0})
        sides.append({'teamId':team,'players':players})
    match={'teams':[{'teamId':'home','isHome':True,'score':2},{'teamId':'away','isHome':False,'score':2}]}
    events=[]
    def event(kind,period,clock,p1,p2,h=0,a=0,**kw):
        events.append(dict(sequenceIndex=len(events),eventType=kind,period=period,clock=clock,player1Id=p1,player2Id=p2,homePoints=h,awayPoints=a,**kw))
    for index in range(5):event('JumpBall',1,720,'home'+str(index),'away'+str(index))
    event('Shot',1,700,'home0','away0',2,0,shotType='Layup',shotResult='ShotMade')
    event('Substitution',4,360,'home5','home0',2,0,teamIndex=0,detail=1)
    # A free throw may retain the fouler after he has been substituted off.
    event('FreeThrow',4,350,'away0','home0',2,0,shotResult='FreeThrowMissed')
    event('Shot',4,300,'away0','away1',2,2,shotType='Layup',shotResult='ShotMadeAssist')
    event('Assist',4,300,'away1','away0',2,2)
    event('ReboundOut',4,200,'home5','away0',2,2,reboundType='Offensive')
    event('GameOver',4,0,'home5','away0',2,2)
    return events,match,{'teams':sides}


class ReconstructionTests(unittest.TestCase):
    def analyze(self):
        e,m,b=fixture();return analyze_events('test',e,m,b,'home')

    def test_actor_context_distinguishes_defender_and_passer(self):
        result=self.analyze();first,second=result['shots']
        self.assertEqual(first['resolvedDefenderId'],'away0')
        self.assertEqual(first['defenseState'],'defended')
        self.assertEqual(second['passerId'],'away1')
        self.assertEqual(second['defenseState'],'open')
        self.assertIsNone(second.get('resolvedDefenderId'))

    def test_blocked_assist_with_opposing_actor_recovers_defender(self):
        e,m,b=fixture();e[5]['shotResult']='ShotBlockedAssist'
        result=analyze_events('test',e,m,b,'home')
        self.assertEqual(result['shots'][0]['resolvedDefenderId'],'away0')
        self.assertIsNone(result['shots'][0]['passerId'])

    def test_reconstructed_descriptions_label_their_source(self):
        first,second=self.analyze()['shots']
        self.assertIn('Away 0 defending',first['playDescription'])
        self.assertIn('pass from Away 1',second['playDescription'])
        self.assertEqual(first['descriptionSource'],'normalized-play-by-play-facts')

    def test_lineup_seconds_onoff_clutch_and_roles_reconcile(self):
        x=self.analyze()['reconstruction']
        self.assertEqual(x['status'],'validated',x['reasons'])
        self.assertTrue(x['positionsValidated'])
        self.assertTrue(x['assistsValidated'])
        self.assertTrue(x['turnoversValidated'])
        self.assertEqual(x['players']['home0']['seconds'],42*60)
        self.assertEqual(x['players']['home5']['seconds'],6*60)
        self.assertEqual(x['players']['home0']['plusMinus'],2)
        self.assertEqual(x['players']['home5']['clutchPlusMinus'],-2)
        self.assertEqual(x['players']['home5']['clutchTurnovers'],1)
        self.assertEqual(x['players']['away1']['clutchAssists'],1)
        self.assertEqual(x['players']['home0']['teamOn'],{'a':1,'m':1})
        self.assertEqual(x['players']['home5']['teamOff'],{'a':1,'m':1})
        self.assertEqual(x['players']['home5']['teamDefOn'],{'a':1,'m':1})

    def test_missing_substitution_rejects_lineup_metrics(self):
        e,m,b=fixture();e=[x for x in e if x['eventType']!='Substitution']
        x=analyze_events('test',e,m,b,'home')['reconstruction']
        self.assertEqual(x['status'],'unavailable')
        self.assertTrue(x['reasons'])

    def test_validated_shots_capture_exact_defending_five(self):
        result=self.analyze();first,second=result['shots']
        self.assertTrue(first['lineupValidated'])
        self.assertEqual(set(first['defendingLineup']),{'away0','away1','away2','away3','away4'})
        self.assertIn('home5',second['defendingLineup'])
        self.assertNotIn('home0',second['defendingLineup'])

    def test_same_clock_substitution_uses_event_order_for_defending_five(self):
        e,m,b=fixture();e[6]['clock']=300;e[7]['clock']=300
        for index,minutes in [(0,43),(5,5)]:
            b['teams'][0]['players'][index]['minutes']=minutes
            b['teams'][0]['players'][index]['minutesByPosition']['pointGuard']=minutes
        result=analyze_events('test',e,m,b,'home')
        self.assertEqual(result['reconstruction']['status'],'validated')
        self.assertIn('home5',result['shots'][1]['defendingLineup'])
        self.assertNotIn('home0',result['shots'][1]['defendingLineup'])

    def test_failed_reanalysis_does_not_publish_stale_lineup_snapshots(self):
        e,m,b=fixture();analyze_events('test',e,m,b,'home')
        b['teams'][0]['players'][0]['plusMinus']=100
        result=analyze_events('test',e,m,b,'home')
        self.assertEqual(result['reconstruction']['status'],'unavailable')
        self.assertTrue(all('defendingLineup' not in shot and 'lineupValidated' not in shot for shot in result['shots']))

    def test_official_plusminus_disagreement_rejects_reconstruction(self):
        e,m,b=fixture();b['teams'][0]['players'][0]['plusMinus']=3
        self.assertEqual(analyze_events('test',e,m,b,'home')['reconstruction']['status'],'unavailable')

    def test_whole_minute_clock_difference_preserves_validated_onoff_counts(self):
        e,m,b=fixture()
        # 41:21 / 6:39, published as 42 / 6. The active fives and all player
        # field goals/plus-minus still reconcile; nearest-minute timing does not.
        e[6]['clock']=399
        x=analyze_events('test',e,m,b,'home')['reconstruction']
        self.assertEqual(x['status'],'validated',x['reasons'])
        self.assertFalse(x['timingValidated'])
        self.assertFalse(x['positionsValidated'])
        self.assertEqual(len(x['timingMismatches']),2)
        self.assertTrue(x['notes'])
        self.assertEqual(x['players']['home5']['teamDefOn'],{'a':1,'m':1})

    def test_whole_minute_tolerance_requires_independent_count_evidence(self):
        e,m,b=fixture();e[6]['clock']=399
        b['teams'][0]['players'][0]['plusMinus']=None
        self.assertEqual(analyze_events('test',e,m,b,'home')['reconstruction']['status'],'unavailable')

    def test_a_full_minute_disagreement_still_rejects_onoff(self):
        e,m,b=fixture();e[6]['clock']=420
        self.assertEqual(analyze_events('test',e,m,b,'home')['reconstruction']['status'],'unavailable')

    def test_clock_tolerance_does_not_hide_shooting_or_plusminus_errors(self):
        for field in ('fieldGoalsAttempts','plusMinus'):
            e,m,b=fixture();e[6]['clock']=399
            b['teams'][0]['players'][0][field]+=1
            self.assertEqual(analyze_events('test',e,m,b,'home')['reconstruction']['status'],'unavailable')

    def test_assist_disagreement_does_not_invent_clutch_assists(self):
        e,m,b=fixture();b['teams'][1]['players'][1]['assists']=2
        x=analyze_events('test',e,m,b,'home')['reconstruction']
        self.assertFalse(x['assistsValidated'])
        self.assertEqual(x['players']['away1']['clutchAssists'],0)

    def test_assist_uses_pre_shot_margin(self):
        e,m,b=fixture();shot=e[-4];shot['homePoints']=9;shot['awayPoints']=2
        shot['clutch']=True;assist=e[-3];assist['clutch']=False
        infer_roles(e,b)
        self.assertTrue(assist['clutch'])
        self.assertEqual(assist['linkedShotSequence'],shot['sequenceIndex'])

    def test_explicit_api_attribution_takes_precedence(self):
        e,m,b=fixture();e[-4]['primaryDefenderId']='home1'
        result=analyze_events('test',e,m,b,'home')
        self.assertEqual(result['shots'][1]['resolvedDefenderId'],'home1')
        self.assertEqual(result['shots'][1]['defenderSource'],'api')

    def test_defense_wrappers_from_supplied_catalog(self):
        _,_,box=fixture();players=identities(box)
        for sentence in ['Home 0 attempts a baseline jumper, guarded closely by Away 0.',
                         'Home 0 attempts a baseline jumper with Away 0 right in his face.',
                         'Home 0 attempts a baseline jumper under pressure from Away 0.',
                         'Home 0 attempts a baseline jumper after Away 0 backed off slightly.',
                         'Home 0 attempts a baseline jumper over Away 0.',
                         'Home 0 attempts a baseline jumper, as Away 0 rotates over and alters his shot.']:
            rule=sentence_roles({'text':sentence,'player1Id':'home0'},players)
            self.assertEqual(rule['state'],'defended',sentence)
            self.assertEqual(rule['defenderId'],'away0',sentence)

    def test_complete_shot_sentence_without_defender_is_open(self):
        _,_,box=fixture();players=identities(box)
        rule=sentence_roles({'text':'Home 0 attempts a baseline jumper. Shot missed.','player1Id':'home0'},players)
        self.assertEqual(rule['state'],'open')
        self.assertIsNone(sentence_roles({'text':'Shot missed.','player1Id':'home0'},players))

    def test_passing_wrapper_is_not_a_defender(self):
        _,_,box=fixture();players=identities(box)
        rule=sentence_roles({'text':'Home 1 finds Home 0 in space. Home 0 attempts a baseline jumper.','player1Id':'home0'},players)
        self.assertEqual(rule['state'],'open')
        self.assertEqual(rule['passerId'],'home1')


if __name__=='__main__':unittest.main()
