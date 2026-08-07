# BB box score analysis

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
