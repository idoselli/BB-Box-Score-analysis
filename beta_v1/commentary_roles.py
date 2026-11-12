"""Roles from the old sentence grammar and the new-site English catalog."""
from functools import lru_cache
from pathlib import Path
import re
import xml.etree.ElementTree as ET


@lru_cache(maxsize=1)
def _rules():
    try:
        nodes=ET.parse(Path(__file__).resolve().parents[1]/'commentary-en.xml').getroot().find('Events')
    except (OSError,ET.ParseError):
        return []
    wrappers=[];base=[]
    for node in nodes:
        text=' '.join((node.text or '').split())
        if node.tag.startswith(('e0001t','e0003t')):kind='defended'
        elif node.tag.startswith('e0002t') and '$player2$' in text:kind='pass'
        elif re.fullmatch(r'e[124]\d\dxt\d+',node.tag):kind='open'
        else:continue
        expression=re.escape(text)
        for token,name in [('$event1$','event'),('$player1$','player1'),('$player2$','player2')]:
            expression=expression.replace(re.escape(token),f'(?P<{name}>.+?)')
        if kind=='open':expression+=r'\.?'
        expression+=r'(?:\s*(?:Shot missed\.|Scored\.|Goaltending called\.|Shot blocked\.))?'
        rule=(kind,re.compile('^'+expression+'$',re.IGNORECASE),node.tag)
        (base if kind=='open' else wrappers).append(rule)
    return wrappers+base


def sentence_roles(event, players):
    if event.get('isCommentary'):
        return None
    from .pbp_catalog import sentence_facts
    facts = event.get('pbpFacts') or sentence_facts(event, players)
    if facts:
        defender = facts.get('defenderId') or facts.get('helpDefenderId')
        state = ('defended' if defender else 'unknown' if 'defender' in facts.get('unresolvedRoles', [])
                 else 'open' if facts.get('shotComplete') else None)
        if state:
            return {'state':state, 'source':'sentence:'+','.join(facts['templates']),
                    'defenderId':defender, 'passerId':facts.get('passerId')}
    text=next((event.get(key) for key in ('text','sentence','commentaryText','comment') if isinstance(event.get(key),str) and event[key].strip()),None)
    if text is None:return None
    text=' '.join(text.split())
    by_name={}
    for pid,(_,line) in players.items():
        p=line.get('player') or {};name=' '.join(filter(None,[p.get('firstName'),p.get('lastName')])).casefold()
        if name:by_name.setdefault(name,[]).append(pid)
    unresolved=False
    for kind,pattern,template in _rules():
        match=pattern.fullmatch(text)
        if not match:continue
        captures=match.groupdict();value=captures.get('player2')
        if kind=='open':
            actor=captures.get('player1','').strip()
            expected=event.get('player1Id')
            if actor!='$player1$' and expected not in by_name.get(actor.casefold(),[]):continue
            return {'state':'open','source':'sentence:'+template}
        if value=='$player2$':pid=event.get('player2Id')
        else:
            matches=by_name.get((value or '').strip().casefold(),[])
            pid=matches[0] if len(matches)==1 else None
        if not pid or pid==event.get('player1Id'):
            unresolved=True
            continue
        # Resolve the team relationship too: a passing wrapper cannot identify
        # an opponent as a teammate, or a defense wrapper a teammate as defender.
        shooter=event.get('player1Id')
        if shooter in players and pid in players and ((players[pid][0]==players[shooter][0]) != (kind=='pass')):
            unresolved=True
            continue
        return {'state':'defended' if kind=='defended' else 'open','source':'sentence:'+template,
                'defenderId':pid if kind=='defended' else None,'passerId':pid if kind=='pass' else None}
    return {'state':'unknown','source':'sentence-unresolved-actor'} if unresolved else None


def describe_shot(event):
    """Summarize known facts without inventing an original wording variation."""
    from .pbp_catalog import event_text
    text = event_text(event)
    if text:
        event['playDescription']=text
        event['descriptionSource']='recorded-play-by-play-text'
        return
    labels={'GenericThree':'three-pointer','StraightOnThree':'straight-on three-pointer','WingThree':'wing three-pointer',
            'CornerThree':'corner three-pointer','VeryLong':'long three-pointer','HalfCourtShot':'half-court shot',
            'GenericTwo':'two-point shot','Elbow':'elbow jumper','Wing':'wing jumper','BaselineJ':'baseline jumper',
            'TopKey':'top-of-key jumper','GenericInsideShot':'inside shot','Dunk':'dunk','Layup':'layup',
            'Strong':'inside shot','FallAway':'fade-away','Hook':'hook shot','Spinny':'off-dribble jumper',
            'TipbackDunk':'putback dunk','Tipback':'tip-in','Putback':'rebound shot','DrivingLayup':'driving layup'}
    shooter=event.get('player1Name') or 'Unknown player'
    phrase=shooter+' attempts a '+labels.get(event.get('shotType'),'shot')
    if event.get('passerId'):
        phrase+=' after a pass from '+(event.get('passerName') or event.get('player2Name') or 'Unknown player')
    if event.get('resolvedDefenderId'):
        phrase+=' with '+(event.get('defenderName') or 'Unknown player')+' defending'
    if event.get('helpDefenderId') or event.get('inferredHelpDefenderId'):
        phrase+=' and help from '+(event.get('helpDefenderName') or 'Unknown player')
    result=event.get('shotResult') or ''
    outcome='Outcome unavailable.' if not result or result=='None' else 'Goaltending called.' if result=='Goaltending' else 'Scored.' if event.get('made') else 'Shot blocked.' if 'Blocked' in result else 'Shot missed.'
    if 'Foul' in result:outcome+=' Shooting foul.'
    event['playDescription']=phrase+'. '+outcome
    event['descriptionSource']='normalized-play-by-play-facts'


def describe_event(event):
    """Show original text when supplied; otherwise label known structured facts."""
    from .pbp_catalog import event_text
    if event.get('eventType')=='Shot' and not event.get('isCommentary'):
        describe_shot(event)
        return
    text=event_text(event)
    if text:
        event['playDescription']=text;event['descriptionSource']='recorded-play-by-play-text'
        return
    p1=event.get('player1Name') or 'Unknown player';p2=event.get('player2Name') or 'Unknown player'
    kind=event.get('eventType')
    if event.get('isCommentary'):phrase='Commentary'
    elif kind in {'Steal','StealOnPass'}:phrase=f'{p1} steals the ball from {p2}.'
    elif kind=='Assist':phrase=f'{p1} assists {p2}.'
    elif kind=='Substitution':
        position={1:'PG',2:'SG',3:'SF',4:'PF',5:'C'}.get(event.get('detail'))
        phrase=f'{p1} replaces {p2}'+(f' at {position}.' if position else '.')
    elif kind=='SubstitutionSwap':phrase=f'{p1} and {p2} swap positions.'
    elif kind=='LoseControl':phrase=f'{p1} loses the handle.'
    elif kind=='TenSecViol':phrase=f'Backcourt time violation on {p1}.'
    elif kind=='Rebound':phrase=f'{p1}: '+((event.get('reboundType') or '')+' rebound.').strip()
    elif kind=='FreeThrow':phrase=f'{p1}: '+{'FreeThrowMade':'free throw made.','FreeThrowMissed':'free throw missed.'}.get(event.get('shotResult'),'free throw; outcome unavailable.')
    else:phrase=re.sub(r'(?<=[a-z])(?=[A-Z])',' ',kind or 'Event')
    event['playDescription']=phrase
    event['descriptionSource']='normalized-play-by-play-facts'
