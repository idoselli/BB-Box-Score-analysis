# New-site English play-by-play audit — 12 November 2026

Source: owner-provided `en.json`, 10,066 translation keys. NIKA bundles only the
383 `playByPlay.*` / `commentary.*` entries and seven simple physical-event labels
in `beta_v1/data/pbp-en.json`: **390 entries / 891 wording variants**. The source
catalog hash is retained in that file. Unrelated interface translations are excluded.

The old XML has 182 unique entries. Only 23 new variants exactly match an old
entry after placeholder/whitespace normalization. Different composition and
punctuation can also account for a difference; this is not a count of new game mechanics.

## Catalog classification

| Family | Entries | Variants | Treatment |
| --- | ---: | ---: | --- |
| broadcast | 217 | 488 | Delivery, reactions, setups, stat milestones and spoken recaps; no additional plays. |
| defender | 2 | 6 | Short guard and rotating-help tags; preserve separate primary/help roles. |
| display | 4 | 6 | Timeout/speaker presentation; no new statistical rows. |
| flavor | 104 | 186 | Buzz, color, stakes and talk; no additional plays. |
| foul | 4 | 11 | Named fouler kept separate from primary defender; missed shooting fouls are not FGA. |
| free-throw-result | 6 | 23 | One result for an actual FreeThrow row; no invented attempts. |
| free-throw-summary | 6 | 12 | Never expand 2-of-3 or bonus summaries into additional attempts. |
| lineup | 6 | 17 | Incoming/outgoing players and PG–C position; swaps preserve active membership. |
| rebound | 2 | 11 | Offensive/defensive rebounder when recorded. |
| shot | 18 | 91 | Shooter, make/miss, blocker or passer; keep structured shot types/results authoritative. |
| shot-tag | 5 | 9 | Named blocker/passer enriches a physical Shot row only. |
| simple-event | 7 | 7 | Compact score/block/miss/free-throw labels, with event-type context. |
| turnover | 9 | 24 | Stealer versus losing player; lost-handle and eight-second wording supported. |

## Analysis fixes

- Passer and defender are independent; a play can include both, plus a help defender.
- An actual linked Assist event supplies the passer when the shot’s second actor is the defender.
- A clearly stated pass remains in passing splits even if the passer’s name cannot be resolved; no player assist is invented.
- Direct API primary defender / contest / shot facts take precedence over text-derived fallbacks.
- Team membership, duplicate-name ambiguity, initials, accents and Unicode punctuation are checked.
- An explicitly named unresolved defender is unknown, rather than open or a guessed teammate.
- Substitution text can repair a missing position detail without changing roster membership.
- LoseControl participates in active-lineup validation, in addition to turnover attribution.
- API text is displayed verbatim when present. Otherwise the report labels normalized facts.
- The shot log shows passer and help-defender names; event logs show descriptions. Both are searchable.
- CSV/JSON retain actor names, inference provenance, template matches and commentary flags.

## API boundary and verification

The current public schema was checked at `https://next-api.buzzerbeater.com/v1/public.json`.
GameEventType, ShotResult and ShotType enums are unchanged. MatchTextEvent still
does not export rendered text or variation IDs: the catalog alone does not reveal
which wording a particular match used. Structured-only events retain the existing
role fallback and are not reinterpreted as 891 extra event types.

155 unit tests pass. Variant checks iterate every new shot, guard/help, substitution,
rebound, foul, steal, turnover and individual
free-throw outcome variant, and cover compound roles, foul misses, summaries, commentary
duplication, source precedence, duplicate names and missing fields. All ten captured
Israel U21 season-73 games continue to validate official player FG and plus/minus.
Chromium verifies original text, compound roles, description search, CSV downloads,
all six NBA views, bounded panels and a 390px layout without page overflow.

## Complete entry index

The bundled JSON contains the full text. This index records the handling of every entry.

| Key | Variants | Classification |
| --- | ---: | --- |
| `commentary.buzzer.lead.hot` | 2 | broadcast |
| `commentary.buzzer.replay.raised` | 3 | broadcast |
| `commentary.buzzer.tie.hot` | 2 | broadcast |
| `commentary.buzzer.winner.hot` | 3 | broadcast |
| `commentary.call.block.hot` | 2 | shot-tag |
| `commentary.call.block.raised` | 2 | shot-tag |
| `commentary.call.dunk.calm` | 4 | broadcast |
| `commentary.call.dunk.hot` | 5 | broadcast |
| `commentary.call.dunk.raised` | 7 | broadcast |
| `commentary.call.foul.hot` | 2 | broadcast |
| `commentary.call.foul.raised` | 4 | broadcast |
| `commentary.call.layup.calm` | 4 | broadcast |
| `commentary.call.layup.hot` | 5 | broadcast |
| `commentary.call.layup.raised` | 6 | broadcast |
| `commentary.call.miss.calm` | 4 | broadcast |
| `commentary.call.miss.hot` | 4 | broadcast |
| `commentary.call.miss.raised` | 4 | broadcast |
| `commentary.call.putback.raised` | 3 | broadcast |
| `commentary.call.three.calm` | 6 | broadcast |
| `commentary.call.three.hot` | 9 | broadcast |
| `commentary.call.three.raised` | 8 | broadcast |
| `commentary.call.two.calm` | 7 | broadcast |
| `commentary.call.two.hot` | 7 | broadcast |
| `commentary.call.two.raised` | 7 | broadcast |
| `commentary.clutch.winner.hot` | 2 | broadcast |
| `commentary.color.blowout.calm` | 1 | broadcast |
| `commentary.color.cold.calm` | 2 | broadcast |
| `commentary.color.doubleDouble.calm` | 1 | broadcast |
| `commentary.color.ejected.raised` | 1 | broadcast |
| `commentary.color.exhausted.calm` | 3 | broadcast |
| `commentary.color.flow.calm` | 5 | broadcast |
| `commentary.color.foulTrouble.calm` | 1 | broadcast |
| `commentary.color.foulTrouble.raised` | 1 | broadcast |
| `commentary.color.hot.raised` | 3 | broadcast |
| `commentary.color.injury.calm` | 2 | broadcast |
| `commentary.color.leadChanges.calm` | 2 | broadcast |
| `commentary.color.taping.calm` | 2 | broadcast |
| `commentary.color.tripleDouble.raised` | 1 | broadcast |
| `commentary.foul.intentional.raised` | 2 | broadcast |
| `commentary.freeThrow.made.calm` | 5 | free-throw-result |
| `commentary.freeThrow.made.hot` | 3 | free-throw-result |
| `commentary.freeThrow.made.raised` | 5 | free-throw-result |
| `commentary.freeThrow.miss.calm` | 3 | free-throw-result |
| `commentary.freeThrow.miss.hot` | 3 | free-throw-result |
| `commentary.freeThrow.miss.raised` | 4 | free-throw-result |
| `commentary.freeThrow.stakes.calm` | 1 | broadcast |
| `commentary.freeThrow.stakes.raised` | 2 | broadcast |
| `commentary.freeThrow.stakesTie.hot` | 1 | broadcast |
| `commentary.freeThrow.stakesTieShort.hot` | 1 | broadcast |
| `commentary.homer.lead.hot` | 2 | broadcast |
| `commentary.homer.lead.raised` | 2 | broadcast |
| `commentary.homer.loss.calm` | 2 | broadcast |
| `commentary.homer.opponent.calm` | 2 | broadcast |
| `commentary.homer.run.raised` | 2 | broadcast |
| `commentary.homer.score.raised` | 3 | broadcast |
| `commentary.homer.trail.raised` | 2 | broadcast |
| `commentary.homer.win.hot` | 2 | broadcast |
| `commentary.lostHandle.raised` | 1 | broadcast |
| `commentary.period.end.calm` | 2 | broadcast |
| `commentary.period.endTied.calm` | 1 | broadcast |
| `commentary.period.final.hot` | 2 | broadcast |
| `commentary.period.final.raised` | 1 | broadcast |
| `commentary.period.half.calm` | 2 | broadcast |
| `commentary.period.leader.calm` | 2 | broadcast |
| `commentary.period.overtime.hot` | 2 | broadcast |
| `commentary.play.bringUp.calm` | 8 | broadcast |
| `commentary.play.bringUp.raised` | 6 | broadcast |
| `commentary.play.clock.raised` | 5 | broadcast |
| `commentary.play.kickOut.calm` | 5 | broadcast |
| `commentary.play.kickOut.raised` | 1 | broadcast |
| `commentary.play.post.calm` | 6 | broadcast |
| `commentary.play.skip.calm` | 5 | broadcast |
| `commentary.play.skip.raised` | 1 | broadcast |
| `commentary.play.swing.calm` | 8 | broadcast |
| `commentary.rebound.defensive.calm` | 2 | broadcast |
| `commentary.rebound.defensive.raised` | 2 | broadcast |
| `commentary.rebound.offensive.calm` | 1 | broadcast |
| `commentary.rebound.offensive.raised` | 1 | broadcast |
| `commentary.setup.corner.raised` | 2 | broadcast |
| `commentary.setup.deep.raised` | 2 | broadcast |
| `commentary.setup.drive.calm` | 2 | broadcast |
| `commentary.setup.drive.raised` | 4 | broadcast |
| `commentary.setup.halfCourt.raised` | 3 | broadcast |
| `commentary.setup.jumper.calm` | 2 | broadcast |
| `commentary.setup.jumper.raised` | 3 | broadcast |
| `commentary.setup.longRange.raised` | 2 | broadcast |
| `commentary.setup.post.calm` | 1 | broadcast |
| `commentary.setup.post.raised` | 2 | broadcast |
| `commentary.setup.short.calm` | 1 | broadcast |
| `commentary.setup.short.hot` | 1 | broadcast |
| `commentary.setup.short.raised` | 1 | broadcast |
| `commentary.setup.three.calm` | 2 | broadcast |
| `commentary.setup.three.hot` | 2 | broadcast |
| `commentary.setup.three.raised` | 4 | broadcast |
| `commentary.setup.win.hot` | 3 | broadcast |
| `commentary.spoken.call.block.hot` | 1 | broadcast |
| `commentary.spoken.call.block.raised` | 5 | broadcast |
| `commentary.spoken.call.putback.raised` | 4 | broadcast |
| `commentary.spoken.color.blowout.calm` | 1 | broadcast |
| `commentary.spoken.color.cold.calm` | 1 | broadcast |
| `commentary.spoken.color.doubleDouble.calm` | 1 | broadcast |
| `commentary.spoken.color.foulTrouble.calm` | 1 | broadcast |
| `commentary.spoken.color.foulTrouble.raised` | 1 | broadcast |
| `commentary.spoken.color.hot.raised` | 1 | broadcast |
| `commentary.spoken.color.leadChanges.calm` | 1 | broadcast |
| `commentary.spoken.color.tripleDouble.raised` | 1 | broadcast |
| `commentary.spoken.foul.intentional.raised` | 1 | broadcast |
| `commentary.spoken.freeThrow.stakes.calm` | 1 | broadcast |
| `commentary.spoken.freeThrow.stakes.raised` | 1 | broadcast |
| `commentary.spoken.freeThrow.stakesTie.hot` | 1 | broadcast |
| `commentary.spoken.homer.lead.hot` | 1 | broadcast |
| `commentary.spoken.homer.lead.raised` | 1 | broadcast |
| `commentary.spoken.homer.loss.calm` | 1 | broadcast |
| `commentary.spoken.homer.opponent.calm` | 2 | broadcast |
| `commentary.spoken.homer.run.raised` | 1 | broadcast |
| `commentary.spoken.homer.score.raised` | 2 | broadcast |
| `commentary.spoken.homer.trail.raised` | 1 | broadcast |
| `commentary.spoken.homer.win.hot` | 1 | broadcast |
| `commentary.spoken.period.end.calm` | 3 | broadcast |
| `commentary.spoken.period.endTied.calm` | 1 | broadcast |
| `commentary.spoken.period.final.hot` | 1 | broadcast |
| `commentary.spoken.period.final.raised` | 3 | broadcast |
| `commentary.spoken.period.half.calm` | 3 | broadcast |
| `commentary.spoken.period.leader.calm` | 1 | broadcast |
| `commentary.spoken.rebound.defensive.calm` | 5 | broadcast |
| `commentary.spoken.rebound.defensive.raised` | 1 | broadcast |
| `commentary.spoken.rebound.offensive.calm` | 4 | broadcast |
| `commentary.spoken.rebound.offensive.raised` | 3 | broadcast |
| `commentary.spoken.setup.corner.calm` | 1 | broadcast |
| `commentary.spoken.setup.corner.hot` | 1 | broadcast |
| `commentary.spoken.setup.corner.raised` | 3 | broadcast |
| `commentary.spoken.setup.deep.hot` | 1 | broadcast |
| `commentary.spoken.setup.deep.raised` | 1 | broadcast |
| `commentary.spoken.setup.drive.calm` | 4 | broadcast |
| `commentary.spoken.setup.drive.hot` | 1 | broadcast |
| `commentary.spoken.setup.drive.raised` | 4 | broadcast |
| `commentary.spoken.setup.halfCourt.hot` | 1 | broadcast |
| `commentary.spoken.setup.jumper.calm` | 4 | broadcast |
| `commentary.spoken.setup.jumper.hot` | 1 | broadcast |
| `commentary.spoken.setup.jumper.raised` | 3 | broadcast |
| `commentary.spoken.setup.longRange.hot` | 1 | broadcast |
| `commentary.spoken.setup.longRange.raised` | 1 | broadcast |
| `commentary.spoken.setup.post.calm` | 4 | broadcast |
| `commentary.spoken.setup.post.raised` | 1 | broadcast |
| `commentary.spoken.setup.short.calm` | 3 | broadcast |
| `commentary.spoken.setup.short.hot` | 1 | broadcast |
| `commentary.spoken.setup.short.raised` | 1 | broadcast |
| `commentary.spoken.setup.three.calm` | 4 | broadcast |
| `commentary.spoken.setup.three.hot` | 3 | broadcast |
| `commentary.spoken.setup.three.raised` | 4 | broadcast |
| `commentary.spoken.setup.win.hot` | 2 | broadcast |
| `commentary.spoken.steal.calm` | 1 | broadcast |
| `commentary.spoken.steal.hot` | 1 | broadcast |
| `commentary.spoken.steal.raised` | 5 | broadcast |
| `commentary.spoken.suspense.clutch.hot` | 1 | broadcast |
| `commentary.spoken.suspense.clutch.raised` | 1 | broadcast |
| `commentary.spoken.tag.answer.calm` | 1 | broadcast |
| `commentary.spoken.tag.answer.raised` | 3 | broadcast |
| `commentary.spoken.tag.assist.calm` | 4 | broadcast |
| `commentary.spoken.tag.assist.raised` | 1 | broadcast |
| `commentary.spoken.tag.assists.calm` | 1 | broadcast |
| `commentary.spoken.tag.assists.raised` | 1 | broadcast |
| `commentary.spoken.tag.bigLead.calm` | 1 | broadcast |
| `commentary.spoken.tag.bigLead.raised` | 1 | broadcast |
| `commentary.spoken.tag.buzzerBeater.hot` | 1 | broadcast |
| `commentary.spoken.tag.comeback.hot` | 1 | broadcast |
| `commentary.spoken.tag.comeback.raised` | 1 | broadcast |
| `commentary.spoken.tag.cut.calm` | 1 | broadcast |
| `commentary.spoken.tag.cut.raised` | 1 | broadcast |
| `commentary.spoken.tag.extend.calm` | 1 | broadcast |
| `commentary.spoken.tag.extend.raised` | 1 | broadcast |
| `commentary.spoken.tag.fastBreak.hot` | 1 | broadcast |
| `commentary.spoken.tag.fastBreak.raised` | 1 | broadcast |
| `commentary.spoken.tag.lead.hot` | 1 | broadcast |
| `commentary.spoken.tag.lead.raised` | 3 | broadcast |
| `commentary.spoken.tag.points.calm` | 1 | broadcast |
| `commentary.spoken.tag.points.raised` | 1 | broadcast |
| `commentary.spoken.tag.run.calm` | 1 | broadcast |
| `commentary.spoken.tag.run.raised` | 1 | broadcast |
| `commentary.spoken.tag.scoring.calm` | 1 | broadcast |
| `commentary.spoken.tag.scoring.raised` | 1 | broadcast |
| `commentary.spoken.tag.threes.calm` | 1 | broadcast |
| `commentary.spoken.tag.threes.raised` | 1 | broadcast |
| `commentary.spoken.tag.tie.hot` | 1 | broadcast |
| `commentary.spoken.tag.tie.raised` | 3 | broadcast |
| `commentary.spoken.timeout.calm` | 5 | broadcast |
| `commentary.spoken.timeout.raised` | 1 | broadcast |
| `commentary.steal.hot` | 2 | broadcast |
| `commentary.steal.raised` | 2 | broadcast |
| `commentary.suspense.clutch.hot` | 2 | broadcast |
| `commentary.suspense.clutch.raised` | 2 | broadcast |
| `commentary.tag.andOne.hot` | 1 | broadcast |
| `commentary.tag.andOne.raised` | 4 | broadcast |
| `commentary.tag.answer.calm` | 1 | broadcast |
| `commentary.tag.answer.raised` | 1 | broadcast |
| `commentary.tag.assist.calm` | 1 | shot-tag |
| `commentary.tag.assist.raised` | 3 | shot-tag |
| `commentary.tag.assists.calm` | 1 | shot-tag |
| `commentary.tag.assists.raised` | 1 | broadcast |
| `commentary.tag.bigLead.calm` | 1 | broadcast |
| `commentary.tag.bigLead.raised` | 1 | broadcast |
| `commentary.tag.buzzerBeater.hot` | 2 | broadcast |
| `commentary.tag.comeback.hot` | 1 | broadcast |
| `commentary.tag.comeback.raised` | 1 | broadcast |
| `commentary.tag.cut.calm` | 1 | broadcast |
| `commentary.tag.cut.raised` | 2 | broadcast |
| `commentary.tag.extend.calm` | 1 | broadcast |
| `commentary.tag.extend.raised` | 2 | broadcast |
| `commentary.tag.fastBreak.hot` | 1 | broadcast |
| `commentary.tag.fastBreak.raised` | 2 | broadcast |
| `commentary.tag.lead.hot` | 2 | broadcast |
| `commentary.tag.lead.raised` | 2 | broadcast |
| `commentary.tag.onePoint.hot` | 2 | broadcast |
| `commentary.tag.onePoint.raised` | 2 | broadcast |
| `commentary.tag.points.calm` | 1 | broadcast |
| `commentary.tag.points.raised` | 2 | broadcast |
| `commentary.tag.run.calm` | 1 | broadcast |
| `commentary.tag.run.raised` | 3 | broadcast |
| `commentary.tag.scoring.calm` | 1 | broadcast |
| `commentary.tag.scoring.raised` | 1 | broadcast |
| `commentary.tag.threes.calm` | 1 | broadcast |
| `commentary.tag.threes.raised` | 2 | broadcast |
| `commentary.tag.tie.hot` | 2 | broadcast |
| `commentary.tag.tie.raised` | 2 | broadcast |
| `commentary.timeout.calm` | 1 | broadcast |
| `commentary.timeout.raised` | 2 | broadcast |
| `commentary.tipoff.calm` | 6 | broadcast |
| `commentary.turnover.calm` | 6 | broadcast |
| `other.p1IsBlockedByP2` | 1 | simple-event |
| `other.p1MakesTheFreeThrow` | 1 | simple-event |
| `other.p1Misses` | 1 | simple-event |
| `other.p1MissesTheFreeThrow` | 1 | simple-event |
| `other.p1Scores` | 1 | simple-event |
| `other.p1ScoresFromThree` | 1 | simple-event |
| `other.stealsTheBallFromP2` | 1 | simple-event |
| `playByPlay.andOne` | 3 | foul |
| `playByPlay.buzz.alleyOop` | 2 | flavor |
| `playByPlay.buzz.andOne` | 2 | flavor |
| `playByPlay.buzz.backCourt` | 1 | flavor |
| `playByPlay.buzz.badPass` | 2 | flavor |
| `playByPlay.buzz.bigLead` | 2 | flavor |
| `playByPlay.buzz.blocked` | 2 | flavor |
| `playByPlay.buzz.buzzerBeater` | 2 | flavor |
| `playByPlay.buzz.clutch` | 2 | flavor |
| `playByPlay.buzz.coldStreak` | 2 | flavor |
| `playByPlay.buzz.deepMade` | 2 | flavor |
| `playByPlay.buzz.doubleDouble` | 1 | flavor |
| `playByPlay.buzz.dunk` | 2 | flavor |
| `playByPlay.buzz.dunkMissed` | 2 | flavor |
| `playByPlay.buzz.eliminated` | 1 | flavor |
| `playByPlay.buzz.firstBasket` | 1 | flavor |
| `playByPlay.buzz.foulTrouble` | 2 | flavor |
| `playByPlay.buzz.fouledOut` | 2 | flavor |
| `playByPlay.buzz.freeThrowsBricked` | 3 | flavor |
| `playByPlay.buzz.hotHand` | 2 | flavor |
| `playByPlay.buzz.largeLateLead` | 2 | flavor |
| `playByPlay.buzz.leadChange` | 2 | flavor |
| `playByPlay.buzz.lostHandle` | 1 | flavor |
| `playByPlay.buzz.missedLayup` | 2 | flavor |
| `playByPlay.buzz.offensiveFoul` | 1 | flavor |
| `playByPlay.buzz.opponentBasket` | 2 | flavor |
| `playByPlay.buzz.playoffs` | 3 | flavor |
| `playByPlay.buzz.putback` | 2 | flavor |
| `playByPlay.buzz.run` | 2 | flavor |
| `playByPlay.buzz.shotClock` | 2 | flavor |
| `playByPlay.buzz.steal` | 2 | flavor |
| `playByPlay.buzz.tenSeconds` | 1 | flavor |
| `playByPlay.buzz.three` | 2 | flavor |
| `playByPlay.buzz.threeSeconds` | 1 | flavor |
| `playByPlay.buzz.tie` | 1 | flavor |
| `playByPlay.buzz.title` | 2 | flavor |
| `playByPlay.buzz.travel` | 2 | flavor |
| `playByPlay.buzz.tripleDouble` | 1 | flavor |
| `playByPlay.color.bigLead` | 2 | flavor |
| `playByPlay.color.buzzerBeater` | 2 | flavor |
| `playByPlay.color.clutch` | 3 | flavor |
| `playByPlay.color.coldStreak` | 2 | flavor |
| `playByPlay.color.doubleDouble` | 2 | flavor |
| `playByPlay.color.firstBasket` | 2 | flavor |
| `playByPlay.color.foulTrouble` | 2 | flavor |
| `playByPlay.color.fouledOut` | 2 | flavor |
| `playByPlay.color.hotStreak` | 2 | flavor |
| `playByPlay.color.largeLateLead` | 2 | flavor |
| `playByPlay.color.leadChange` | 3 | flavor |
| `playByPlay.color.points` | 2 | flavor |
| `playByPlay.color.run` | 2 | flavor |
| `playByPlay.color.threes` | 2 | flavor |
| `playByPlay.color.tie` | 2 | flavor |
| `playByPlay.color.tripleDouble` | 2 | flavor |
| `playByPlay.foul` | 3 | foul |
| `playByPlay.fouledOnMiss` | 3 | foul |
| `playByPlay.freeThrows.awarded` | 1 | free-throw-summary |
| `playByPlay.freeThrows.bonusMade` | 2 | free-throw-summary |
| `playByPlay.freeThrows.bonusMissed` | 2 | free-throw-summary |
| `playByPlay.freeThrows.none` | 2 | free-throw-summary |
| `playByPlay.freeThrows.perfect` | 3 | free-throw-summary |
| `playByPlay.freeThrows.split` | 2 | free-throw-summary |
| `playByPlay.guarded` | 5 | defender |
| `playByPlay.helped` | 1 | defender |
| `playByPlay.intentionalFoul` | 2 | foul |
| `playByPlay.lineup.c` | 3 | lineup |
| `playByPlay.lineup.pf` | 3 | lineup |
| `playByPlay.lineup.pg` | 3 | lineup |
| `playByPlay.lineup.sf` | 3 | lineup |
| `playByPlay.lineup.sg` | 2 | lineup |
| `playByPlay.lineup.swap` | 3 | lineup |
| `playByPlay.made.deep` | 5 | shot |
| `playByPlay.made.dunk` | 8 | shot |
| `playByPlay.made.dunkAssist` | 4 | shot |
| `playByPlay.made.jumper` | 6 | shot |
| `playByPlay.made.jumperAssist` | 5 | shot |
| `playByPlay.made.layup` | 9 | shot |
| `playByPlay.made.layupAssist` | 5 | shot |
| `playByPlay.made.post` | 7 | shot |
| `playByPlay.made.postAssist` | 2 | shot |
| `playByPlay.made.putback` | 4 | shot |
| `playByPlay.made.three` | 8 | shot |
| `playByPlay.made.threeAssist` | 5 | shot |
| `playByPlay.missed.blocked` | 6 | shot |
| `playByPlay.missed.deep` | 2 | shot |
| `playByPlay.missed.dunk` | 2 | shot |
| `playByPlay.missed.inside` | 4 | shot |
| `playByPlay.missed.jumper` | 4 | shot |
| `playByPlay.missed.three` | 5 | shot |
| `playByPlay.rebound.defensive` | 5 | rebound |
| `playByPlay.rebound.offensive` | 6 | rebound |
| `playByPlay.speaker` | 1 | display |
| `playByPlay.stakes.after.knockedOut` | 2 | flavor |
| `playByPlay.stakes.after.relegated` | 2 | flavor |
| `playByPlay.stakes.celebration.confetti` | 2 | flavor |
| `playByPlay.stakes.celebration.courtInvasion` | 2 | flavor |
| `playByPlay.stakes.clutch.advance` | 2 | flavor |
| `playByPlay.stakes.clutch.firstPlace` | 2 | flavor |
| `playByPlay.stakes.clutch.playoffs` | 2 | flavor |
| `playByPlay.stakes.clutch.survival` | 2 | flavor |
| `playByPlay.stakes.clutch.title` | 2 | flavor |
| `playByPlay.stakes.tipoff.clinchChance` | 3 | flavor |
| `playByPlay.stakes.tipoff.clinchFirst` | 2 | flavor |
| `playByPlay.stakes.tipoff.cupRound` | 2 | flavor |
| `playByPlay.stakes.tipoff.decider` | 2 | flavor |
| `playByPlay.stakes.tipoff.elimination` | 2 | flavor |
| `playByPlay.stakes.tipoff.final` | 2 | flavor |
| `playByPlay.stakes.tipoff.mustWin` | 3 | flavor |
| `playByPlay.stakes.tipoff.national` | 2 | flavor |
| `playByPlay.stakes.tipoff.semifinal` | 1 | flavor |
| `playByPlay.stakes.tipoff.seriesGame` | 2 | flavor |
| `playByPlay.stakes.tipoff.survival` | 2 | flavor |
| `playByPlay.stakes.won.advance` | 2 | flavor |
| `playByPlay.stakes.won.firstPlace` | 2 | flavor |
| `playByPlay.stakes.won.game` | 2 | flavor |
| `playByPlay.stakes.won.playoffs` | 3 | flavor |
| `playByPlay.stakes.won.seriesLead` | 1 | flavor |
| `playByPlay.stakes.won.seriesLevel` | 1 | flavor |
| `playByPlay.stakes.won.survival` | 2 | flavor |
| `playByPlay.stakes.won.title` | 3 | flavor |
| `playByPlay.stakes.won.toFinal` | 2 | flavor |
| `playByPlay.steal` | 6 | turnover |
| `playByPlay.talk.calledOutBusted` | 2 | flavor |
| `playByPlay.talk.challengeCheck.boards` | 1 | flavor |
| `playByPlay.talk.challengeCheck.holdUnder` | 1 | flavor |
| `playByPlay.talk.challengeCheck.rivalMargin` | 1 | flavor |
| `playByPlay.talk.challengeCheck.stopStar` | 2 | flavor |
| `playByPlay.talk.challengeCheck.threes` | 1 | flavor |
| `playByPlay.talk.challengeDone.threes` | 1 | flavor |
| `playByPlay.talk.challengeMissed.holdUnder` | 1 | flavor |
| `playByPlay.talk.challengeMissed.noQuarterLost` | 1 | flavor |
| `playByPlay.talk.challengeMissed.stopStar` | 1 | flavor |
| `playByPlay.talk.challengeOn.boards` | 1 | flavor |
| `playByPlay.talk.challengeOn.holdUnder` | 1 | flavor |
| `playByPlay.talk.challengeOn.noQuarterLost` | 1 | flavor |
| `playByPlay.talk.challengeOn.rivalMargin` | 1 | flavor |
| `playByPlay.talk.challengeOn.stopStar` | 1 | flavor |
| `playByPlay.talk.challengeOn.threes` | 1 | flavor |
| `playByPlay.talk.handledBusted` | 1 | flavor |
| `playByPlay.talk.holdUnderBusted` | 1 | flavor |
| `playByPlay.talk.noThreeBusted` | 2 | flavor |
| `playByPlay.talk.starKept` | 2 | flavor |
| `playByPlay.talk.threesKept` | 1 | flavor |
| `playByPlay.talk.tipoff` | 2 | flavor |
| `playByPlay.timeout.called` | 1 | display |
| `playByPlay.timeout.full` | 2 | display |
| `playByPlay.timeout.short` | 2 | display |
| `playByPlay.turnover.backCourt` | 1 | turnover |
| `playByPlay.turnover.badPass` | 4 | turnover |
| `playByPlay.turnover.lostHandle` | 3 | turnover |
| `playByPlay.turnover.offensiveFoul` | 2 | turnover |
| `playByPlay.turnover.shotClock` | 2 | turnover |
| `playByPlay.turnover.tenSeconds` | 2 | turnover |
| `playByPlay.turnover.threeSeconds` | 1 | turnover |
| `playByPlay.turnover.travel` | 3 | turnover |
