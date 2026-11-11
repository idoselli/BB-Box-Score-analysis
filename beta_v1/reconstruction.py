"""Reconstruct public event roles and lineups, with box-score reconciliation."""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import permutations

ZERO = '00000000-0000-0000-0000-000000000000'
POSITIONS = ('pointGuard','shootingGuard','smallForward','powerForward','center')
ACTIVE_EVENTS = {'Shot','FreeThrow','ShootingFoul','NoShootFoul','Assist','Steal','StealOnPass',
                 'BadPass','OffFoul','Travel','ThreeSecond','ShotClockZero','BackCourtViol',
                 'TenSecViol','Rebound','ReboundOut','ReboundFoul','JumpBall','Injury','SubstitutionSwap'}
TURNOVERS = {'ThreeSecond','BadPass','OffFoul','ShotClockZero','BackCourtViol','TenSecViol','Travel','LoseControl'}


def identities(box):
    return {str(line['player']['id']):(str(side.get('teamId')),line)
            for side in box.get('teams',[]) for line in side.get('players',[]) if (line.get('player') or {}).get('id')}


def infer_roles(events, box):
    """The legacy shot grammar distinguishes an opposing defender from a teammate passer."""
    players=identities(box)
    for e in events:
        kind=e.get('eventType');p1=str(e.get('player1Id') or '');p2=str(e.get('player2Id') or '')
        if kind=='Assist':
            e['assisterId']=p1 if p1 in players else None
        if kind in TURNOVERS or kind in {'Steal','StealOnPass'} or (kind=='ReboundOut' and e.get('reboundType')=='Offensive'):
            pid=p2 if kind in {'Steal','StealOnPass'} else p1
            e['turnoverPlayerId']=pid if pid in players else None
        if kind!='Shot' or e.get('isCommentary'):
            continue
        for key in ('inferredDefenderId','resolvedDefenderId','passerId','defenseState','defenderSource'):
            e.pop(key,None)
        from .commentary_roles import sentence_roles
        sentence=sentence_roles(e,players)
        primary=e.get('primaryDefenderId')
        e['defenderSource']='api' if primary and primary!=ZERO else None
        e['passerId']=None
        if primary and primary!=ZERO:
            e['defenseState']='defended'
        elif e.get('contestLevel')=='Open':
            e['defenseState']='open';e['defenderSource']='api-contest'
        elif sentence is not None:
            e['defenseState']=sentence['state'];e['defenderSource']=sentence['source']
            if sentence.get('defenderId'):e['inferredDefenderId']=sentence['defenderId']
            if sentence.get('passerId'):e['passerId']=sentence['passerId']
        elif p1 in players and p2 in players and players[p1][0]!=players[p2][0]:
            # player2 is an opposing participant in the shot grammar. This also
            # covers ShotBlockedAssist; the enum suffix alone does not identify a passer.
            e['inferredDefenderId']=p2
            e['defenseState']='defended';e['defenderSource']='play-by-play-opponent'
        elif p1 in players and p2 in players and p1!=p2 and players[p1][0]==players[p2][0]:
            e['passerId']=p2
            e['defenseState']='defended' if e.get('contestLevel') in {'Light','Contested','Smothered'} else 'open'
            e['defenderSource']='play-by-play-passer'
        elif e.get('contestLevel') in {'Light','Contested','Smothered'}:
            e['defenseState']='defended';e['defenderSource']='api-contest'
        else:
            # The current API does not export rendered sentences. A genuinely
            # missing/unknown actor remains distinct from a known passer-only play.
            e['defenseState']='unknown'
    # Assist events follow their scoring shot: use that shot's PRE-play clutch state.
    last_shot=None
    for e in events:
        if e.get('eventType')=='Shot' and not e.get('isCommentary'):
            last_shot=e
        elif e.get('eventType')=='Assist' and last_shot:
            if (e.get('period'),e.get('clock'),e.get('player2Id')) == (last_shot.get('period'),last_shot.get('clock'),last_shot.get('player1Id')):
                e['clutch']=last_shot.get('clutch',False)
                e['linkedShotSequence']=last_shot.get('sequenceIndex')


def _split():
    return {'m':0,'a':0}


def _player():
    return {'seconds':0,'plusMinus':0,'clutchPlusMinus':0,'clutchAssists':0,'clutchTurnovers':0,
            'teamOn':_split(),'teamOff':_split(),'teamDefOn':_split(),'teamDefOff':_split()}


def reconstruct(events, match, box):
    players=identities(box)
    team_ids={team for team,_ in players.values()}
    rosters={team:{pid for pid,(tid,line) in players.items() if tid==team and (line.get('minutes') or line.get('fieldGoalsAttempts') or line.get('position'))} for team in team_ids}
    result={'status':'unavailable','reasons':[],'players':{pid:_player() for pid in players},
            'assistsValidated':False,'turnoversValidated':False,'defenderBlocksValidated':False,'positionsValidated':False,'starters':{},'stints':[]}
    stats=result['players']
    blocks=Counter((e.get('resolvedDefenderId') or e.get('primaryDefenderId') or e.get('inferredDefenderId'))
                   for e in events if e.get('eventType')=='Shot' and 'Blocked' in (e.get('shotResult') or '') and not e.get('isCommentary'))
    result['defenderBlocksValidated']=bool(events) and all(isinstance(line.get('blocks'),int) and blocks[pid]==line['blocks'] for pid,(_,line) in players.items())
    # Validate actor rules separately: these do not require reconstructed lineups.
    for field,actor,flag,target in [('assists','assisterId','assistsValidated','clutchAssists'),('turnovers','turnoverPlayerId','turnoversValidated','clutchTurnovers')]:
        counts=Counter(e.get(actor) for e in events if not e.get('isCommentary') and e.get(actor))
        eligible=[(pid,line) for pid,(_,line) in players.items() if line.get('minutes') or line.get(field)]
        valid=bool(events and eligible) and all(isinstance(line.get(field),int) and counts[pid]==line[field] for pid,line in eligible)
        result[flag]=valid
        result.setdefault('actorMismatches',{})[field]=[{'playerId':pid,'official':line.get(field),'events':counts[pid]}
                                                       for pid,line in eligible if not isinstance(line.get(field),int) or counts[pid]!=line[field]]
        if valid:
            for e in events:
                if e.get('clutch') and e.get(actor) in stats and not e.get('isCommentary'):
                    stats[e[actor]][target]+=1
    if not events or len(team_ids)!=2 or not any(e.get('eventType')=='GameOver' for e in events):
        result['reasons'].append('Complete finished-game events are required for lineup reconstruction.')
        return result
    starts={team:set() for team in team_ids};ever_in=set()
    for e in events:
        if e.get('isCommentary'):
            continue
        if e.get('eventType')=='Substitution':
            pid=e.get('player2Id')
            if pid in players and pid not in ever_in:starts[players[pid][0]].add(pid)
            ever_in.add(e.get('player1Id'))
        elif e.get('eventType') in ACTIVE_EVENTS:
            for key in (('player1Id',) if e.get('eventType')=='FreeThrow' else ('player1Id','player2Id')):
                pid=e.get(key)
                if pid in players and pid not in ever_in and pid in rosters[players[pid][0]]:
                    starts[players[pid][0]].add(pid)
    for team in team_ids:
        starts[team] |= rosters[team]-ever_in
    if any(len(ids)!=5 for ids in starts.values()):
        result['reasons'].append('The play-by-play does not uniquely identify five starters per side.')
        return result
    result['starters']={team:sorted(ids) for team,ids in starts.items()}
    active={team:set(ids) for team,ids in starts.items()}
    # Track symbolic starting-role identities through substitutions and swaps.
    symbols={pid:pid for ids in starts.values() for pid in ids}
    constraints={};role_seconds=defaultdict(Counter)
    home=next((str(side.get('teamId')) for side in match.get('teams',[]) if side.get('isHome')),None)
    away=next((str(side.get('teamId')) for side in match.get('teams',[]) if not side.get('isHome')),None)
    if {home,away}!=team_ids:
        result['reasons'].append('Home and away identities could not be reconciled.')
        return result
    elapsed=0;home_score=away_score=0;position_conflict=False
    def fail(reason):
        result['reasons'].append(reason)
        return result
    for e in events:
        period=e.get('period');clock=e.get('clock')
        if not isinstance(period,int) or period<1 or not isinstance(clock,int):
            return fail('An event has an invalid period or clock.')
        length=720 if period<=4 else 300
        current=(period-1)*720 if period<=4 else 2880+(period-5)*300
        current+=length-clock
        if clock<0 or clock>length or current<elapsed:
            return fail('Event clocks do not form a consistent game timeline.')
        delta=current-elapsed
        if delta:
            result['stints'].append({'from':elapsed,'to':current,'lineups':{team:sorted(ids) for team,ids in active.items()}})
        for ids in active.values():
            for pid in ids:
                stats[pid]['seconds']+=delta
                role_seconds[pid][symbols[pid]]+=delta
        elapsed=current
        h=e.get('homePoints');a=e.get('awayPoints')
        if not isinstance(h,int) or not isinstance(a,int) or h<home_score or a<away_score:
            return fail('Event scores do not form a consistent scoring timeline.')
        dh=h-home_score;da=a-away_score
        clutch=period>=4 and clock<=300 and abs(home_score-away_score)<=5
        for team,ids in active.items():
            diff=dh-da if team==home else da-dh
            for pid in ids:
                stats[pid]['plusMinus']+=diff
                if clutch:stats[pid]['clutchPlusMinus']+=diff
        home_score=h;away_score=a
        if e.get('isCommentary'):
            continue
        kind=e.get('eventType');p1=e.get('player1Id');p2=e.get('player2Id')
        if kind=='Substitution':
            if p1 not in players or p2 not in players or players[p1][0]!=players[p2][0]:
                return fail('A substitution has unresolved or inconsistent player identities.')
            team=players[p1][0]
            if p2 not in active[team] or (p1!=p2 and p1 in active[team]):
                return fail('A substitution contradicts the reconstructed active five.')
            symbol=symbols[p2];role=e.get('detail')
            if role in range(1,6):
                if symbol in constraints and constraints[symbol]!=role-1:position_conflict=True
                constraints[symbol]=role-1
            if p1!=p2:
                active[team].remove(p2);active[team].add(p1)
                symbols[p1]=symbols.pop(p2)
        elif kind=='SubstitutionSwap':
            if p1 not in symbols or p2 not in symbols or players[p1][0]!=players[p2][0]:
                return fail('A position swap has unresolved active players.')
            symbols[p1],symbols[p2]=symbols[p2],symbols[p1]
        elif kind in ACTIVE_EVENTS:
            for pid in ({p1} if kind=='FreeThrow' else {p1,p2}):
                if pid in players and pid not in active[players[pid][0]]:
                    return fail('An on-court play references a player outside the reconstructed lineup.')
        if kind=='Shot' and e.get('countsAsAttempt'):
            shooter_team=players.get(p1,(None,None))[0]
            if shooter_team not in active:
                return fail('A shot has no resolvable shooting team.')
            for team,ids in rosters.items():
                for pid in ids:
                    key=('teamOn' if pid in active[team] else 'teamOff') if team==shooter_team else ('teamDefOn' if pid in active[team] else 'teamDefOff')
                    stats[pid][key]['a']+=1;stats[pid][key]['m']+=int(bool(e.get('made')))
    attempts=Counter(e.get('player1Id') for e in events if e.get('eventType')=='Shot' and e.get('countsAsAttempt') and not e.get('isCommentary'))
    makes=Counter(e.get('player1Id') for e in events if e.get('eventType')=='Shot' and e.get('countsAsAttempt') and e.get('made') and not e.get('isCommentary'))
    if any((line.get('fieldGoalsAttempts') is not None and attempts[pid]!=line['fieldGoalsAttempts']) or
           (line.get('fieldGoals') is not None and makes[pid]!=line['fieldGoals']) for pid,(_,line) in players.items()):
        return fail('Event field-goal totals do not reconcile with the official player lines.')
    expected={str(side.get('teamId')):side.get('score') for side in match.get('teams',[])}
    if home_score!=expected.get(home) or away_score!=expected.get(away):
        return fail('The final event score differs from the official match score.')
    mismatches=[]
    for pid,(_,line) in players.items():
        if abs(stats[pid]['seconds']/60-(line.get('minutes') or 0))>.51:
            mismatches.append('minutes')
        if line.get('plusMinus') is not None and stats[pid]['plusMinus']!=line['plusMinus']:
            mismatches.append('plus/minus')
    if mismatches:
        return fail('Reconstructed '+', '.join(sorted(set(mismatches)))+' do not reconcile with the official player lines.')
    result['status']='validated'
    # At most 5! assignments per side; accept exact roles only when unique.
    resolved_roles={}
    if not position_conflict:
        for team in team_ids:
            starters=sorted(starts[team]);solutions=[]
            for roles in permutations(range(5)):
                assignment=dict(zip(starters,roles))
                if any(assignment[symbol]!=role for symbol,role in constraints.items() if symbol in assignment):continue
                valid=True
                for pid in rosters[team]:
                    split=players[pid][1].get('minutesByPosition')
                    if split is None:continue
                    seconds=[0]*5
                    for symbol,value in role_seconds[pid].items():seconds[assignment[symbol]]+=value
                    if any(not isinstance(split.get(pos),int) or abs(seconds[i]/60-split[pos])>.51 for i,pos in enumerate(POSITIONS)):
                        valid=False;break
                if valid:solutions.append(assignment)
            if len(solutions)==1:resolved_roles.update(solutions[0])
    if len(resolved_roles)==10:
        result['positionsValidated']=True
        for pid in stats:
            seconds=dict.fromkeys(POSITIONS,0)
            for symbol,value in role_seconds[pid].items():seconds[POSITIONS[resolved_roles[symbol]]]+=value
            stats[pid]['secondsByPosition']=seconds
    return result
