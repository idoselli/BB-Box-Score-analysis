# NIKA Multi Match Team Aggregate parity — 11 November 2026

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
| Player Matchup Overview | Restored columns and color bands; assisted-result and explicit open/contest splits; on/off unavailable |
| Player Defense Overview | Restored columns and color bands; explicit event ranges and saved defended totals; on/off unavailable |
| Defended Shot Log | Same defender/shot-type/result multiselects and summary; only attributed selected-team defense; unknown attribution remains in the all-shot log |
| NBA-Style Dashboard | All six original views: Traditional, Advanced Lite, Shooting, Defense, Clutch, Four Factors; same filters, sorting and glossary |
| Detections & Suggestions | Same high-usage, shot-diet, range-efficiency and supported defended-shot rules; same grouped cards/table, minimum eight attempts; no invented on/off findings |
| Offense Shot Profile By Player | Restored per-shot-type columns, made/missed/blocked totals and range grouping |
| Global filters | Player, result, tactic group, attempts and minutes; reset. As in the old renderer, result/tactic affect match/event selection; NBA dashboard filters separately recalculate its own totals |
| Exports | JSON, CSV ZIP and combined CSV; include native facts and the derived `aggregate` presentation. All-shot/event CSV and Print/PDF retained |
| Extra shooting facts | Team/opponent zone and player split tables retained behind side buttons |

Clutch points and field-goal/three-point figures are calculated from pre-play
score margin and recorded events. Clutch AST, TO and +/− stay explicitly
unavailable pending actor semantics and lineup data. Advanced metrics such as
TS%, usage proxy, per-36 and estimated possessions retain the old formulas and
labels. Missing contest/defender history is not interpreted as open or zero.

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

- Live OpenAPI contract reread at https://next-api.buzzerbeater.com/v1/public.json.
  Event play facts are available despite an outdated prose migration statement.
- A captured production match provides 530 events, 199 shot events and both
  rosters. Selected-team attempts reconcile at 84 and field-goal points at 53.
  It has no explicit defender coverage, exercising the unavailable state.
- Chromium compares the old and new renderers with the same underlying match:
  Player Summary, Matchup and Defense colors and font sizes match exactly.
  The first ten core report panels retain their original order.
- Browser checks cover both-side names (no visible UUID labels), actual vertical
  scrolling, height changes, pagination, search, player/minute filters, glossary,
  all six NBA views and JSON/ZIP/combined exports. A 390px viewport has no document
  horizontal overflow and the browser reports no JavaScript errors.
- Synthetic regressions cover explicit defensive attribution, missing contest
  history, unknown identities, foul-miss attempt rules, clutch free throws,
  tactic minutes, label escaping and the shared legacy structure.

No application credentials, personal tokens or captured account payloads are
committed. The API requests above are data limitations; the listed visual and
identity fixes do not depend on additional API endpoints.
