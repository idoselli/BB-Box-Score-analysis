/* Experimental defensive associations. Pure calculations are shared with Node checks. */
(function () {
  'use strict';
  const THREE = new Set(['GenericThree', 'StraightOnThree', 'WingThree', 'CornerThree', 'VeryLong', 'HalfCourtShot']);
  const TWO = new Set(['GenericTwo', 'Elbow', 'Wing', 'BaselineJ', 'TopKey', 'GenericInsideShot', 'Dunk', 'Layup', 'Strong', 'FallAway', 'Hook', 'Spinny', 'TipbackDunk', 'Tipback', 'Putback', 'DrivingLayup']);
  const CONTEST = ['Open', 'Light', 'Contested', 'Smothered'];
  const ZERO = '00000000-0000-0000-0000-000000000000';
  const validId = id => Boolean(id && id !== ZERO);
  function split() { return {a:0, m:0, typeA:0, typeM:0, threeA:0, threeM:0, helpKnown:0, helped:0}; }
  function add(target, shot) {
    target.a++; target.m += Number(shot.made);
    if (THREE.has(shot.type) || TWO.has(shot.type)) {
      target.typeA++; target.typeM += Number(shot.made);
      if (THREE.has(shot.type)) { target.threeA++; target.threeM += Number(shot.made); }
    }
    if (shot.helpKnown) { target.helpKnown++; target.helped += Number(shot.helped); }
  }
  function rate(sample, key='fg') {
    if (key === 'efg') return sample.typeA ? 100 * (sample.typeM + .5 * sample.threeM) / sample.typeA : null;
    if (key === 'threeShare') return sample.typeA ? 100 * sample.threeA / sample.typeA : null;
    if (key === 'helpRate') return sample.helpKnown ? 100 * sample.helped / sample.helpKnown : null;
    return sample.a ? 100 * sample.m / sample.a : null;
  }
  function denominator(sample, key) { return key === 'helpRate' ? sample.helpKnown : ['efg','threeShare'].includes(key) ? sample.typeA : sample.a; }
  function prepare(report) {
    const all = report.events || report.shotLog || [];
    const byMatch = new Map();
    for (const event of all) {
      if (event.eventType !== 'Shot' || event.isCommentary || !event.countsAsAttempt) continue;
      const list = byMatch.get(String(event.matchId)) || [];
      list.push(event); byMatch.set(String(event.matchId), list);
    }
    const games = (report.matches || []).map(match => {
      const own = new Set((match.playerLines || []).map(line => String(line.player?.id)));
      const opponents = new Set((match.opponentPlayerLines || []).map(line => String(line.player?.id)));
      const roster = (match.playerLines || []).filter(line => line.minutes > 0 || line.fieldGoalsAttempts > 0)
        .map(line => ({id:String(line.player.id), minutes:line.minutes || 0}));
      const shots = [];
      const seen = new Set();
      for (const event of byMatch.get(String(match.matchId)) || []) {
        if (!opponents.has(String(event.player1Id))) continue;
        // Duplicate physical rows are never extra attempts in this panel.
        const identity = event.sequenceIndex;
        if (identity != null && seen.has(identity)) continue;
        seen.add(identity);
        const facts = event.pbpFacts || {};
        const ownId = id => validId(id) && own.has(String(id)) ? String(id) : null;
        const legacyHelp = String(event.defenderSource || '').startsWith('sentence:e0003');
        const helper = ownId(event.helpDefenderId) || ownId(event.inferredHelpDefenderId) || ownId(facts.helpDefenderId)
          || (legacyHelp ? ownId(event.resolvedDefenderId) : null);
        const explicitPrimary = ownId(event.primaryDefenderId);
        let primary = explicitPrimary || ownId(event.resolvedDefenderId);
        // A rotation-only sentence identifies a helper, not a second primary.
        if (!explicitPrimary && primary === helper && (legacyHelp || facts.helpDefenderId) && !facts.defenderId) primary = null;
        const alteration = legacyHelp || (facts.templates || []).some(key => key.startsWith('playByPlay.helped:'));
        const helped = event.isHelped === true || Boolean(helper) || alteration;
        const lineup = Array.isArray(event.defendingLineup) ? [...new Set(event.defendingLineup.map(String))] : [];
        const lineupValid = event.lineupValidated === true && event.defendingLineup?.length === 5 && lineup.length === 5 && lineup.every(id => own.has(id));
        shots.push({sequence:event.sequenceIndex, shooter:String(event.player1Id), type:event.shotType,
          made:Boolean(event.made), primary, helper, alteration, helped,
          helpKnown:typeof event.isHelped === 'boolean' || Boolean(helper) || alteration,
          contest:CONTEST.includes(event.contestLevel) ? event.contestLevel : null,
          textKnown:Boolean(event.text || event.sentence || event.commentaryText || event.comment),
          primarySource:explicitPrimary ? 'API' : primary ? String(event.defenderSource || 'participant') : null,
          helperSource:ownId(event.helpDefenderId) ? 'API' : helper ? 'sentence' : null,
          lineup:lineupValid ? lineup : null});
      }
      const expected = match.opponentTotals?.fieldGoalsAttempts;
      const eligible = new Set(roster.map(entry => entry.id));
      for (const shot of shots) for (const id of new Set([...(shot.lineup || []),shot.primary,shot.helper].filter(Boolean))) {
        if (!eligible.has(id)) {
          roster.push({id,minutes:(match.playerLines || []).find(line=>String(line.player?.id)===id)?.minutes || 0});
          eligible.add(id);
        }
      }
      const onoffValid = match.reconstruction?.status === 'validated' && shots.every(shot => shot.lineup)
        && (typeof expected !== 'number' || expected === shots.length);
      return {id:String(match.matchId), label:`${String(match.scheduledAt || '').slice(0,10)} · ${match.opponent || 'Opponent'}`,
        roster, shots, onoffValid};
    });
    return {games, names:report.playerNames || {}};
  }
  function aggregate(prepared, options={}) {
    const chosen = options.matchIds ? new Set(options.matchIds.map(String)) : null;
    const games = prepared.games.filter(game => !chosen || chosen.has(game.id));
    const players = new Map();
    const shots = games.flatMap(game => game.shots);
    const summary = {games:games.length, onoffGames:games.filter(game => game.onoffValid).length,
      attempts:shots.length, namedDefense:0, namedHelp:0, helpMarked:0, helpUnknown:0, alterations:0,
      textAttempts:0, contestKnown:0, contest:Object.fromEntries(CONTEST.map(key => [key,split()])),
      primaryApi:0, primaryInferred:0, helperApi:0, helperInferred:0};
    const player = id => {
      if (!players.has(id)) players.set(id, {id, name:prepared.names[id] || 'Unknown player', games:0, minutes:0,
        onoffGames:0, missingGames:[], primary:split(), help:split(), any:split(), flagged:split(), unflagged:split(),
        alterations:0, on:split(), off:split(), records:[]});
      return players.get(id);
    };
    for (const game of games) {
      for (const entry of game.roster) {
        const row = player(entry.id); row.games++; row.minutes += entry.minutes;
        if (game.onoffValid) row.onoffGames++; else row.missingGames.push(game.id);
        if (game.onoffValid) for (const shot of game.shots) add(shot.lineup.includes(entry.id) ? row.on : row.off, shot);
      }
      for (const shot of game.shots) {
        if (shot.primary) { summary.namedDefense++; summary[shot.primarySource === 'API' ? 'primaryApi' : 'primaryInferred']++; }
        if (shot.helper) { summary.namedHelp++; summary[shot.helperSource === 'API' ? 'helperApi' : 'helperInferred']++; }
        if (shot.helped) { summary.helpMarked++; if (!shot.helper) summary.helpUnknown++; }
        if (shot.alteration) summary.alterations++;
        if (shot.textKnown) summary.textAttempts++;
        if (shot.contest) { summary.contestKnown++; add(summary.contest[shot.contest], shot); }
        // One shot can have two distinct roles; "any" counts it once per player.
        for (const id of new Set([shot.primary,shot.helper].filter(Boolean))) {
          const row = player(id); add(row.any, shot); row.records.push(shot);
          if (shot.primary === id) add(row.primary, shot);
          if (shot.helper === id) add(row.help, shot);
        }
      }
    }
    const bucketKey = shot => validId(shot.shooter) && (TWO.has(shot.type) || THREE.has(shot.type)) ? JSON.stringify([shot.shooter,shot.type]) : null;
    const baseline = new Map();
    for (const shot of shots) {
      const key = bucketKey(shot); if (!key) continue;
      if (!baseline.has(key)) baseline.set(key,split()); add(baseline.get(key),shot);
    }
    const role = ['primary','help'].includes(options.role) ? options.role : 'any';
    for (const row of players.values()) {
      row.flagged=split(); row.unflagged=split(); row.alterations=0;
      const involved = new Map();
      for (const shot of row.records) {
        const key = bucketKey(shot); if (!key) continue;
        if (!involved.has(key)) involved.set(key,split()); add(involved.get(key),shot);
      }
      const matched = {attempts:0, made:0, referenceAttempts:0, expectedMakes:0, delta:null};
      const used = new Set();
      for (const shot of row.records) {
        if (role !== 'any' && shot[role === 'primary' ? 'primary' : 'helper'] !== row.id) continue;
        if (shot.helpKnown) add(shot.helped ? row.flagged : row.unflagged,shot);
        if (shot.alteration && shot.helper===row.id) row.alterations++;
        const key = bucketKey(shot), total = baseline.get(key), own = involved.get(key);
        if (!total || !own) continue;
        const attempts = total.a - own.a, made = total.m - own.m;
        // Require three other shots from this exact shooter/type before comparing.
        if (attempts < 3) continue;
        matched.attempts++; matched.made += Number(shot.made); matched.expectedMakes += made / attempts;
        if (!used.has(key)) { matched.referenceAttempts += attempts; used.add(key); }
      }
      if (matched.attempts) matched.delta = 100 * (matched.made - matched.expectedMakes) / matched.attempts;
      row.comparison = matched;
      row.sample = row[role];
      delete row.records;
    }
    return {version:1, role, summary, players:[...players.values()]};
  }

  function mount(report) {
    const root = document.getElementById('defenseLab'); if (!root) return;
    const prepared = prepare(report), table = root.querySelector('#lab-table');
    const query = root.querySelector('#lab-search'), role = root.querySelector('#lab-role');
    const metric = root.querySelector('#lab-metric'), minimum = root.querySelector('#lab-minimum');
    const hideSmall = root.querySelector('#lab-hide-small'), notice = root.querySelector('#lab-notice');
    let view = 'shots', sort = {key:'attempts',dir:-1}, currentRows = [], currentAnalysis;
    const percent = value => value == null ? 'Not recorded' : `${value.toFixed(1)}%`;
    const pp = value => value == null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(1)} pp`;
    const element = (tag, text, cls) => { const e=document.createElement(tag); if(text!=null)e.textContent=text; if(cls)e.className=cls; return e; };
    function sampleCell(sample) {
      if (!sample.a) return element('span','No attempts','lab-muted');
      const e=element('span',percent(rate(sample))); e.append(element('small',`${sample.m}/${sample.a} made`)); return e;
    }
    function deltaCell(delta, lowIsBetter=true) {
      const e=element('span',pp(delta));
      if (delta!=null && lowIsBetter) e.className=delta < 0 ? 'lab-lower' : delta > 0 ? 'lab-higher' : '';
      return e;
    }
    function onoffCell(row, sample) {
      if (!row.onoffGames) return element('span','Unavailable','lab-muted');
      const n=denominator(sample,metric.value), value=rate(sample,metric.value);
      if (!n) return element('span',sample.a ? 'Not recorded' : 'No attempts','lab-muted');
      const e=element('span',percent(value)); e.append(element('small',`${n} attempts`)); return e;
    }
    function coverage(row) {
      return element('span',`${row.onoffGames}/${row.games} games`,row.onoffGames < row.games ? 'lab-partial' : 'lab-muted');
    }
    const metrics={fg:'Opponent FG%',efg:'Opponent eFG%',threeShare:'Opponent 3PA share',helpRate:'Help-marked share'};
    function render() {
      const matchIds=prepared.games.filter(game => typeof matchPassesGlobalFilters !== 'function' || matchPassesGlobalFilters(game.id)).map(game=>game.id);
      const analysis=aggregate(prepared,{matchIds,role:role.value}); currentAnalysis=analysis;
      const s=analysis.summary, threshold=Math.max(0,Number(minimum.value)||0);
      const globalPlayer=document.getElementById('globalPlayerFilter')?.value || 'all';
      const globalAttempts=Math.max(0,Number(document.getElementById('globalMinAttempts')?.value)||0);
      const globalMinutes=Math.max(0,Number(document.getElementById('globalMinMinutes')?.value)||0);
      let rows=analysis.players.filter(row => (globalPlayer==='all'||row.name===globalPlayer)
        && row.name.toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase()) && row.minutes>=globalMinutes);
      for (const row of rows) {
        const onN=denominator(row.on,metric.value), offN=denominator(row.off,metric.value);
        row.small=view==='shots' ? row.sample.a<threshold : onN<threshold||offN<threshold;
      }
      rows=rows.filter(row=>view==='shots' ? row.sample.a>0 && row.sample.a>=globalAttempts : row.on.a>=globalAttempts);
      if (hideSmall.checked) rows=rows.filter(row=>!row.small);
      root.querySelector('#lab-attempts').textContent=s.attempts;
      root.querySelector('#lab-help').textContent=s.helpMarked;
      root.querySelector('#lab-help-detail').textContent=`${s.namedHelp} with a named helper · ${s.helpUnknown} unnamed`;
      root.querySelector('#lab-alterations').textContent=s.textAttempts||s.alterations ? s.alterations : 'Not recorded';
      root.querySelector('#lab-lineups').textContent=`${s.onoffGames}/${s.games}`;
      root.querySelector('#lab-coverage').textContent=`Named defenders: ${s.namedDefense}/${s.attempts} attempts (${s.primaryApi} API, ${s.primaryInferred} inferred). Named helpers: ${s.namedHelp} (${s.helperApi} API, ${s.helperInferred} sentence). Contest levels: ${s.contestKnown}/${s.attempts}. Text available: ${s.textAttempts}/${s.attempts}.`;
      const labels = CONTEST.map(level=>`${level}: ${s.contest[level].a ? percent(rate(s.contest[level]))+' allowed on '+s.contest[level].a+' attempts' : s.contestKnown ? 'no attempts' : 'not recorded'}`);
      root.querySelector('#lab-contests').textContent=labels.join(' · ');
      notice.textContent=!s.attempts ? 'No opponent shot events in this selection. Include play-by-play when building your report.'
        : view==='onoff' && !s.onoffGames ? 'No validated shot lineups in this selection. On/off is unavailable; named-shot outcomes may still be shown.'
        : role.value==='help' && view==='shots' && !s.namedHelp ? 'No named helpers in these plays. A help flag alone does not identify who helped. Try Any named role or On/off court.'
        : `Observed associations, not a causal rating. ${s.helpUnknown ? s.helpUnknown+' help-marked shots lack a named helper. ' : ''}Filters above apply. Coverage cards describe the selected games.`;
      const columns=view==='shots' ? [
        {key:'name',label:'Player',value:r=>r.name,render:r=>element('strong',r.name)},
        {key:'attempts',label:'Role FGA',value:r=>r.sample.a,render:r=>element('span',r.sample.a)},
        {key:'fg',label:'FG% allowed',value:r=>rate(r.sample),render:r=>sampleCell(r.sample)},
        {key:'primary',label:'Named defense FGA',value:r=>r.primary.a,render:r=>element('span',r.primary.a)},
        {key:'help',label:'Named help FGA',value:r=>s.namedHelp ? r.help.a:null,render:r=>element('span',s.namedHelp ? r.help.a:'Not recorded')},
        {key:'helpFg',label:'Help-marked FG%',value:r=>rate(r.flagged),render:r=>r.flagged.a+r.unflagged.a?sampleCell(r.flagged):element('span','Not recorded','lab-muted')},
        {key:'soloFg',label:'Unmarked FG%',value:r=>rate(r.unflagged),render:r=>r.flagged.a+r.unflagged.a?sampleCell(r.unflagged):element('span','Not recorded','lab-muted')},
        {key:'alterations',label:'Alteration mentions',value:r=>s.textAttempts||s.alterations?r.alterations:null,render:r=>element('span',s.textAttempts||s.alterations?r.alterations:'Not recorded')},
        {key:'comparison',label:'Shooter comparison',value:r=>r.comparison.delta,render:r=>{const e=deltaCell(r.comparison.delta); e.append(element('small',`${r.comparison.attempts}/${r.sample.a} matched · ${r.comparison.referenceAttempts} reference`)); return e;}}
      ] : [
        {key:'name',label:'Player',value:r=>r.name,render:r=>element('strong',r.name)},
        {key:'coverage',label:'On/off games',value:r=>r.onoffGames,render:coverage},
        {key:'on',label:'On court',value:r=>r.onoffGames?rate(r.on,metric.value):null,render:r=>onoffCell(r,r.on)},
        {key:'off',label:'Off court',value:r=>r.onoffGames?rate(r.off,metric.value):null,render:r=>onoffCell(r,r.off)},
        {key:'delta',label:'On minus off',value:r=>r.onoffGames&&rate(r.on,metric.value)!=null&&rate(r.off,metric.value)!=null?rate(r.on,metric.value)-rate(r.off,metric.value):null,
          render:r=>{const on=rate(r.on,metric.value),off=rate(r.off,metric.value);return deltaCell(r.onoffGames&&on!=null&&off!=null?on-off:null,['fg','efg'].includes(metric.value));}},
        {key:'onFga',label:'Opponent FGA on',value:r=>r.onoffGames?r.on.a:null,render:r=>element('span',r.onoffGames?r.on.a:'Unavailable')},
        {key:'offFga',label:'Opponent FGA off',value:r=>r.onoffGames?r.off.a:null,render:r=>element('span',r.onoffGames?r.off.a:'Unavailable')}
      ];
      columns.push({key:'small',label:'Sample',value:r=>r.small?0:1,render:r=>element('span',r.small?'Small sample':'Meets minimum',r.small?'lab-partial':'lab-muted')});
      const col=columns.find(c=>c.key===sort.key)||columns[1];
      rows.sort((a,b)=>{const av=col.value(a),bv=col.value(b);if(av==null)return bv==null?0:1;if(bv==null)return -1;return sort.dir*(typeof av==='string'?av.localeCompare(bv):av-bv)||a.name.localeCompare(b.name);});
      currentRows=rows;
      table.replaceChildren(); const head=element('thead'),hr=element('tr'),body=element('tbody');head.append(hr);table.append(head,body);
      for(const c of columns){const th=element('th'),b=element('button',c.label);b.type='button';b.className='lab-sort';th.setAttribute('aria-sort',col.key===c.key?(sort.dir>0?'ascending':'descending'):'none');b.onclick=()=>{sort={key:c.key,dir:sort.key===c.key?-sort.dir:1};render();};th.append(b);hr.append(th);}
      for(const r of rows){const tr=element('tr');for(const c of columns){const td=element('td');td.append(c.render(r));tr.append(td);}body.append(tr);}
      if(!rows.length){const tr=element('tr'),td=element('td','No players meet this selection. Adjust the role, player search or small-sample filter.','empty');td.colSpan=columns.length;tr.append(td);body.append(tr);}
      root.querySelector('#lab-row-count').textContent=`${rows.length} players · ${s.games} selected games`;
      root.querySelector('#lab-view-note').textContent=view==='shots'
        ? 'FG% is made / attempts in the chosen role. Help-marked and unmarked splits use that same role. Shooter comparison matches the same shooter and exact shot type on other shots where this player is not named as defender/helper; negative means lower shooting.'
        : `${metrics[metric.value]}. Both sides use the same validated games. Negative FG/eFG differences mean lower opponent shooting on court. Shot mix, teammates and opponents can explain the difference.`;
      report.defenseLab={...analysis,filters:{matchIds,role:role.value,view,metric:metric.value,search:query.value,minimum:threshold,hideSmall:hideSmall.checked},visiblePlayerIds:rows.map(r=>r.id)};
    }
    for(const button of root.querySelectorAll('[data-lab-view]'))button.onclick=()=>{
      view=button.dataset.labView; sort={key:view==='shots'?'attempts':'onFga',dir:-1};
      for(const other of root.querySelectorAll('[data-lab-view]'))other.setAttribute('aria-pressed',String(other===button));
      root.querySelector('#lab-role-control').hidden=view!=='shots'; root.querySelector('#lab-metric-control').hidden=view!=='onoff';render();
    };
    for(const control of [query,role,metric,minimum,hideSmall])control.addEventListener(control===query||control===minimum?'input':'change',render);
    for(const id of ['globalPlayerFilter','globalResultFilter','globalTacticFilter','globalMinAttempts','globalMinMinutes'])document.getElementById(id)?.addEventListener('change',render);
    for(const id of ['globalMinAttempts','globalMinMinutes'])document.getElementById(id)?.addEventListener('input',render);
    document.getElementById('globalResetFilters')?.addEventListener('click',render);
    root.querySelector('#lab-download').onclick=()=>{
      const headers=['playerId','player','role','roleFGA','roleMade','roleFGPercent','primaryFGA','helpFGA','alterationMentions','helpMarkedFGA','helpMarkedMade','unmarkedFGA','unmarkedMade','matchedFGA','referenceFGA','shooterDifferencePP','onoffGames','eligibleGames','opponentFGAOn','opponentFGAOff','metric','onValue','offValue','onMinusOffPP'];
      const values=currentRows.map(r=>{const on=r.onoffGames?rate(r.on,metric.value):null,off=r.onoffGames?rate(r.off,metric.value):null;return [r.id,r.name,role.value,r.sample.a,r.sample.m,rate(r.sample),r.primary.a,currentAnalysis.summary.namedHelp?r.help.a:null,currentAnalysis.summary.textAttempts?r.alterations:null,r.flagged.a,r.flagged.m,r.unflagged.a,r.unflagged.m,r.comparison.attempts,r.comparison.referenceAttempts,r.comparison.delta,r.onoffGames,r.games,r.onoffGames?r.on.a:null,r.onoffGames?r.off.a:null,metric.value,on,off,on!=null&&off!=null?on-off:null];});
      const safe=v=>{let s=v==null?'':String(v);if(/^[=+\-@\t\r]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
      const csv=[headers,...values].map(row=>row.map(safe).join(',')).join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='nika-defense-lab-beta.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    };
    render();
  }
  const api={prepare,aggregate,rate,denominator};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  if(typeof document!=='undefined'&&typeof sourceReport!=='undefined')mount(sourceReport);
})();
