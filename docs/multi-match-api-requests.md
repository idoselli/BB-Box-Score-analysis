# Optional API improvements after play-by-play reconstruction

NIKA now uses the owner-confirmed English sentence grammar and equivalent event
actor roles to recover defenders, passers, starters, substitutions and swaps.
Validated games support on/off, separately validated position minutes, clutch plus/minus,
assists and turnovers without new endpoints. Missing direct defender fields
alone no longer block these features.

There is no confirmed missing endpoint blocking core multi-match analysis for
complete event feeds. The owner considers these two remaining differences low priority:

1. **Individual played effort settings**, if intended to be public. Only
   home-minus-away effort difference is exported, so the two settings cannot
   always be uniquely determined.
2. **Rendered commentary or its template/variation IDs**, if exact original
   sentences are needed. The current event schema exports facts and actors but
   not the sentence text. The supplied sentence catalog explains their roles;
   it cannot identify which wording variant was used in a particular game.

Starting fives, substitutions, swaps and event-clock seconds are reconstructed
from play-by-play. Exact-second or lineup snapshot endpoints are optional
cross-checks, not requirements. Only genuinely missing/corrupt events would
prevent recovery; that has not been established for the tested Israel U21 games.

The new-site `en.json` catalog has now been audited and bundled. See
[new-site-pbp-audit.md](new-site-pbp-audit.md) for all 390 relevant entries and
the distinction between physical plays and broadcast/color/summary text.

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
