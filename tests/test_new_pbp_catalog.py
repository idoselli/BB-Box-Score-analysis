"""New-site catalog variants, compound actor roles, and statistical boundaries."""
from copy import deepcopy
import unittest

from beta_v1.events import analyze_events
from beta_v1.pbp_catalog import catalog, category, sentence_facts, normalize
from beta_v1.reconstruction import identities
from test_reconstruction import fixture


class NewPbpCatalogTests(unittest.TestCase):
    def setUp(self):
        self.events,self.match,self.box=fixture()
        names={'home0':("D'Andre",'O’Neal'),'home1':('José','van Dijk'),
               'away0':('Dr. A.','Defender'),'away1':('Tim','Helper')}
        for side in self.box['teams']:
            for line in side['players']:
                p=line['player']
                if p['id'] in names:p['firstName'],p['lastName']=names[p['id']]
        self.players=identities(self.box)

    def text(self,template,p1='home0',p2='away0'):
        def name(pid):
            p=self.players[pid][1]['player'];return p['firstName']+' '+p['lastName']
        values={'p1':name(p1),'p2':name(p2),'team':'Home Team','opp':'Away Team',
                'n':'2','m':'3','a':'90','b':'89','pts':'20','secs':'4','run':'8-0'}
        for key,value in values.items():template=template.replace('%{'+key+'}',value).replace('{'+key+'}',value)
        return template

    def shot(self,text,p2=None,**kwargs):
        return dict(eventType='Shot',player1Id='home0',player2Id=p2,text=text,**kwargs)

    def test_every_new_shot_variant_identifies_shooter_outcome_and_actor(self):
        checked=0
        for key,value in catalog().items():
            if not key.startswith(('playByPlay.made.','playByPlay.missed.')):continue
            p2='home1' if key.endswith('Assist') else 'away0'
            for template in value.split(' | '):
                with self.subTest(template=template):
                    facts=sentence_facts(self.shot(self.text(template,p2=p2),p2),self.players)
                    self.assertTrue(facts.get('shotComplete'),facts)
                    self.assertEqual(facts['shooterId'],'home0')
                    self.assertEqual(facts['made'],key.startswith('playByPlay.made.'))
                    if key.endswith('Assist'):self.assertEqual(facts['passerId'],'home1')
                    if key.endswith('blocked'):
                        self.assertEqual(facts['defenderId'],'away0');self.assertTrue(facts['blocked'])
                    checked+=1
        self.assertGreaterEqual(checked,90)

    def test_every_guard_and_help_variant_resolves_opposing_player(self):
        for key in ('playByPlay.guarded','playByPlay.helped'):
            for template in catalog()[key].split(' | '):
                facts=sentence_facts(self.shot(self.text(template),'away0'),self.players)
                self.assertEqual(facts['helpDefenderId' if key.endswith('helped') else 'defenderId'],'away0',template)

    def test_compound_shot_keeps_passer_defender_and_helper(self):
        text=self.text(catalog()['playByPlay.made.threeAssist'].split(' | ')[0],p2='home1')
        text+=' '+self.text('Guarded closely by {p2}.',p2='away0')
        text+=' '+self.text(catalog()['playByPlay.helped'],p2='away1')
        e=self.events[5];e.update(text=text,player2Id='home1')
        shot=analyze_events('m',self.events,self.match,self.box,'home')['shots'][0]
        self.assertEqual(shot['passerId'],'home1')
        self.assertEqual(shot['resolvedDefenderId'],'away0')
        self.assertEqual(shot['inferredHelpDefenderId'],'away1')
        self.assertTrue(shot['isHelped'])
        self.assertEqual(shot['defenseState'],'defended')
        self.assertEqual(shot['shotType'],'Layup')  # API type stays authoritative.

    def test_explicit_api_defender_does_not_discard_teammate_passer(self):
        self.events[5].update(player2Id='home1',primaryDefenderId='away0')
        shot=analyze_events('m',self.events,self.match,self.box,'home')['shots'][0]
        self.assertEqual(shot['resolvedDefenderId'],'away0')
        self.assertEqual(shot['passerId'],'home1')

    def test_linked_assist_recovers_passer_when_second_actor_is_defender(self):
        self.events[-4].update(player2Id='home0')
        result=analyze_events('m',self.events,self.match,self.box,'home')
        shot=result['shots'][1]
        self.assertEqual(shot['resolvedDefenderId'],'home0')
        self.assertEqual(shot['passerId'],'away1')
        self.assertEqual(shot['passerSource'],'linked-assist-event')
        self.assertTrue(result['reconstruction']['assistsValidated'])

    def test_unknown_named_defender_is_not_open_or_guessed_from_passer(self):
        text=self.text('{p2} threads the needle, {p1} lays it in.',p2='home1')+' Guarded closely by Missing Defender.'
        e=self.events[5];e.update(text=text,player2Id='home1')
        shot=analyze_events('m',self.events,self.match,self.box,'home')['shots'][0]
        self.assertEqual(shot['defenseState'],'unknown')
        self.assertIsNone(shot['resolvedDefenderId'])
        self.assertEqual(shot['passerId'],'home1')

    def test_opponent_in_pass_template_is_never_a_passer(self):
        facts=sentence_facts(self.shot(self.text('{p2} lobs it, {p1} slams it home!'),'away0'),self.players)
        self.assertNotIn('passerId',facts)

    def test_unresolved_passer_does_not_turn_an_explicit_pass_into_no_pass(self):
        self.events[5].update(text=self.text('Missing Teammate lobs it, {p1} slams it home!'),player2Id=None)
        shot=analyze_events('m',self.events,self.match,self.box,'home')['shots'][0]
        self.assertTrue(shot['receivedPass'])
        self.assertIsNone(shot['passerId'])
        self.assertIn('passer',shot['pbpFacts']['unresolvedRoles'])

    def test_generic_defender_and_celebrity_names_are_not_attributed(self):
        for key in ('playByPlay.made.dunk','playByPlay.made.post','playByPlay.made.layup'):
            for template in catalog()[key].split(' | '):
                facts=sentence_facts(self.shot(self.text(template)),self.players)
                self.assertNotIn('defenderId',facts,template)
                self.assertNotIn('defender',facts['unresolvedRoles'],template)

    def test_every_substitution_variant_recovers_position_and_both_players(self):
        for key,value in catalog().items():
            if not key.startswith('playByPlay.lineup.'):continue
            for template in value.split(' | '):
                e={'eventType':'SubstitutionSwap' if key.endswith('swap') else 'Substitution',
                   'player1Id':'home5','player2Id':'home0','text':self.text(template,'home5','home0')}
                facts=sentence_facts(e,self.players)
                self.assertEqual(facts['player1Id'],'home5',template)
                self.assertEqual(facts['player2Id'],'home0',template)
                if not key.endswith('swap'):self.assertIn('position',facts)

    def test_substitution_text_repairs_missing_detail_without_changing_counts(self):
        self.events[6].update(detail=None,text=self.text('{p1} checks in for {p2} at point guard.','home5','home0'))
        result=analyze_events('m',self.events,self.match,self.box,'home')
        self.assertEqual(result['reconstruction']['status'],'validated')
        self.assertTrue(result['reconstruction']['positionsValidated'])
        self.assertEqual(result['events'][6]['detail'],1)
        self.assertIn('detail',result['events'][6]['pbpInferredFields'])

    def test_every_turnover_and_steal_variant_uses_correct_actor(self):
        event_types={'backCourt':'BackCourtViol','badPass':'BadPass','lostHandle':'LoseControl',
                     'offensiveFoul':'OffFoul','shotClock':'ShotClockZero','tenSeconds':'TenSecViol',
                     'threeSeconds':'ThreeSecond','travel':'Travel'}
        for key,value in catalog().items():
            if not key.startswith('playByPlay.turnover.') and key!='playByPlay.steal':continue
            steal=key=='playByPlay.steal'
            p1,p2=('away0','home0') if steal else ('home0','away0')
            for template in value.split(' | '):
                facts=sentence_facts({'eventType':'Steal' if steal else event_types[key.rsplit('.',1)[1]],
                                     'player1Id':p1,'player2Id':p2,'text':self.text(template,p1,p2)},self.players)
                self.assertEqual(facts['turnoverPlayerId'],'home0',template)
                if steal:self.assertEqual(facts['stealerId'],'away0')

    def test_every_rebound_variant_keeps_offensive_and_defensive_roles_separate(self):
        for key,value in catalog().items():
            if not key.startswith('playByPlay.rebound.'):continue
            for template in value.split(' | '):
                facts=sentence_facts({'eventType':'Rebound','player1Id':'home0','text':self.text(template)},self.players)
                self.assertEqual(facts['rebounderId'],'home0',template)
                self.assertEqual(facts['reboundType'],'Offensive' if key.endswith('offensive') else 'Defensive')

    def test_every_foul_variant_keeps_fouler_separate_from_primary_defender(self):
        for key,value in catalog().items():
            if category(key)!='foul':continue
            for template in value.split(' | '):
                facts=sentence_facts(self.shot(self.text(template),'away0'),self.players)
                self.assertNotIn('defenderId',facts,template)
                if '{p2}' in template:self.assertEqual(facts['foulerId'],'away0',template)
                if key=='playByPlay.andOne':self.assertTrue(facts['andOne'])

    def test_free_throw_summaries_flavor_and_commentary_do_not_create_attempts(self):
        for key,value in catalog().items():
            if category(key) not in {'free-throw-summary','flavor','broadcast'}:continue
            for template in value.split(' | '):
                e=self.shot(self.text(template),isCommentary=True,shotResult='ShotMade')
                self.assertEqual(sentence_facts(e,self.players),{},key)
        extra=deepcopy(self.events[5]);extra.update(sequenceIndex=5,isCommentary=True,text=self.text(catalog()['playByPlay.made.dunk'].split(' | ')[0]))
        self.events.insert(6,extra)
        result=analyze_events('m',self.events,self.match,self.box,'home')
        self.assertEqual(len(result['shots']),2)
        self.assertTrue(result['reconstruction']['assistsValidated'])
        self.assertEqual(result['reconstruction']['status'],'validated')

    def test_actual_text_is_preserved_and_missing_shot_facts_have_provenance(self):
        text=self.text('{p2} finds {p1} wide open, and it\'s a triple!',p2='home1')
        self.events[5].update(text=text,shotResult=None,shotType=None,player2Id='home1')
        shot=analyze_events('m',self.events,self.match,self.box,'home')['shots'][0]
        self.assertEqual(shot['playDescription'],text)
        self.assertEqual(shot['descriptionSource'],'recorded-play-by-play-text')
        self.assertEqual(shot['points'],3)
        self.assertEqual(shot['shotType'],'GenericThree')
        self.assertEqual(set(shot['pbpInferredFields']),{'shotType','shotResult'})
        self.assertEqual(shot['defenseState'],'open')

    def test_contested_api_shot_is_not_also_classified_open_by_its_sentence(self):
        self.events[5].update(text=self.text('{p1} pulls up and nails the jumper.'),contestLevel='Contested')
        shot=analyze_events('m',self.events,self.match,self.box,'home')['shots'][0]
        self.assertEqual(shot['defenseState'],'defended')
        self.assertEqual(shot['resolvedDefenderId'],'away0')

    def test_fouled_miss_text_does_not_become_a_field_goal_attempt(self):
        self.events[5].update(text=self.text('{p1} misses the jumper. Whistle: foul by {p2} on the shot.'),shotResult=None)
        shot=analyze_events('m',self.events,self.match,self.box,'home')['shots'][0]
        self.assertEqual(shot['shotResult'],'ShotMissedFoul')
        self.assertFalse(shot['countsAsAttempt'])
        self.assertEqual(shot['points'],0)

    def test_free_throw_result_variants_recover_one_attempt_only_in_free_throw_context(self):
        for key,value in catalog().items():
            if category(key)!='free-throw-result':continue
            for template in value.split(' | '):
                e={'eventType':'FreeThrow','player1Id':'home0','text':self.text(template)}
                facts=sentence_facts(e,self.players)
                self.assertEqual(facts['freeThrowMade'],'.made.' in key,template)
                self.assertNotIn('shotComplete',facts)
                self.assertEqual(sentence_facts(self.shot(self.text(template)),self.players),{},template)
        self.events[-5].update(shotResult=None,text='No good.')
        result=analyze_events('m',self.events,self.match,self.box,'home')
        self.assertEqual(result['events'][-5]['shotResult'],'FreeThrowMissed')
        self.assertEqual(len(result['shots']),2)

    def test_free_throw_summaries_never_recover_a_free_throw_result(self):
        for key,value in catalog().items():
            if category(key)!='free-throw-summary':continue
            for template in value.split(' | '):
                self.assertEqual(sentence_facts({'eventType':'FreeThrow','player1Id':'home0','text':self.text(template)},self.players),{},template)

    def test_assist_milestone_is_not_a_new_passer_or_assist(self):
        e=self.shot(self.text(catalog()['commentary.tag.assists.raised'],p2='home1'))
        self.assertEqual(sentence_facts(e,self.players),{})

    def test_duplicate_names_require_unambiguous_actor_context(self):
        twin=self.box['teams'][1]['players'][1]['player']
        twin.update(firstName='Dr. A.',lastName='Defender')
        self.players=identities(self.box)
        e=self.shot(self.text('Guarded closely by {p2}.'))
        self.assertNotIn('defenderId',sentence_facts(e,self.players))
        e['player2Id']='away1'
        self.assertEqual(sentence_facts(e,self.players)['defenderId'],'away1')

    def test_unicode_punctuation_and_prefix_names_match_correctly(self):
        self.box['teams'][1]['players'][1]['player'].update(firstName='Dr. A.',lastName='Defender Junior')
        self.players=identities(self.box)
        text=self.text('{p1} launches from another zip code, and it drops!')+' '+self.text('Under pressure from {p2}.',p2='away1')
        facts=sentence_facts(self.shot(text),self.players)
        self.assertEqual(facts['defenderId'],'away1')
        self.assertEqual(normalize('It’s… good!'),'It\'s... good!')


if __name__=='__main__':unittest.main()
