# New-world beta data

This directory is separate from `data/u21-tracker/`, which belongs to the current BuzzerBeater world.

- `u21-tracker/team-map.json` contains verified new-world country and junior-team IDs.
- `u21-tracker/s<season>/w<week>.json` contains locally collected weekly roster snapshots. These files are ignored by Git. Local week 1 DMI is explicitly illustrative at 90% of week 2; it is not observed history.
- `market/players.json` contains locally collected last-known auction records. It is ignored by Git.
- `demo/` contains fully fabricated, labeled sample records for the public beta UI. They are generated deterministically with `python -m beta_v1.demo` and contain no v1 API responses.

The beta collectors require `BB_V1_EXCEPTION_APPROVED=true` in the ignored local `.env` file. The GitHub workflows are manual-only, and the local archive automation is paused. Do not enable publication of real data until the written collection and publication exception has been verified and retained. Tokens are never written here.
