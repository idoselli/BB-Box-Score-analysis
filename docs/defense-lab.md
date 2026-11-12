# Defense lab — beta experiment

The new-site multi-match report includes a Defense lab card directly after Player
Defense Overview. It uses the existing report payload and makes no additional
API requests. Existing tables/formulas remain available.

## What it adds

- Named-defense and explicit-helper shot outcomes, with made/attempt counts.
- Help-marked versus unmarked outcomes within the selected recorded role.
- Explicit rotation/alteration mentions, with unknown identity kept unknown.
- A comparison using the same shooters and exact shot types elsewhere in the
  selected games, excluding all shots where this player is a named defender or
  helper. Each shooter/type requires at least three reference attempts. The
  baseline is weighted to the matched role attempts; it is not a shot-quality
  model. Matched and reference sample sizes are shown.
- Opponent FG%, eFG%, three-point attempt share and help-marked share with each
  player on and off court. Both sides use the same validated games for that
  player. Coverage is shown as validated games / eligible games played.
- Direct/API versus inferred source coverage and recorded contest-level outcomes.

Result/tactic filters select games; player/minute/attempt filters select rows.
The panel's search, role selector, sample minimum, hide-small-samples toggle and
sortable columns are local. Coverage cards always describe the selected games.
Beta CSV includes the visible player rows. Full report JSON/combined exports
include `defenseLab` with calculations, selected match IDs, metric/role/sample
settings and visible-player IDs.

## Definitions and limits

**Help-marked** means a true API help flag, an explicit helper ID or a recognized
rotation sentence. The flag alone does not establish who helped or who received
help. An opposing second actor is not automatically relabeled as a helper when
the flag is true. The helper identity requires an explicit field/sentence.

**Alteration** counts only the catalog's explicit rotating/altering sentence,
including the legacy equivalent. It is not inferred from a miss, contest, block
or help flag. Without relevant text, it is Not recorded, not zero altered shots.
A rotation-only helper is not also assigned as primary defense in this panel.
Any-role attempts are deduplicated per player even if both roles name them.

**Snapshots** are captured at the physical shot's exact place in event order,
including substitutions at the same displayed clock. They are attached only
once the whole reconstruction validates and are cleared before reanalysis.
A game without a complete valid defending-five snapshot for every opponent FGA
cannot enter this panel's on/off calculation. Rounded-minute disagreements do
not alter sequence-based shot membership once the existing reconciliation passes.

**Denominators**: FG uses all known opponent FGA; eFG and 3PA share use only FGA
with a known two-/three-point shot type. Help share uses shots with known help
flags/explicit helper evidence. Rates with no denominator stay unavailable or
No attempts. Free throws, fouled misses, commentary and duplicate sequence rows
never create opponent FGA. Known-empty samples are distinguished from absent data.

**Interpretation**: FG/eFG on minus off and shooter-comparison differences are in
percentage points, with negative values indicating lower observed shooting.
Help frequency and three-point share have neutral coloring: less is not inherently
better. A sample minimum is a visibility flag, not a confidence interval or
significance test. Teammates, opponents, tactics, role and game state can explain
an observed association. Causal points saved, off-ball deterrence, exact contest
geometry and unrecorded helper identities cannot be recovered from these events.

## Evidence

- Israel U21 season 73, last ten completed games: 896 opponent FGA, 542 named
  defensive involvements, 35 help flags and zero named helpers/contest levels/
  original text. The panel exposes the available help outcomes and labels the
  missing detail. All ten games support validated on/off snapshots.
- Every player's on/off makes and attempts reconcile with the existing validated
  `teamDefOn` / `teamDefOff` splits. Nineteen of twenty players have at least one
  same-shooter/exact-type comparison; small samples remain labeled.
- Python regressions cover exact snapshots, same-clock substitutions and stale
  snapshot removal on a failed reconstruction. JavaScript calculation checks
  cover attribution/deduplication, reference exclusions and weighting, filters,
  partial coverage, absent fields, denominator selection and eFG above 100%.
- Chromium verifies role/metric switches, all four on/off metrics, sorting,
  search, global filters/reset, CSV download, explicit-helper and missing-data
  cases, empty feeds, actual bounded scrolling and a 390px mobile layout.

Run the focused checks with:

```sh
.venv/bin/python -m unittest discover -s tests -q
node tests/defense_lab_checks.cjs
```

If developers want to improve beta coverage, populating the existing
`helpDefenderId`, `primaryDefenderId` and `contestLevel` fields would help.
Rendered text or a template/variation ID would enable explicit alteration
mentions where absent. These are coverage improvements, not prerequisites for
the available role and on/off statistics.
