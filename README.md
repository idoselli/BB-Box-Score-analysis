# BB box score analysis

### new-world beta section

The new BuzzerBeater API integration lives under `/beta/`. The original pages, reports, and weekly U21 job remain on their existing routes and data files. The current home page has one Beta link.

Beta pages: `/beta/u21-tracker`, `/beta/multi-match`, `/beta/national-training`, and `/beta/market`. New-world IDs and snapshots are separate from legacy IDs and `data/u21-tracker/`.

To enable sign-in for other managers, register a confidential application in the new game's **Settings → API & third-party apps**, configure its exact callback URL, and set `BB_V1_CLIENT_ID`, `BB_V1_CLIENT_SECRET`, `BB_V1_REDIRECT_URI`, `BB_V1_REDIS_URL`, and `BB_V1_TOKEN_ENCRYPTION_KEY` on the server. Generate the Fernet key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. OAuth access and rotating refresh tokens stay encrypted in Redis; the browser cookie contains only an opaque session ID. Application review is required before other managers can use it.

Managers may instead paste their own personal API token into the form at `/beta/`. The server validates it with `/me` and stores it in encrypted Redis for 24 hours; the browser receives only an opaque session cookie. A local preview may use `BB_V1_ALLOW_INMEMORY_TOKEN_LOGIN=true` without Redis, in which case token sessions disappear when Flask restarts. Do not enable the in-memory option on a public site.

The public beta tracker and market archive show clearly labeled, fabricated demo data from `data/v1/demo/` until real-data publication is authorized. Regenerate the demo files with `python -m beta_v1.demo`. Their player IDs, names, values, and auction records are synthetic. The demo DMI for week 1 is 10% lower than week 2 to illustrate an individual trend, and the UI labels it as illustrative.

The new-world collectors use a separate personal token in `BB_V1_PERSONAL_TOKEN`. The two beta GitHub Actions are manual-only, and the local beta archive automation is paused. If real-data publication is later authorized, add the token as a GitHub secret and set repository variable `BB_V1_EXCEPTION_APPROVED=true` only after verifying the written exceptions for collection and public publication. Set the same variable on the site to serve real beta snapshots and market archives. The market collector enforces a 72-hour interval when invoked and may miss shorter auctions. Do not put tokens in tracked files.

For local-only collection, keep `BB_V1_PERSONAL_TOKEN` and `BB_V1_EXCEPTION_APPROVED=true` in the ignored `.env` file and run `./run-beta-collector.ps1 u21` or `./run-beta-collector.ps1 market`. Generated snapshots and the market archive are ignored by Git until public publication is explicitly enabled. Local collection does not configure GitHub Actions.

The v1 API does not expose play-by-play, so the beta multi-match report is a box-score report and explicitly labels unavailable event-based analysis. The original detailed report remains available at `/`.

### contact Ido to run it
* credit to Radek for bulding BB Insider, which this tool was built upon.

### local development
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

### U21 tracker weekly scrape
The GitHub Action `.github/workflows/u21-tracker-weekly.yml` refreshes `data/u21-tracker/` every Friday at 10:30 UTC.

Configure these repository secrets in GitHub before enabling it:
- `BBAPI_LOGIN`
- `BBAPI_CODE`
- `BB_PASSWORD`

Optional repository variable:
- `CURRENT_SEASON` - overrides automatic season detection when set

The scraper automatically rolls the scheduled run to season 73 on August 7, 2026, then advances in 98-day season blocks.

The workflow commits only `data/u21-tracker/` JSON files. Credentials are read from GitHub Actions secrets and are not written into the repository.

You can also run the same scraper locally after filling `.env`:

```bash
python scrape_u21_tracker.py
```

Run locally:

```bash
python -m flask --app app run --debug
```
