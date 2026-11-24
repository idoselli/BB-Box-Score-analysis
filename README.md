# BB box score analysis

### New BuzzerBeater site

The app opens on the new-site home, with **Match Analysis** as its primary
feature. The old-site tool is at `/legacy/`. To enable the shared password
lock screen, set `NIKA_SITE_PASSWORD` as a Vercel Production Secret and redeploy.
See [site access setup](docs/site-access.md).

For the exact registration, Redis and production settings, follow
[Enable public NIKA sign-in](docs/oauth-production-setup.md).

The production integration remains at `/beta/` to preserve existing bookmarks,
OAuth callbacks and sessions. It now defaults to `https://next-api.buzzerbeater.com/v1`
and `https://play.buzzerbeater.com/oauth/authorize`. Remove stale `BB_V1_API_BASE`
or `BB_V1_AUTHORIZE_URL` overrides pointing at sb1 when deploying.

Pages: `/beta/multi-match` (one or many matches), `/beta/u21-tracker`,
`/beta/national-training`, and `/beta/market`. Old integer IDs and new UUIDs are
separate worlds; old snapshots are never relabeled as new-site history.

Match analysis includes public cursor-paginated events, shot-type and clutch
filters, explicit defender matchups, shooting zones and player shooting/defended
aggregates, actual role minutes, strategies, GDP outcomes, effort difference,
rating sublevels and expected PP100. Player totals, averages, per-36 rates and
estimated TS% are available. JSON and CSV exports retain advanced fields.
Shooting/events failures leave the box-score report available with warnings.
Multi Match Team Aggregate shares the original report renderer, colors, grouping, dashboard views and supported detection rules. Table panels have bounded scrolling and height controls. Opponent and event names resolve across both teams. Play-by-play roles reconstruct defenders, passers and lineups; on/off, timing and clutch figures are enabled after box-score reconciliation. Unresolved games stay labeled.
See [the parity audit and API request list](docs/new-site-parity.md).

For public use, configure the registered OAuth application with
`BB_V1_CLIENT_ID`, `BB_V1_CLIENT_SECRET`, `BB_V1_REDIRECT_URI`,
`BB_V1_REDIS_URL` and `BB_V1_TOKEN_ENCRYPTION_KEY`. Request only the feature's
required scopes. A private localhost preview can use the owner's personal token
with `BB_V1_ALLOW_INMEMORY_TOKEN_LOGIN=true`; sessions then expire after 24 hours
or a restart. Never commit tokens or put them in browser exports.

The production U21 tracker and market archive show labeled demos when published
snapshots are unavailable. The market and beta collectors retain their manual
workflows and use `BB_V1_PERSONAL_TOKEN` and `BB_V1_EXCEPTION_APPROVED`.


### contact Ido to run it
* credit to Radek for bulding BB Insider, which this tool was built upon.

### local development

BuzzerBeater Coach information is available at `/buzzerbeater-coach/`, with
support at `/buzzerbeater-coach/support`, privacy at `/buzzerbeater-coach/privacy`,
and terms at `/buzzerbeater-coach/terms`. Publication preparation is tracked in
`docs/buzzerbeater-coach-publication.md`.

Copy `.env.example` to `.env` and fill in local-only values.

Start the web app:
```powershell
.\run-local.ps1
```

Open:
```text
http://127.0.0.1:5055/
```

Check whether it is responding:
```powershell
.\check-local.ps1
```

Stop the local server:
```powershell
.\stop-local.ps1
```

### local configuration
Set `U21_ANALYZER_PASSWORD` in the runtime environment to unlock the U21 squad analyzer fields.

### minutes analyzers
- `/u21-minutes` — U21 national-team weekly/season minutes overview + player career history
- `/nt-minutes` — senior NT version of the same tool
- `/player-minutes` — enter a player ID and load full career weekly minutes
- `/u21-tracker` — U21 Round Robin DMI/game-shape tracker with position-colored player lines, backed by JSON snapshots

Optional env vars:
- `BB_PASSWORD` — BB site password fallback when the form field is empty
- `BBAPI_LOGIN` / `BBAPI_CODE` — BBAPI credential fallbacks
- `CURRENT_SEASON` — defaults to `73`
- `U21_MINUTES_MIN_SEASON` — U21 career history floor (defaults to `60`; NT uses the player's BB season dropdown)

### U21 tracker weekly snapshots

The GitHub Actions workflow `u21-tracker-weekly.yml` is scheduled for Fridays at
13:30 in `Asia/Jerusalem`. It reads the European confederation's junior squads
and includes Israel, USA, China, Hong Kong and Taiwan. It reads DMI, game shape,
salary, position and potential in one roster request per squad and publishes
completed snapshots under `data/v1/production-u21-tracker/`.

Set the GitHub Actions secret `BB_U21_API_TOKEN` to a production BuzzerBeater
personal token with Public scope. For a local dry run, set the same variable in
the ignored `.env` and run:

```bash
python collect_u21_tracker.py --dry-run --countries IL,US,CN,HK,TW
```

The API supplies season dates. The tracker counts one week per Friday, with
November 27, 2026 as season 74, week 2. Each later season starts its tracker
count on the Friday on or before its API start date. The workflow's manual
dispatch defaults to a dry run and accepts a week override.

Run locally:

```bash
python -m flask --app app run --debug
```
