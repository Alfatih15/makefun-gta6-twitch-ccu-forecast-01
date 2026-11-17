# Build log — gta6-twitch-ccu-forecast-01

## What was built

`main.py`: a log-space quantile forecaster for a game launch's Twitch
viewer curve. Per hour, a weighted ridge regression over the comparable
launches shipped with the case maps the hour-1 print to that hour's log
viewers, weighted by scale similarity (Gaussian kernel on log hour-1
viewers, bandwidth 2.0). Quantile bands come from leave-one-out residuals
(empirical quantiles, smoothed across hours, shrunk 0.4x toward the
median). GTA VI pre-release history and early-access-contaminated curves
are excluded from the fit. A persistence fallback keeps every case valid
if the fit cannot be built. Python 3.13, standard library only.

## How it was validated

Practice answers (hours 2–24 prints for p00–p03) were read from the same
public source the kit names (SullyGnome hourly averages, one month request
per launch) and cross-checked against each case file's own history tail,
which shares the source up to the checkpoint — all four matched exactly.

Local scoring with the competition's pinball loss on the log scale:

- House persistence baseline (kit starter, reproduced locally): mean
  0.3871 (p00 0.7437, p01 0.2868, p02 0.2146, p03 0.3033) — matches the
  house's published ~0.387.
- This entry: mean 0.1483 (p00 0.1242, p01 0.1551, p02 0.1283,
  p03 0.1857), typical miss 24.5%, 90% coverage 0.924.

Tuning notes: plain per-hour median log-offsets scored 0.4075; unweighted
ridge on log hour-1 scored 0.2225; scale-similarity weighting brought the
typical miss from 30.6% to 24.5%; the raw cross-launch residual spread is
far wider than the median is wrong, so the band is shrunk 0.4x (coverage
0.924 at that setting, close to the nominal 0.90).

## Verification

- Ran on all four practice cases with MAKEFUN_INPUT_DIR /
  MAKEFUN_OUTPUT_DIR: 23 rows x 5 quantiles each, positive, finite,
  non-decreasing per hour, under the 65,536-byte cap.
- Determinism: each case run twice, outputs byte-identical.
- Kit check: `node cli/makefun.mjs check --worktree` from the unpacked kit
  (2026-11-17 ~09:48 UTC): 4 passed (competition_open, snapshot,
  license_osi, entrypoint), 1 failed — transcripts_present, because no
  transcript bundle exists yet (the parent agent bundles and submits);
  all other transcript-gate checks skip without a bundle, so the
  authorship figure is measured at bundle time, not here. 5 checks are
  decided at submission (repo public / owner / created-after-open /
  commit pushed / duplicate snapshot). Authorship hygiene followed
  throughout: all code written with file write/edit tools only, no shell
  writes, starter read but never copied, main.py written then revised in
  a second edit (band monotonicity floor) before the final run.
