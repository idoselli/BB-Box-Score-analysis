# API requests for NIKA Multi Match Team Aggregate

Please add or clarify the following in the public match/event API:

1. **Starting lineups and complete lineup changes**, including player positions,
   timestamped substitutions, swaps and removals at each period. This is needed
   for Team FG On/Off, Team Defense On/Off, clutch +/− and the corresponding
   on/off detections. Exact playing seconds by position, or enough lineup data
   to calculate them, would also match the old report's minute precision.
2. **Complete saved primary/help defender and contest attribution on historical
   shots**, where available, plus a coverage indicator when it was not recorded.
   The fields already exist, but older reports can omit them. Without them we
   cannot fully reproduce open/defended splits, defended-shot logs, per-range
   defense or their detections. A missing defender must not imply an open shot.
3. **Document participant roles for every event type**, especially which player
   IDs identify the assister/passer and the player committing a turnover. Explicit
   `assisterId`/`turnoverPlayerId` fields would remove ambiguity. This is needed
   to validate exact clutch assists/turnovers and richer passing attribution.
4. **Individual played effort settings, if intended to be public.** The API
   currently exports only home-minus-away `effortDelta`, which NIKA displays.
   Individual settings cannot be recovered uniquely from that difference.

These are requests for fields/semantics on `/matches/{id}`,
`/matches/{id}/boxscore` and `/matches/{id}/events`, not necessarily new endpoints.

Player-name resolution, bounded scrolling, panel arrangement, tactic groups,
colors, dashboard views, supported detections and exports are application fixes;
they are not requests for new API endpoints. Replay/animation and other NIKA
modes are outside this audit.
