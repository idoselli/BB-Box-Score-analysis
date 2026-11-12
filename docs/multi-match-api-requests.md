# Remaining API requests after play-by-play reconstruction

NIKA now uses the owner-confirmed English sentence grammar and equivalent event
actor roles to recover defenders, passers, starters, substitutions and swaps.
Validated games support on/off, separately validated position minutes, clutch plus/minus,
assists and turnovers without new endpoints. Missing direct defender fields
alone no longer block these features.

The remaining requests are:

1. **Individual played effort settings**, if intended to be public. Only
   home-minus-away effort difference is exported, so the two settings cannot
   always be uniquely determined.
2. **Rendered commentary or its template/variation IDs**, if exact original
   sentences are needed. The current event schema exports facts and actors but
   not the sentence text. The supplied sentence catalog explains their roles;
   it cannot identify which wording variant was used in a particular game.
3. **Repair incomplete historical event feeds, or provide starting-lineup
   snapshots for those games.** These are fallbacks for games that cannot pass
   reconstruction checks, rather than a requirement for every match. Document
   and guarantee event actor, substitution-detail and clock semantics.
4. **Document minute accounting and expose per-player/per-position seconds.**
   Integer box-score minutes sometimes differ from nearest-minute event-clock
   totals despite identical FG and plus/minus. Exact seconds would resolve
   timing precision; shot on/off does not need to wait for this endpoint.

Unknown/incomplete records remain labeled. A complete known shot sentence with
no named defender is open under NIKA's commentary definition; an omitted API
field by itself is not treated as a complete sentence.

Evidence from the captured finished game: all 199 shot events resolve to 112
named-defender and 87 passer-only/open events; all 24 blocked-shot defenders
match official block totals. Both starting fives, substitutions and positional
swaps reconcile with every official player's rounded minutes and plus/minus.
Assist and turnover actor totals also reconcile for every player. This is a
verified example, not proof that all historical games have complete records.

Israel U21 season 73's last ten finished games were also checked. All ten match
official player FG and plus/minus; eight have small whole-minute timing
differences (largest total discrepancy: 39 seconds). On/off counts now work for
all ten, with clock validation reported separately and official minutes retained
where timing cannot be confirmed. No additional endpoint is required for this
on/off case.
