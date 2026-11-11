"""Adapt production facts to the existing multi-match renderer and its visual system."""
from __future__ import annotations

import re
from collections import defaultdict, Counter

from flask import render_template_string

from .events import ZERO_UUID
from .reports import POSITIONS

SHOT_CODES = dict(zip(
    ('GenericThree','StraightOnThree','WingThree','CornerThree','VeryLong','HalfCourtShot',
     'GenericTwo','Elbow','Wing','BaselineJ','TopKey','GenericInsideShot','Dunk','Layup',
     'Strong','FallAway','Hook','Spinny','TipbackDunk','Tipback','Putback','DrivingLayup'),
    ('100','101','102','103','104','105','200','201','202','203','204','400','401','402',
     '403','404','405','406','407','408','409','411')))
FIELDS = {'mins':'minutes','pts':'points','fgm':'fieldGoals','fga':'fieldGoalsAttempts',
          'tpm':'threePointFieldGoals','tpa':'threePointFieldGoalsAttempts','ftm':'freeThrows',
          'fta':'freeThrowsAttempts','tr':'rebounds','or':'offensiveRebounds','ast':'assists',
          'to':'turnovers','stl':'steals','blk':'blocks','pf':'fouls','pm':'plusMinus'}


def stats(line):
    out = {short: line.get(long) or 0 for short, long in FIELDS.items()}
    out['dr'] = out['tr'] - out['or']
    return out


def group(offense):
    if offense in {'LookInside','LowPost'}:
        return 'inside'
    if offense in {'Motion','RunAndGun','Princeton'}:
        return 'outside'
    return 'balanced'


def split():
    return {'m': 0, 'a': 0}


def add(target, made, attempts=1):
    target['a'] += attempts
    target['m'] += int(made)


def tactics(ratings):
    def prediction(key):
        value = ratings.get('prediction' + key)
        correct = ratings.get('prediction' + key + 'Correct')
        return {'value': value or 'N/A', 'result': 'Correct' if correct is True else 'Incorrect' if correct is False else 'N/A'}
    from web_tool import tactic_label
    offense = {'BaseOffense':'Base','PushTheBall':'Push'}.get(ratings.get('offenseStrategy'),ratings.get('offenseStrategy'))
    return {'offense': {'BaseOffense':'Base','PushTheBall':'Push'}.get(ratings.get('offenseStrategy'), ratings.get('offenseStrategy')),
            'offense_label': tactic_label(offense) if offense else 'Unavailable',
            'defense': re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', ratings.get('defensiveStrategy') or 'Unavailable'),
            'gdp': {'focus': prediction('Focus'), 'pace': prediction('Pace')}}


def presentation(report):
    from web_tool import empty_nba_player_row
    names = dict(report.get('playerNames') or {})
    # Captured reports from before the directory fix also render correctly.
    for match in report.get('matches', []):
        for line in match.get('playerLines', []) + match.get('opponentPlayerLines', []):
            p = line.get('player') or {}
            name = ' '.join(filter(None, [p.get('firstName'), p.get('lastName')])).strip()
            if name and name.lower() != 'unknown player':
                names[str(p.get('id'))] = name
    ids = {str((line.get('player') or {}).get('id')) for match in report.get('matches', [])
           for line in match.get('playerLines', []) + match.get('opponentPlayerLines', [])}
    ids |= {str(e.get(field)) for e in report.get('events', [])
            for field in ('player1Id','player2Id','primaryDefenderId','helpDefenderId') if e.get(field)}
    for index,pid in enumerate(sorted(pid for pid in ids if pid not in names and pid not in {'None',ZERO_UUID}),1):
        names[pid] = f'Unknown player {index}'
    duplicates = Counter(names.values())
    seen = Counter()
    for pid in sorted(names):
        original = names[pid]
        if duplicates[original] > 1:
            seen[original] += 1
            names[pid] = f'{original} · {seen[original]}'
    def name(pid):
        return names.get(str(pid)) or 'Unknown player'
    summary = [dict(stats(p), name=name(p['playerId']), gp=p['games'], playerId=p['playerId']) for p in report.get('players', [])]
    matchups = {}
    defenses = {}
    offense = {}
    nba = []
    team_rows = []
    matches = []
    defended_events = []
    minutes = {g: {pos: defaultdict(int) for pos in POSITIONS} for g in ('inside','outside','balanced')}
    shot_codes = set()
    results = set()
    derived_seconds=Counter();invalid_minutes=set()
    event_by_match = {r['matchId']: r for r in report.get('eventReports', [])}
    for match in report.get('matches', []):
        mid = match['matchId']
        offense_type = (match.get('ratings') or {}).get('offenseStrategy')
        tactic_group = group(offense_type)
        own_ids = {str((line.get('player') or {}).get('id')) for line in match.get('playerLines', [])}
        opponent_ids = {str((line.get('player') or {}).get('id')) for line in match.get('opponentPlayerLines', [])}
        event_report = event_by_match.get(mid, {})
        reconstructed=event_report.get('reconstruction') or match.get('reconstruction') or {}
        lineup_valid=reconstructed.get('status')=='validated'
        role_valid=lineup_valid and reconstructed.get('positionsValidated',False)
        nba_players = {}
        for line in match.get('playerLines', []):
            pid = str((line.get('player') or {}).get('id'))
            if not line.get('minutes') and not line.get('fieldGoalsAttempts'):
                continue
            row = empty_nba_player_row(mid, match['result'], tactic_group, name(pid))
            row.update(stats(line), playerId=pid, lineup_valid=lineup_valid,
                       assists_valid=reconstructed.get('assistsValidated',False),turnovers_valid=reconstructed.get('turnoversValidated',False))
            derived=(reconstructed.get('players') or {}).get(pid,{})
            if lineup_valid:
                row['mins']=round(derived.get('seconds',0)/60,1)
                derived_seconds[pid]+=derived.get('seconds',0)
                for source,target in [('teamDefOn','team_def_on'),('teamDefOff','team_def_off')]:
                    row[target]=dict(derived.get(source) or split())
                row['clutch']['pm']=derived.get('clutchPlusMinus',0)
            else:
                invalid_minutes.add(pid)
            row['clutch']['ast']=derived.get('clutchAssists',0)
            row['clutch']['to']=derived.get('clutchTurnovers',0)
            nba_players[pid] = row
            matchups.setdefault(pid, dict(name=name(pid), playerId=pid, **{key: split() for key in ('defended','openClose','openMid','openThree','openTotal','withPass','withoutPass')}, teamOn=split(), teamOff=split(), lineup_valid=True))
            defenses.setdefault(pid, dict(name=name(pid), playerId=pid, **{key: split() for key in ('defendedTotal','defendedClose','defendedMid','defendedThree')}, teamDefOn=split(), teamDefOff=split(), lineup_valid=True))
            for store,keys in [(matchups[pid],('teamOn','teamOff')),(defenses[pid],('teamDefOn','teamDefOff'))]:
                store['lineup_valid'] = store['lineup_valid'] and lineup_valid
                if lineup_valid:
                    for key in keys:
                        value=derived.get(key) or split()
                        store[key]['a']+=value['a'];store[key]['m']+=value['m']
            role_minutes = ({pos:value/60 for pos,value in derived.get('secondsByPosition',{}).items()} if role_valid else line.get('minutesByPosition'))
            if isinstance(role_minutes, dict) and (role_valid or (all(isinstance(role_minutes.get(pos), int) and role_minutes[pos] >= 0 for pos in POSITIONS) and sum(role_minutes[pos] for pos in POSITIONS) == line.get('minutes'))):
                for pos in POSITIONS:
                    if role_minutes[pos] > 0:
                        minutes[tactic_group][pos][pid] += role_minutes[pos]
        # Shooting fallback is useful even when public event reads are unavailable.
        for shot in (match.get('shooting') or {}).get('players', []):
            pid = str(shot.get('playerId'))
            if pid not in nba_players:
                continue
            for api_key, key in [('inside','shots_close'),('midRange','shots_mid'),('three','shots_three')]:
                value = shot.get(api_key) or {}
                nba_players[pid][key] = {'m': value.get('made') or 0, 'a': value.get('attempts') or 0}
        for e in event_report.get('events', []):
            pid = str(e.get('player1Id'))
            row = nba_players.get(pid)
            if row and e.get('clutch') and e.get('eventType') == 'FreeThrow' and e.get('shotResult') == 'FreeThrowMade':
                row['clutch']['pts'] += 1
        if event_report:
            for row in nba_players.values():
                for key in ('shots_close','shots_mid','shots_three'):
                    row[key] = split()
        for e in event_report.get('shots', []):
            pid = str(e.get('player1Id'))
            code = SHOT_CODES.get(e.get('shotType'), e.get('shotType') or 'Unknown')
            range_key = ('Three' if code.startswith('10') else 'Mid' if code.startswith('20') else 'Close') if e.get('shotType') in SHOT_CODES else None
            made = bool(e.get('made'))
            attempt = bool(e.get('countsAsAttempt'))
            defender = str(e.get('resolvedDefenderId') or e.get('primaryDefenderId') or e.get('inferredDefenderId') or '')
            explicit_defender = defender and defender != ZERO_UUID
            is_open = e.get('defenseState') == 'open' or e.get('contestLevel') == 'Open'
            is_defended = bool(explicit_defender) or e.get('contestLevel') in {'Light','Contested','Smothered'}
            assisted = bool(e.get('passerId')) if 'defenseState' in e else 'Assist' in (e.get('shotResult') or '')
            result = '1' if made else '3' if 'Blocked' in (e.get('shotResult') or '') else '4' if 'Foul' in (e.get('shotResult') or '') else '0'
            if e.get('shotResult') == 'Goaltending':
                result = '2'
            if pid in own_ids and attempt:
                shot_codes.add(code)
                item = offense.setdefault(pid, {'name': name(pid), 'playerId': pid, 'counts': {}})
                cell = item['counts'].setdefault(code, {'a':0,'m':0,'mi':0,'b':0})
                cell['a'] += 1
                cell['m'] += int(made)
                cell['mi'] += int(not made and result != '3')
                cell['b'] += int(result == '3')
                matchup = matchups.get(pid)
                if matchup:
                    if is_defended:
                        add(matchup['defended'], made)
                    if is_open and range_key:
                        add(matchup['open'+range_key], made)
                        add(matchup['openTotal'], made)
                    add(matchup['withPass' if assisted else 'withoutPass'], made)
                row = nba_players.get(pid)
                if row:
                    if range_key:
                        add(row['shots_'+range_key.lower()], made)
                    add(row['assisted' if assisted else 'unassisted'], made)
                    if is_open or is_defended:
                        add(row['open' if is_open else 'defended'], made)
                    if e.get('clutch'):
                        row['clutch']['pts'] += e.get('points') or 0
                        row['clutch']['fga'] += 1
                        row['clutch']['fgm'] += int(made)
                        if code.startswith('10'):
                            row['clutch']['tpa'] += 1
                            row['clutch']['tpm'] += int(made)
            if pid in opponent_ids and explicit_defender and defender in own_ids:
                if attempt:
                    d = defenses.get(defender)
                    if d:
                        add(d['defendedTotal'], made)
                        if range_key:
                            add(d['defended'+range_key], made)
                    row = nba_players.get(defender)
                    if row:
                        add(row['defended_total'], made)
                        if range_key:
                            add(row['defended_'+range_key.lower()], made)
                results.add(result)
                shot_codes.add(code)
                defended_events.append({'matchid':mid,'defenderId':defender,'shooterId':pid,
                    'defender':name(defender),'shooter':name(pid),'opponent':match.get('opponent'),
                    'shot_type':code,'shot_result':result,'comment':f"Q{e.get('period')} {e.get('clock',0)//60}:{e.get('clock',0)%60:02d} · {e.get('playDescription') or e.get('defenderSource') or 'API attribution'}",
                    'attempt':attempt, 'made':made})
        # Use the official saved defended total when more complete than event attribution.
        for shot in (match.get('shooting') or {}).get('players', []):
            pid = str(shot.get('playerId'))
            value = shot.get('defended') or {}
            row = nba_players.get(pid)
            if row and (value.get('attempts') or 0) > row['defended_total']['a']:
                previous = row['defended_total']
                official = {'m':value.get('made') or 0,'a':value.get('attempts') or 0}
                d = defenses[pid]['defendedTotal']
                d['a'] += official['a'] - previous['a']
                d['m'] += official['m'] - previous['m']
                row['defended_total'] = official
        nba.extend(nba_players.values())
        team_rows.append({'matchid':mid,'result':match['result'],'tactic_group':tactic_group,
                          'team':stats(match['totals']),'opponent':stats(match['opponentTotals'])})
        home, away = (match.get('team'),match.get('opponent')) if match.get('home') else (match.get('opponent'),match.get('team'))
        delta = match.get('effortDelta')
        selected_score, opponent_score = match.get('score','').split('–') if '–' in match.get('score','') else ('?','?')
        score = f'{selected_score}–{opponent_score}' if match.get('home') else f'{opponent_score}–{selected_score}'
        matches.append({'matchid':mid,'start_time':match.get('scheduledAt',''),'home_team':home,'away_team':away,
            'score':score,'detected_side':'Home' if match.get('home') else 'Away','result':match['result'],'status':'Used',
            'selected_tactics':tactics(match.get('ratings') or {}),'opponent_tactics':tactics(match.get('opponentRatings') or {}),
            'effort': 'Individual effort unavailable' if delta is None else 'Home effort minus away effort: '+str(delta),
            'effort_display': {'stronger': 'Unavailable' if delta is None else home if delta >= 0 else away,
                'other': '' if delta is None else away if delta >= 0 else home,
                'symbol': '' if delta is None else '==' if delta == 0 else '>>' if abs(delta)==2 else '>'}})
    known_contest = sum(bool(e.get('defenseState') in {'open','defended'} or e.get('contestLevel') or (e.get('primaryDefenderId') and e['primaryDefenderId'] != ZERO_UUID))
                        for event in report.get('eventReports', []) for e in event.get('shots', []) if e.get('countsAsAttempt'))
    known_defense = bool(known_contest) or any(row['defendedTotal']['a'] for row in defenses.values())
    for row in summary:
        if row['playerId'] not in invalid_minutes and row['playerId'] in derived_seconds:
            row['mins']=round(derived_seconds[row['playerId']]/60,1)
    for row in matchups.values():
        if not row['lineup_valid']:
            row['teamOn']=row['teamOff']=None
        if not known_contest:
            for key in ('defended','openClose','openMid','openThree','openTotal'):
                row[key] = None
        row['total_attempts'] = row['withPass']['a'] + row['withoutPass']['a']
    for row in defenses.values():
        if not row['lineup_valid']:
            row['teamDefOn']=row['teamDefOff']=None
        row['total_attempts'] = row['defendedTotal']['a']
        if not known_defense:
            for key in ('defendedTotal','defendedClose','defendedMid','defendedThree'):
                row[key] = None
    def code_sort(code):
        return (0,int(code)) if str(code).isdigit() else (1,str(code))
    codes = sorted(shot_codes, key=code_sort)
    offense_rows = []
    for row in offense.values():
        row['counts'] = {code:row['counts'].get(code, {'a':0,'m':0,'mi':0,'b':0}) for code in codes}
        row['total'] = {key:sum(cell[key] for cell in row['counts'].values()) for key in ('a','m','mi','b')}
        offense_rows.append(row)
    return {'team_name':report.get('teamName'),'submitted_matches':report.get('submittedMatches',report['usedMatches']+len(report.get('skipped',[]))),
        'used_matches':report['usedMatches'],'skipped_matches':len(report.get('skipped',[])),
        'wins':report['wins'],'losses':report['losses'],'warnings':report.get('warnings',[]),
        'player_summary':summary,'matches':matches,'matchup':list(matchups.values()),'defense':list(defenses.values()),
        'tactic_minutes':[{'key':g,'label':g.title(),'positions':[
            {'key':pos,'label':label,'players':[{'playerId':pid,'name':name(pid),'mins':round(value,1)}
              for pid,value in sorted(minutes[g][pos].items(),key=lambda pair:(-pair[1],name(pair[0])))[:3]]}
            for pos,label in zip(POSITIONS,('PG','SG','SF','PF','C'))]} for g in ('inside','outside','balanced')],
        'offense':{'players':offense_rows,'shot_types':codes},
        'defended_shots':{'players':sorted({e['defender'] for e in defended_events}),'shot_types':codes,'results':sorted(results),'events':defended_events},
        'nba_dashboard':{'players':nba,'team_rows':team_rows},'return_state':{},
        'selected_team_key':report.get('teamId'),'input_matchids':[m['matchId'] for m in report.get('matches',[])],
        'playerNames':names,'coverage':{'contest':bool(known_contest),'defense':known_defense,'events':bool(report.get('eventCoverageGames')),
            'lineups':sum((m.get('reconstruction') or event_by_match.get(m['matchId'],{}).get('reconstruction') or {}).get('status')=='validated' for m in report.get('matches',[]))}}


def render_report(report, fields, username=''):
    from web_tool import MULTI_REPORT_HTML
    view = presentation(report)
    report = dict(report, playerNames=view['playerNames'])
    # Events already contain the analyzed shot facts. Avoid embedding the same
    # feed three times; flat events remain lossless for CSV/JSON inspection.
    report.pop('eventReports', None)
    report.pop('shotLog', None)
    template = MULTI_REPORT_HTML
    template = template.replace('BBAPI user:', 'New site · Manager:')
    template = template.replace('href="/"', 'href="/beta/multi-match"').replace('href="/legacy/"', 'href="/beta/multi-match"')
    template = template.replace('fetch("/export-multi"', 'fetch("/beta/export-multi"')
    template = template.replace('const data = {{ report_json | tojson }};', '''const sourceReport = JSON.parse(document.getElementById('native-report').textContent);
      sourceReport.shotLog=(sourceReport.events||[]).filter(e=>e.eventType==='Shot'&&!e.isCommentary);
      const data = {{ report_json|tojson }};
      function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
      function matchLabel(id){const m=sourceReport.matches.find(m=>m.matchId===id);return escapeHtml(m ? `${m.scheduledAt?.slice(0,10)||'Match'} · ${m.opponent}` : 'Match')}
    ''')
    template = template.replace('addOffCells(out[getShotRange(code)], cell);', 'const range=getShotRange(code);if(out[range])addOffCells(out[range],cell);')
    template = template.replace('const value = String(code);\n        if (value.startsWith', 'const value = String(code);\n        if(!/^\\d+$/.test(value))return "unknown";\n        if (value.startsWith')
    template = template.replace('const shotResultLabel = {', 'shotTypeLabel["400"]="Inside";\n      const shotResultLabel = {')
    template = template.replace('JSON.stringify({ format, report: data })','JSON.stringify({ format, report: {...sourceReport, aggregate: data} })')
    template = re.sub(r'<form id="singleMatchForm".*?</form>', '''<form id="singleMatchForm" method="post" action="/beta/multi-match" hidden><input name="match_ids" id="singleMatchId"><input name="team_id" value="{{ source_report.teamId }}"></form>''',template, flags=re.S)
    template = template.replace('String(row.matchid).match(/^\\d+$/)', 'Boolean(row.matchid)')
    # Keep opaque identifiers for filtering/navigation, but use human labels in cells.
    template = template.replace('>${row.matchid}</button>', '>${matchLabel(row.matchid)}</button>')
    template = template.replace('<td>${ev.matchid}</td>', '<td>${matchLabel(ev.matchid)}</td>')
    # Escape external labels inserted into the inherited template's HTML strings.
    for expression in ('row.name','row.home_team','row.away_team','row.status','row.label','player.name','item','ev.defender','ev.shooter','ev.opponent','ev.comment','group.label','position.label','tactics.offense_label || tactics.offense || "-"','tactics.defense_label || tactics.defense || "-"','stronger','other','row.effort || ""'):
        template = template.replace('${'+expression+'}', '${escapeHtml('+expression+')}')
    # Null is different from an actual empty sample.
    for signature in ('shotStatHtml(stat)','defenseStatHtml(stat)','defensePctHtml(stat)'):
        template = template.replace('function '+signature+' {','function '+signature+' {\n        if(stat == null)return "Unavailable";')
    template = template.replace('name,\n          matches: new Set(),', 'name,\n          lineup_valid:true,assists_valid:true,turnovers_valid:true,\n          matches: new Set(),')
    template = template.replace('item.matches.add(row.matchid);', 'item.matches.add(row.matchid);\n          for(const flag of ["lineup_valid","assists_valid","turnovers_valid"])item[flag]=item[flag]&&row[flag]===true;')
    template = template.replace('function renderNbaTable(columns, rows, emptyColspan, emptyMessage) {','''function renderNbaTable(columns, rows, emptyColspan, emptyMessage) {
        const requirements={teamDefOn:'lineup_valid',teamDefOff:'lineup_valid',clutchPm:'lineup_valid',clutchAst:'assists_valid',clutchTo:'turnovers_valid'};
        columns=columns.map(c=>requirements[c.key]?{...c,value:r=>r[requirements[c.key]]?c.value(r):"Unavailable",sortValue:r=>r[requirements[c.key]]?(c.sortValue?c.sortValue(r):Number(c.value(r))):null}:c);
        if(nbaViewFilter.value==='defense' && !data.coverage.defense) columns=columns.map(c=>c.key==='name'?c:{...c,value:()=>"Unavailable",sortValue:()=>null});
        if(nbaViewFilter.value==='shooting' && !data.coverage.contest) columns=columns.map(c=>['open','defended'].includes(c.key)?{...c,value:()=>"Unavailable",sortValue:()=>null}:c);
        if(nbaViewFilter.value==='clutch' && sourceReport.eventCoverageGames===0){rows=[];emptyMessage='Public events unavailable; clutch figures cannot be calculated.'}
    ''')
    template = template.replace('${column.render ? column.render(row) : column.value(row)}', '${column.key === "name" || column.key === "label" ? escapeHtml(column.value(row)) : column.render ? column.render(row) : column.value(row)}')
    # Empty multiselect means no rows, rather than accidentally selecting everything.
    template = template.replace('if (selectedDefenders.size && !selectedDefenders.has(ev.defender))','if (!selectedDefenders.has(ev.defender))')
    template = template.replace('if (selectedShotTypes.size && !selectedShotTypes.has(ev.shot_type))','if (!selectedShotTypes.has(ev.shot_type))')
    template = template.replace('if (selectedResults.size && !selectedResults.has(ev.shot_result))','if (!selectedResults.has(ev.shot_result))')
    template = template.replace('const madeCount = filtered.filter', 'const attempts = filtered.filter(ev=>ev.attempt);\n        const madeCount = attempts.filter')
    template = template.replace('const fgPct = filtered.length ? ((madeCount / filtered.length)', 'const fgPct = attempts.length ? ((madeCount / attempts.length)')
    template = template.replace('const fgPct = attempts.length ? ((madeCount / attempts.length) * 100).toFixed(1) + "%" : "0.0%";', 'const fgPct = attempts.length ? ((madeCount / attempts.length) * 100).toFixed(1) + "%" : "Unavailable";')
    template = template.replace('Event-derived split based on whether the play-by-play identified a defender on the shot.', 'Defense wrappers name the opposing player; passing wrappers name a teammate. A known passer-only shot has no named primary defender. Unresolved actors are labeled separately.')
    template = template.replace('function playerPassesGlobalFilters(row, attempts = 0, minutes = 0) {', 'function playerPassesGlobalFilters(row, attempts = 0, minutes = 0) {\n        if(!minutes)minutes=data.player_summary.find(p=>p.name===row.name)?.mins||0;')
    template = template.replace('Filters update detailed tables only. Summary and detections stay based on the full aggregate.', 'Result/tactic filters select matches and events. Player and threshold filters select aggregate rows. NBA dashboard filters recalculate its totals; summary and detections use the full aggregate.')
    template = template.replace('<h2>Player Matchup Overview</h2>', '<h2>Player Matchup Overview</h2><p class="coverage-note">Defenders and passers follow the play-by-play sentence roles. On/off figures are shown when reconstructed lineups reconcile with the official minutes and plus/minus.</p>')
    template = template.replace('<h2>Player Defense Overview</h2>', '<h2>Player Defense Overview</h2><p class="coverage-note">Defense includes named opponents recovered from play-by-play. On/off figures require a validated reconstruction. Saved API totals may cover additional attempts.</p>')
    template = template.replace('<h2>Defended Shot Log</h2>', '<h2>Defended Shot Log</h2><p class="coverage-note">Includes selected-team defenders from direct API fields or reconstructed play-by-play roles. The all-shot log retains the attribution source.</p>')
    template = template.replace('These filters apply only to this NBA-style dashboard. Estimated and proxy metrics are labeled in the glossary.', 'These filters apply only to this NBA-style dashboard. On/off and clutch roles appear only when their reconstruction reconciles with official statistics. Event coverage: {{ source_report.eventCoverageGames or 0 }}/{{ source_report.usedMatches }} games. Estimates and proxies are labeled in the glossary.')
    template = template.replace('Findings favor large percentage swings', 'On/off findings use validated reconstructed lineups. Findings favor large percentage swings')
    template = template.replace('</head>', '<link rel="stylesheet" href="/static/legacy-beta-theme.css"><link rel="stylesheet" href="/static/new-multi-report.css"></head>')
    template = template.replace('<body>', '<body><header class="legacy-site-header"><div class="legacy-site-inner"><strong>BuzzerBeater · New site</strong><nav><a href="/beta/">Home</a><a href="/beta/multi-match">Multi match</a><a href="/legacy/">Old site</a></nav></div></header>')
    # Supplementary facts retain their original available fields and opponent names.
    template = template.replace('    <div id="nbaGlossaryModal"', '{% include "beta/multi_supplement.html" %}\n    <div id="nbaGlossaryModal"')
    return render_template_string(template, report_json=view, source_report=report, username=username, password='', report=report, names=view['playerNames'])
