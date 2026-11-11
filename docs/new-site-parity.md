# NIKA new-site parity audit — 11 November 2026

This change is local source work, not a production deployment. It upgrades the
existing `/beta/` integration to the production API. It does **not** establish
100% parity with the legacy tool. The legacy report engine stays available.

## Sources and verification

- Official guides: https://play.buzzerbeater.com/play/developers/
- Authoritative response schema: https://next-api.buzzerbeater.com/v1/public.json
- Interactive schema: https://next-api.buzzerbeater.com/v1/reference
- The prose migration guide still says play-by-play is unavailable. The live
  OpenAPI schema and a successful live `/events` response contradict that claim.
  The implementation follows the live contract, not the outdated statement.
- Tested an owner-team completed match using the supplied token (Public scope).
  All 530 ordered events loaded through cursors 0, 200 and 400. Its 84 selected-team
  field-goal attempts and 53 points excluding free throws reconcile with the box
  score. Position minutes total 240. No defender IDs were present in this sample.
- Chromium checked real captured report rendering, event/shot filters, JSON
  download, JavaScript errors and a 390px viewport. This is not a live OAuth or
  private-scope browser test. The supplied token cannot test private endpoints.

## Feature comparison

| Existing feature | New-site behavior in this change | Limitation |
| --- | --- | --- |
| Single match | Submit one match UUID; switch the analyzed team | Uses the new report layout |
| Multi-match | Manual UUIDs, club schedule, national schedule; selected team | Maximum 30 matches; quotas still apply |
| Match summary | Score, periods in export, tactics, ratings/sublevels, GDP results, rebounding priorities, effort difference, PP100 | Historical nulls stay null; individual effort is not returned |
| Player summary | Totals, averages, per-36, FG/3PT/FT/eFG and estimated TS | Integer box-score minutes; TS uses FTA × 0.44 |
| Tactic position minutes | Saved role minutes, with per-match offense/defense | Missing splits have an explicit missing-game count; no primary-role guessing |
| Offense shot profile | Team/opponent zones, left/right, assisted/open/contested; player inside/midrange/three | No exact shot coordinates; historical split coverage may be incomplete |
| Player matchup overview | Per-match shooter/primary-defender FG and points | Only explicit defender IDs; historical match tested has none |
| Player defense overview | API per-player defended aggregates plus explicit matchup rows | No assumed player2-to-defender mapping |
| Defended shot log | Public shot events, explicit defender/help/contest fields, search and clutch filters | Missing defender fields remain missing |
| Play-by-play result | Full ordered cursor feed, scores, periods, clocks, players, event types/results | Public facts; no localized legacy commentary reconstruction |
| NBA-style dashboard | Common box-score rates and per-game/per-36 table | Legacy interactive dashboard/on-off panels are not reproduced |
| Filters | Wins/losses, court, exact offense/defense/type; event/player/type search, minimum shot-type attempts, clutch/defender-only | Legacy tactic-group selectors and all cross-table filters are not reproduced |
| Exports | Full JSON; player, match, shot and event CSV; CSV ZIP/combined CSV; browser print/PDF | New-site schema uses UUIDs and explicit coverage fields |
| Animation / court replay | Unavailable | See API data request list below |
| On/off, stint and lineup analysis | Unavailable | Need unambiguous lineup state |
| Detections & suggestions | No unsupported tactical recommendations generated | Legacy rules requiring full on/off/defender coverage are not ported |
| U21 historical tracker | Existing new-world collector and labeled demo/published archive | Needs real longitudinal snapshots; old-world history cannot be transferred |
| National/club training | Existing owner/staff scope checks and recorded training views use production host | Legacy squad analyzer/player-minutes planner is not fully ported |
| Market | Production host and documented parameter casing | Existing collection/publication gates retained |

## API data / endpoint request list for BuzzerBeater

These are requests, **not existing documented endpoints**. Some could be added
as fields on `/matches/{id}` or `/matches/{id}/events` rather than new endpoints.

1. **Starting five with positions for each side, plus complete timestamped
   substitution/position-swap and removal semantics.** Box-score primary roles
   and minutesByPosition do not identify who was on court at a given moment.
   Needed for exact on/off, lineup stints and event-based positional matchups.
   Document player1/player2/detail/teamIndex semantics for substitutions as well.
2. **Shot x/y coordinates and court orientation.** Public events expose a shot
   type, not exact coordinates. Needed for the same point-based shot maps.
   Aggregate zones are already exposed and used.
3. **Replay frames / player and ball movement, or an equivalent public replay
   export.** The events contract explicitly excludes replay movement. Needed for
   equivalent animation. A text-event feed alone cannot reconstruct it.
4. **Complete primary defender, help defender and contest attribution on old
   shots, where historical records exist.** Fields exist in the schema, but the
   tested historical match omits them and has zero recorded open/contested
   attempts. Needed for complete matchup/defense tables and their detections.
   If unrecoverable, an explicit coverage flag would distinguish missing history
   from a genuine zero.
5. **Individual effort values, if public disclosure is intended.** Only
   effortDelta (home minus away) is exported. Equal effort cannot distinguish
   two normal settings from two crunch-time settings. Do not infer them.
6. **Historical public player game logs including club at game time and role
   minutes**, or equivalent bounded player-match discovery. The documented API
   offers current club schedules and owner-only training history, but no public
   career game-log endpoint. Needed for the legacy player analyzer and U21
   minute planning across transfers without scanning other clubs' schedules.
7. **Historical DMI/game-shape/salary/roster snapshots**, if available for export.
   Current player/roster endpoints provide current public figures. Existing
   collector snapshots can build future history but cannot backfill missing
   new-world weeks, much less turn old-world IDs into new ones.

The first four are the main blockers to matching detailed legacy match analysis.
Items 5–7 affect effort display and player/U21 history parity. Missing archive
publication, unported UI panels and export formats are implementation or setup
gaps, not evidence of missing API endpoints.

## Access/setup requirements (not missing endpoints)

- The supplied token grants **Public only**. Club private skills/training require
  **Team**; national private training/prospects require **National** and the
  game's coach/staff permissions; auctions/search require **Market**.
- Some advanced shooting/scouting calls require supporter access. A 403 or a
  quota error leaves the report with a warning rather than fabricated zeros.
- Public OAuth needs the registered application and encrypted Redis session
  configuration on the host. This patch changes defaults but cannot alter an
  already configured environment override or deploy credentials.
- Public tracker/market demos remain clearly labeled. No token, live account
  payload or fabricated historical data is added to the repository.
