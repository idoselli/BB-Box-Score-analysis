# NIKA Multi Match Team Aggregate parity — 12 November 2026

This audit covers **Multi Match Team Aggregate only**. Other modes are out of
scope. Full data parity remains limited by the API items in the
[short developer request list](multi-match-api-requests.md).

## Implementation

The new-site report now adapts its source data to the original
`MULTI_REPORT_HTML` renderer. It shares the legacy panel order, table columns,
tactic grouping, color bands, typography, sorting, multiselect controls,
dashboard tabs/glossary and supported detection rules. The old site's report
code and routes are unchanged.

The new-site form accepts explicit match IDs, club schedules and national
schedules, with a team chooser when the common team is ambiguous. Public API
pagination, a maximum of 30 matches and the manager's API quotas still apply.

| Old aggregate feature | New-site status |
| --- | --- |
| Summary cards and Match Summary | Restored; scores, side, result, both tactics/GDP, effort difference; extra rating/sublevel/rebounding/PP100 panel retained |
| Tactic Position Minutes | Same Inside / Outside / Balanced cards, PG–C, top three players per role; only valid saved position splits, zero-minute entries excluded |
| Player Summary | Same sortable totals and shooting columns; box-score minute precision |
| Player Matchup Overview | Restored columns and color bands; sentence-role passing and open/defended splits; on/off available for validated reconstructions |
| Player Defense Overview | Restored columns and color bands; API/reconstructed event ranges and saved defended totals; on/off available for validated reconstructions |
| Defended Shot Log | Same defender/shot-type/result multiselects and summary; API and play-by-play-attributed selected-team defense; unresolved attribution remains in the all-shot log |
| NBA-Style Dashboard | All six original views: Traditional, Advanced Lite, Shooting, Defense, Clutch, Four Factors; same filters, sorting and glossary |
| Detections & Suggestions | Same high-usage, shot-diet, range-efficiency and supported defended-shot rules; same grouped cards/table, minimum eight attempts; on/off findings enabled for validated reconstructions |
| Offense Shot Profile By Player | Restored per-shot-type columns, made/missed/blocked totals and range grouping |
| Global filters | Player, result, tactic group, attempts and minutes; reset. As in the old renderer, result/tactic affect match/event selection; NBA dashboard filters separately recalculate its own totals |
| Exports | JSON, CSV ZIP and combined CSV; include native facts and the derived `aggregate` presentation. All-shot/event CSV and Print/PDF retained |
| Extra shooting facts | Team/opponent zone and player split tables retained behind side buttons |

Clutch points and field-goal/three-point figures use pre-play score margin.
Clutch assists use the linked shot's pre-play state, not the score after the
basket. Clutch assists/turnovers are enabled when their full-game actor counts
match every player's official totals. Reconstructed lineups must identify five
starters per side, follow a consistent substitution/swap timeline and reconcile
with official scores, field goals and plus/minus. Whole-minute totals must be
compatible with the floor or ceiling of event minutes. If they differ from
nearest-minute timing, complete player FG/plus-minus evidence is required;
clock timing stays unvalidated and displayed totals retain official minutes.
A discrepancy of a full minute or more still rejects the reconstruction. Exact role
seconds are used only when a unique role assignment also matches the saved
position minutes. Per-row flags prevent incomplete games from becoming fake
zero on/off or clutch figures. A failed game no longer erases the valid subset:
both on/off splits use the same validated games, and an On/off games column
shows validated games / games played. Partial coverage is highlighted in both
main tables and the NBA Defense view, preserved in exports, and stated in
detection evidence. Empty samples say No attempts; unavailable is reserved for
missing validation. Clutch plus/minus still requires every contributing game.

The English commentary catalog was confirmed by the owner. Reconstructed shot descriptions summarize recorded shot/actor/result facts and are labeled accordingly; they do not invent movement, contest intensity or an original wording variation. Defense wrappers
name the opponent; passing wrappers name a teammate. Direct API attribution
takes precedence. The same role grammar applies to structured events, including
blocked-assist outcomes where the second actor is an opponent. Complete supplied
shot sentences without a defender classify as open; result-only text and
unresolved actors remain distinct. Original template wording cannot be recovered
from a bare event enum when the API omits text/variation codes.

Advanced metrics retain the old formulas and labels. Reconstructed timing and
role data carry their provenance and validation status in exports and per-match
expandable details.

## Names and scrolling

- A shared directory contains players from **both teams across all loaded
  matches**, not just the selected team's summary. Event actor, opponent shooting,
  matchup, tactic and defense labels use it.
- Truly unresolved referenced names can be repaired through a bounded maximum
  of eight player reads per report. Quota/auth/transient errors stop that repair;
  they do not destroy the report. A missing label is shown as Unknown player,
  with an identifying number where needed; raw IDs remain in exports/tooltips.
- Equal full names receive stable numbered display labels in the presentation,
  keeping the inherited name-keyed dashboard from merging different players.
- Every report table has sticky headers, keyboard-focusable bounded scrolling,
  Compact/Comfortable/Large height selection and Expand/Collapse. Comfortable
  height is capped at 520px; mobile uses a smaller default.
- Public event/shot tables show 200 rows per page with Previous/Next and complete
  CSV/JSON exports. All events remain accessible. The browser payload embeds the flat event feed once, derives the shot-log view from it, and omits duplicate helper eventReports. No long page-wide event dump.

## Evidence and checks

- Israel U21, season 73, last ten completed games (7 September–9 November):
  all ten have complete, consistent lineups, player FG totals and plus/minus.
  Eight previously failed the nearest-minute check alone; the largest total
  difference is 39 seconds. All ten now contribute on/off counts. Separate
  clock/position validation and official-minute fallbacks remain visible.
- The Israel U21 report was checked in Chromium at 1440px and 390px, including
  complete and mixed-validity coverage, actual zero-attempt off-court samples,
  all NBA views, result/tactic filters, bounded scrolling and legacy colors.
- Live OpenAPI contract reread at https://next-api.buzzerbeater.com/v1/public.json.
  Event play facts are available despite an outdated prose migration statement.
- A captured production match provides 530 events, 199 shot events and both
  rosters. Selected-team attempts reconcile at 84 and field-goal points at 53.
  Although direct defender fields are absent, sentence actor roles recover 112 defended and 87 open/pass-assisted events; block attribution matches official totals. Every player's reconstructed minutes and plus/minus reconcile, as do assists and turnovers.
- Chromium compares the old and new renderers with the same underlying match:
  Player Summary, Matchup and Defense colors and font sizes match exactly.
  The first ten core report panels retain their original order.
- Browser checks cover both-side names (no visible UUID labels), actual vertical
  scrolling, height changes, pagination, search, player/minute filters, glossary,
  all six NBA views and JSON/ZIP/combined exports. A 390px viewport has no document
  horizontal overflow and the browser reports no JavaScript errors.
- Synthetic regressions cover all six defense wrappers, passing/open sentence rules, validated starters/substitutions/swaps, missing/inconsistent timelines, official statistical reconciliation, clutch scoring-state links, identity handling, exports and the shared legacy structure.

No application credentials, personal tokens or captured account payloads are
committed. The API requests above are data limitations; the listed visual and
identity fixes do not depend on additional API endpoints.
