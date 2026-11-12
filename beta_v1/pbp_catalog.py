"""New-site English templates: recover recorded roles, never manufacture events.

Only physical play templates and explicit actor tags carry statistical roles.
Buzz, color, stakes, trash talk, replays and spoken recaps remain presentation.
"""
from __future__ import annotations

from functools import lru_cache
import html
import json
from pathlib import Path
import re

ZERO = '00000000-0000-0000-0000-000000000000'
POSITIONS = {'pg': 1, 'sg': 2, 'sf': 3, 'pf': 4, 'c': 5}
TEXT_FIELDS = ('text', 'sentence', 'commentaryText', 'comment')
SHOT_TYPES = {'three': 'GenericThree', 'deep': 'VeryLong', 'dunk': 'Dunk',
              'jumper': 'GenericTwo', 'layup': 'Layup', 'post': 'GenericInsideShot',
              'putback': 'Putback', 'inside': 'GenericInsideShot'}


def normalize(text):
    return ' '.join(html.unescape(text).translate(str.maketrans({'’': "'", '‘': "'", '…': '...', '–': '-', '—': '-'})).split())


def event_text(event):
    return next((event[key] for key in TEXT_FIELDS if isinstance(event.get(key), str) and event[key].strip()), None)


@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent / 'data' / 'pbp-en.json').read_text())['catalog']


def category(key):
    """Explicitly classify every catalog entry; unknown categories add no facts."""
    if key.startswith(('playByPlay.buzz.', 'playByPlay.color.', 'playByPlay.stakes.', 'playByPlay.talk.')):
        return 'flavor'
    if key.startswith(('playByPlay.made.', 'playByPlay.missed.')):
        return 'shot'
    if key in {'playByPlay.guarded', 'playByPlay.helped'}:
        return 'defender'
    if key.startswith('playByPlay.lineup.'):
        return 'lineup'
    if key.startswith('playByPlay.turnover.') or key == 'playByPlay.steal':
        return 'turnover'
    if key.startswith('playByPlay.rebound.'):
        return 'rebound'
    if key.startswith('playByPlay.freeThrows.'):
        return 'free-throw-summary'
    if key in {'playByPlay.andOne', 'playByPlay.foul', 'playByPlay.fouledOnMiss', 'playByPlay.intentionalFoul'}:
        return 'foul'
    if key.startswith('other.'):
        return 'simple-event'
    if key.startswith('commentary.'):
        # Spoken variants change delivery, not actor semantics. These short tags
        # may enrich a physical Shot row but cannot create a new statistical row.
        if key.startswith('commentary.spoken.'):
            return 'broadcast'
        if key.startswith(('commentary.freeThrow.made.', 'commentary.freeThrow.miss.')):
            return 'free-throw-result'
        if key.startswith(('commentary.call.block.', 'commentary.tag.assist.')) or key == 'commentary.tag.assists.calm':
            return 'shot-tag'
        return 'broadcast'
    return 'display'


@lru_cache(maxsize=32)
def _rules(names):
    # Known names first handles initials, apostrophes and names that prefix other
    # names. The bounded fallback detects explicitly named but unresolved actors.
    actors = '|'.join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    placeholders = r'\$player[12]\$|%?\{p[12]\}'
    actor_pattern = '(?:' + (actors + '|' if actors else '') + placeholders + r'|[^.!?]{1,120}?)'
    rules = []
    for key, value in catalog().items():
        kind = category(key)
        if kind not in {'shot', 'defender', 'lineup', 'turnover', 'rebound', 'foul', 'shot-tag', 'simple-event', 'free-throw-result'}:
            continue
        for variant, text in enumerate(value.split(' | ')):
            text = normalize(text)
            # The fallback UI labels use %{p1}, while main templates use {p1}.
            parts = re.split(r'(%?\{(?:p1|p2|team|n|m)\})', text)
            seen = set(); expression = ''
            for part in parts:
                if re.fullmatch(r'%?\{\w+\}', part):
                    token = part.lstrip('%')[1:-1]
                    if token in seen:
                        expression += f'(?P={token})'
                    else:
                        capture = actor_pattern if token in {'p1', 'p2'} else r'\d+' if token in {'n', 'm'} else r'[^.!?]{1,120}?'
                        expression += f'(?P<{token}>{capture})'; seen.add(token)
                else:
                    expression += re.escape(part)
            # Whole tokens only. A final actor must end at a clause boundary.
            end = r'(?=$|\s*[.!?,;])' if re.search(r'%?\{p[12]\}$', text) else r'(?!\w)'
            rules.append((key, variant, kind, re.compile(r'(?<!\w)' + expression + end, re.I)))
    return rules


def sentence_facts(event, players):
    """Read literal sentences only; structured facts remain authoritative."""
    original = event_text(event)
    if not original or event.get('isCommentary'):
        return {}
    text = normalize(original)
    by_name = {}
    for pid, (_, line) in players.items():
        player = line.get('player') or {}
        name = normalize(' '.join(filter(None, [player.get('firstName'), player.get('lastName')]))).casefold()
        if name:
            by_name.setdefault(name, []).append(pid)
    kind = event.get('eventType')
    facts = {'templates': [], 'unresolvedRoles': []}
    expected_shooter = event.get('player1Id')

    def actor(value, slot, relation=None):
        if not value:
            return None
        if re.fullmatch(r'\$player[12]\$|%?\{p[12]\}', value):
            number = '1' if '1' in value else '2'
            candidates = [event.get('player' + number + 'Id')]
        else:
            candidates = by_name.get(normalize(value).casefold(), [])
        candidates = [pid for pid in candidates if pid in players]
        shooter = facts.get('shooterId') or expected_shooter
        if slot == 'p1' and expected_shooter in players:
            return expected_shooter if expected_shooter in candidates else None
        if relation and shooter in players:
            candidates = [pid for pid in candidates if pid != shooter and
                          ((players[pid][0] == players[shooter][0]) == (relation == 'teammate'))]
        hint = event.get('player' + ('1' if slot == 'p1' else '2') + 'Id')
        return hint if hint in candidates else candidates[0] if len(candidates) == 1 else None

    for key, variant, rule_kind, pattern in _rules(tuple(by_name)):
        # Do not reinterpret a free throw, substitution or recap as a field goal.
        if rule_kind in {'shot', 'defender', 'shot-tag'} and kind != 'Shot':
            continue
        if rule_kind == 'lineup' and kind not in {'Substitution', 'SubstitutionSwap'}:
            continue
        if rule_kind == 'turnover' and kind not in {'Steal', 'StealOnPass', 'ThreeSecond', 'BadPass', 'OffFoul', 'ShotClockZero', 'BackCourtViol', 'TenSecViol', 'Travel', 'LoseControl'}:
            continue
        if rule_kind == 'rebound' and kind != 'Rebound':
            continue
        if rule_kind == 'simple-event' and kind not in {'Shot', 'FreeThrow', 'Steal', 'StealOnPass'}:
            continue
        if rule_kind == 'free-throw-result' and kind != 'FreeThrow':
            continue
        if rule_kind == 'foul' and kind not in {'Shot', 'ShootingFoul', 'NoShootFoul', 'DFoulNoShoot', 'DFoulNoShootEog'}:
            continue
        for match in pattern.finditer(text):
            # Short defender tags start a clause, not a generic phrase such as
            # "skies over the defender" inside a dunk description.
            if rule_kind in {'defender', 'free-throw-result'} and match.start() and text[:match.start()].rstrip()[-1:] not in '.!?,;':
                continue
            captures = match.groupdict()
            p1 = actor(captures.get('p1'), 'p1')
            if captures.get('p1') and not p1:
                continue
            if rule_kind in {'shot', 'simple-event'} and p1:
                facts['shooterId'] = p1
            facts['templates'].append(f'{key}:{variant}')
            if rule_kind == 'shot':
                facts['shotComplete'] = True
                facts['made'] = key.startswith('playByPlay.made.')
                category_name = key.rsplit('.', 1)[1].removesuffix('Assist')
                if category_name in SHOT_TYPES:
                    facts['shotType'] = SHOT_TYPES[category_name]
                if key.endswith('Assist'):
                    facts['receivedPass'] = True
                    pid = actor(captures.get('p2'), 'p2', 'teammate')
                    if pid: facts['passerId'] = pid
                    else: facts['unresolvedRoles'].append('passer')
                if key == 'playByPlay.missed.blocked':
                    facts['blocked'] = True
                    pid = actor(captures.get('p2'), 'p2', 'opponent')
                    if pid: facts['defenderId'] = pid
                    else: facts['unresolvedRoles'].append('defender')
            elif rule_kind == 'defender' or (rule_kind == 'shot-tag' and '.call.block.' in key):
                pid = actor(captures.get('p2'), 'p2', 'opponent')
                target = 'helpDefenderId' if key == 'playByPlay.helped' else 'defenderId'
                if pid: facts[target] = pid
                else: facts['unresolvedRoles'].append('defender')
                if '.call.block.' in key: facts['blocked'] = True
            elif rule_kind == 'shot-tag':
                facts['receivedPass'] = True
                pid = actor(captures.get('p2'), 'p2', 'teammate')
                if pid: facts['passerId'] = pid
                else: facts['unresolvedRoles'].append('passer')
            elif rule_kind == 'lineup':
                p2 = actor(captures.get('p2'), 'p2')
                if p1 and p2 and players[p1][0] == players[p2][0]:
                    facts.update(player1Id=p1, player2Id=p2)
                    if key.rsplit('.', 1)[1] in POSITIONS: facts['position'] = POSITIONS[key.rsplit('.', 1)[1]]
            elif rule_kind == 'turnover':
                if key == 'playByPlay.steal' and kind in {'Steal', 'StealOnPass'}:
                    p2 = actor(captures.get('p2'), 'p2', 'opponent')
                    if p1: facts['stealerId'] = p1
                    if p2: facts['turnoverPlayerId'] = p2
                elif key.startswith('playByPlay.turnover.') and kind not in {'Steal', 'StealOnPass'} and p1:
                    facts['turnoverPlayerId'] = p1
            elif rule_kind == 'rebound' and p1:
                facts.update(rebounderId=p1, reboundType='Offensive' if key.endswith('offensive') else 'Defensive')
            elif rule_kind == 'foul':
                # A named fouler is not automatically the primary shot defender.
                p2 = actor(captures.get('p2'), 'p2', 'opponent')
                if p2: facts['foulerId'] = p2
                if key == 'playByPlay.andOne': facts['andOne'] = True
                if key == 'playByPlay.fouledOnMiss': facts['shootingFoul'] = True
            elif rule_kind == 'free-throw-result':
                facts['freeThrowMade'] = key.startswith('commentary.freeThrow.made.')
            elif rule_kind == 'simple-event':
                if key == 'other.p1IsBlockedByP2' and kind == 'Shot':
                    facts.update(shotComplete=True, made=False, blocked=True)
                    pid = actor(captures.get('p2'), 'p2', 'opponent')
                    if pid: facts['defenderId'] = pid
                    else: facts['unresolvedRoles'].append('defender')
                elif key in {'other.p1Scores', 'other.p1ScoresFromThree', 'other.p1Misses'} and kind == 'Shot':
                    facts.update(shotComplete=True, made=key != 'other.p1Misses')
                    if key == 'other.p1ScoresFromThree': facts['shotType'] = 'GenericThree'
                elif key in {'other.p1MakesTheFreeThrow', 'other.p1MissesTheFreeThrow'} and kind == 'FreeThrow':
                    facts['freeThrowMade'] = key == 'other.p1MakesTheFreeThrow'
                elif key == 'other.stealsTheBallFromP2' and kind in {'Steal', 'StealOnPass'}:
                    pid = actor(captures.get('p2'), 'p2', 'opponent')
                    if pid: facts['turnoverPlayerId'] = pid
                    if expected_shooter in players: facts['stealerId'] = expected_shooter
    facts['templates'] = list(dict.fromkeys(facts['templates']))
    facts['unresolvedRoles'] = sorted(set(facts['unresolvedRoles']))
    shooter = facts.get('shooterId') or expected_shooter
    if kind == 'Shot' and shooter in players:
        for role, relation in [('defenderId', False), ('helpDefenderId', False), ('foulerId', False), ('passerId', True)]:
            pid = facts.get(role)
            if pid and (pid == shooter or (players[pid][0] == players[shooter][0]) != relation):
                facts.pop(role)
                facts['unresolvedRoles'].append('passer' if relation else 'defender')
    return facts if facts['templates'] else {}


def apply_sentence_facts(event, players):
    facts = sentence_facts(event, players)
    event['pbpFacts'] = facts
    if not facts:
        return
    event['pbpTemplates'] = facts['templates']
    inferred = []
    for key in ('player1Id', 'player2Id'):
        value = facts.get(key)
        if key == 'player1Id' and not value: value = facts.get('shooterId') or facts.get('rebounderId') or facts.get('stealerId') or facts.get('turnoverPlayerId')
        if key == 'player2Id' and not value and event.get('eventType') in {'Steal', 'StealOnPass'}: value = facts.get('turnoverPlayerId')
        if value and event.get(key) in {None, '', ZERO}:
            event[key] = value; inferred.append(key)
    if event.get('eventType') == 'Shot' and facts.get('shotComplete'):
        if event.get('shotResult') in {None, 'None'}:
            event['shotResult'] = ('ShotMade' if facts.get('made') else 'ShotMissedFoul' if facts.get('shootingFoul')
                                   else 'ShotBlocked' if facts.get('blocked') else 'ShotMissed')
            inferred.append('shotResult')
        if event.get('shotType') in {None, 'None'} and facts.get('shotType'):
            event['shotType'] = facts['shotType']; inferred.append('shotType')
    if event.get('eventType') == 'Substitution' and event.get('detail') is None and facts.get('position'):
        event['detail'] = facts['position']; inferred.append('detail')
    if event.get('eventType') == 'Rebound' and not event.get('reboundType') and facts.get('reboundType'):
        event['reboundType'] = facts['reboundType']; inferred.append('reboundType')
    if event.get('eventType') == 'FreeThrow' and event.get('shotResult') in {None, 'None'} and 'freeThrowMade' in facts:
        event['shotResult'] = 'FreeThrowMade' if facts['freeThrowMade'] else 'FreeThrowMissed'
        inferred.append('shotResult')
    if inferred: event['pbpInferredFields'] = inferred
