# BB box score analysis

### contact Ido to run it
* credit to Radek for bulding BB Insider, which this tool was built upon.

### local configuration
Set `U21_ANALYZER_PASSWORD` in the runtime environment to unlock the U21 squad analyzer fields.

### minutes analyzers
- `/u21-minutes` — U21 national-team weekly/season minutes overview + player career history
- `/nt-minutes` — senior NT version of the same tool

Optional env vars:
- `BB_PASSWORD` — BB site password fallback when the form field is empty
- `BBAPI_LOGIN` / `BBAPI_CODE` — BBAPI credential fallbacks
- `CURRENT_SEASON` — defaults to `72`
- `U21_MINUTES_MIN_SEASON` — U21 career history floor (defaults to `60`; NT uses the player's BB season dropdown)

Run locally:

```bash
python -m flask --app app run --debug
```
