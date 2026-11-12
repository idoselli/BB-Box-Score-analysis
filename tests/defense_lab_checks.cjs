'use strict';
const assert=require('node:assert/strict');
const lab=require('../static/defense-lab.js');
const close=(a,b)=>assert(Math.abs(a-b)<1e-9,`${a} != ${b}`);
let passed=0;
const check=(label,run)=>{run();passed++;console.log('PASS '+label);};
const roster=['a','b','c','d','e','f'];
function shot(sequence,updates={}) { return {matchId:'m1',sequenceIndex:sequence,eventType:'Shot',countsAsAttempt:true,player1Id:'s',shotType:'Layup',made:false,primaryDefenderId:'a',isHelped:false,lineupValidated:true,defendingLineup:['a','b','c','d','e'],...updates}; }
function report(events,extraMatches=[]) {
 const match=id=>({matchId:id,scheduledAt:'2026-11-09',opponent:'Opponent',playerLines:roster.map(id=>({player:{id},minutes:20})),opponentPlayerLines:[{player:{id:'s'}},{player:{id:'t'}}],reconstruction:{status:'validated'},opponentTotals:{fieldGoalsAttempts:events.filter(e=>e.matchId===id&&e.eventType==='Shot'&&!e.isCommentary&&e.countsAsAttempt&&['s','t'].includes(e.player1Id)).length}});
 return {teamId:'own',playerNames:Object.fromEntries(roster.map(id=>[id,id.toUpperCase()])),events,matches:[match('m1'),...extraMatches.map(id=>match(id))]};
}
const calc=(events,options,more=[])=>lab.aggregate(lab.prepare(report(events,more)),options);
const player=(data,id='a')=>data.players.find(p=>p.id===id);
check('a shared primary/helper identity counts once in any-role outcomes',()=>{
 const data=calc([shot(0,{helpDefenderId:'a'})]);assert.equal(player(data).any.a,1);assert.equal(player(data).primary.a,1);assert.equal(player(data).help.a,1);
});
check('rotation-only helpers are not counted as primary defenders',()=>{
 const data=calc([shot(0,{primaryDefenderId:null,resolvedDefenderId:'a',inferredHelpDefenderId:'a',pbpFacts:{helpDefenderId:'a',templates:['playByPlay.helped:0']},text:'As A rotates over and alters his shot.'})]);
 assert.equal(player(data).primary.a,0);assert.equal(player(data).help.a,1);assert.equal(data.summary.alterations,1);
});
check('a help flag never invents a named helper or alteration',()=>{
 const data=calc([shot(0,{isHelped:true,shotResult:'ShotBlocked'})]);assert.equal(data.summary.helpMarked,1);assert.equal(data.summary.helpUnknown,1);assert.equal(data.summary.namedHelp,0);assert.equal(data.summary.alterations,0);
});
check('commentary, free throws, fouled misses and own shots are excluded',()=>{
 const data=calc([shot(0),shot(1,{isCommentary:true}),shot(2,{eventType:'FreeThrow'}),shot(3,{countsAsAttempt:false}),shot(4,{player1Id:'a'})]);assert.equal(data.summary.attempts,1);
});
check('duplicate physical sequence rows do not inflate outcomes',()=>{
 const data=calc([shot(0),shot(0)]);assert.equal(data.summary.attempts,1);
});
check('same-shooter exact-type comparison excludes this player from reference',()=>{
 const data=calc([shot(0,{made:true}),shot(1),shot(2,{primaryDefenderId:'b',made:true}),shot(3,{primaryDefenderId:'b',made:true}),shot(4,{primaryDefenderId:'b'})]);
 const r=player(data);assert.equal(r.comparison.attempts,2);assert.equal(r.comparison.referenceAttempts,3);close(r.comparison.delta,-100/6);
});
check('reference excludes helper involvements even in primary-only view',()=>{
 const data=calc([shot(0),shot(1,{primaryDefenderId:'b',helpDefenderId:'a',made:true}),shot(2,{primaryDefenderId:'b',made:true}),shot(3,{primaryDefenderId:'b',made:true}),shot(4,{primaryDefenderId:'b'})],{role:'primary'});
 assert.equal(player(data).comparison.attempts,1);assert.equal(player(data).comparison.referenceAttempts,3);close(player(data).comparison.delta,-200/3);
});
check('different shooters/types and reference samples below three are unmatched',()=>{
 for(const updates of [{player1Id:'t'},{shotType:'CornerThree'}]){
 const data=calc([shot(0),shot(1,{primaryDefenderId:'b',...updates}),shot(2,{primaryDefenderId:'b',...updates}),shot(3,{primaryDefenderId:'b',...updates})]);assert.equal(player(data).comparison.delta,null);}
 assert.equal(player(calc([shot(0),shot(1,{primaryDefenderId:'b'}),shot(2,{primaryDefenderId:'b'})])).comparison.delta,null);
});
check('on/off uses shot snapshots and does not count the bench as on court',()=>{
 const data=calc([shot(0,{made:true}),shot(1,{defendingLineup:['f','b','c','d','e']})]);const a=player(data),f=player(data,'f');assert.equal(a.on.a,1);assert.equal(a.off.a,1);assert.equal(a.on.m,1);assert.equal(f.on.m,0);assert.equal(f.off.m,1);assert.equal(a.onoffGames,1);
});
check('a failed game preserves role outcomes but cannot contaminate valid on/off',()=>{
 const events=[shot(0),shot(1,{matchId:'m2',made:true})],r=report(events,['m2']);r.matches[1].reconstruction.status='unavailable';const data=lab.aggregate(lab.prepare(r));const a=player(data);assert.equal(a.any.a,2);assert.equal(a.on.a,1);assert.equal(a.on.m,0);assert.equal(a.onoffGames,1);assert.equal(a.games,2);assert.deepEqual(a.missingGames,['m2']);
});
check('result/tactic-selected match cohorts recompute baseline and coverage',()=>{
 const data=calc([shot(0),shot(1,{matchId:'m2',made:true})],{matchIds:['m2']},['m2']);assert.equal(data.summary.games,1);assert.equal(player(data).games,1);assert.equal(player(data).on.m,1);
});
check('missing/duplicate/out-of-roster snapshots disable new on/off for that game',()=>{
 for(const updates of [{lineupValidated:false},{defendingLineup:['a','a','b','c','d']},{defendingLineup:['a','a','b','c','d','e']},{defendingLineup:['a','b','c','d','foreign']}]){const data=calc([shot(0,updates)]);assert.equal(data.summary.onoffGames,0);assert.equal(player(data).onoffGames,0);assert.equal(player(data).any.a,1);}
});
check('eFG can reach 150 percent and three-point share is calculated correctly',()=>{
 const r=player(calc([shot(0,{made:true,shotType:'CornerThree'})]));close(lab.rate(r.on,'efg'),150);close(lab.rate(r.on,'threeShare'),100);
});
check('unknown shot types/flags remain unavailable instead of becoming zeros',()=>{
 const r=player(calc([shot(0,{made:true,shotType:null,isHelped:undefined})]));close(lab.rate(r.on),100);assert.equal(lab.rate(r.on,'efg'),null);assert.equal(lab.rate(r.on,'threeShare'),null);assert.equal(lab.rate(r.on,'helpRate'),null);
});
check('help-marked share uses only recorded flags',()=>{
 const r=player(calc([shot(0,{isHelped:true}),shot(1),shot(2,{isHelped:undefined})]));close(lab.rate(r.on,'helpRate'),50);assert.equal(lab.denominator(r.on,'helpRate'),2);
});
check('flagged/unflagged splits follow the chosen role',()=>{
 const r=player(calc([shot(0,{isHelped:false}),shot(1,{primaryDefenderId:'b',helpDefenderId:'a',isHelped:true})],{role:'primary'}));assert.equal(r.sample.a,1);assert.equal(r.flagged.a,0);assert.equal(r.unflagged.a,1);
});
check('missing helpers and no matching shots leave coverage explicit',()=>{
 const data=calc([]);assert.equal(data.summary.attempts,0);assert.equal(data.summary.namedHelp,0);assert.equal(lab.rate(player(data).on),null);
});
console.log(`${passed} defense-lab calculation checks passed`);
