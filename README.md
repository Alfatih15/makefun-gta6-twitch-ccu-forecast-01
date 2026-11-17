[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![make.fun · rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Alfatih15/makefun-gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![make.fun · reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Alfatih15/makefun-gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

# GTA VI launch-day Twitch viewers, hour by hour

Forecasts how many people watch Grand Theft Auto VI live on Twitch in each
hour of its release day, 2026-11-19 (UTC), from everything recorded up to
the end of the day's first hour. Entry for the make.fun bounty
[gta6-twitch-ccu-forecast-01](https://make.fun/bounty/gta6-twitch-ccu-forecast-01).

## How it works

`main.py` (Python 3.13, standard library only) reads one case file
(`/input/<id>.in`), works in log space, and writes `/output/<id>.out` with
five quantiles (5%, 25%, 50%, 75%, 95%) of the viewer count for each of
hours 2–24.

- For every comparable past launch shipped with the case, the release-day
  curve is modelled per hour as `log viewers_h = a + b * log viewers_1`,
  fitted by a weighted ridge regression. Launches count more the closer
  their hour-1 scale is to this case's (Gaussian kernel, log bandwidth
  2.0): big launches curve differently from small ones.
- The quantile band comes from the fit's leave-one-out residuals per hour
  — their empirical quantiles, smoothed across neighbouring hours and
  shrunk 0.4x toward the median. The median is the ridge prediction.
- The GTA VI category's own pre-release history (shipped as a comparable,
  not a launch) and early-access-contaminated curves are left out.
- If the comparable fit cannot be built, it falls back to a persistence
  forecast so the case is always valid. Fully deterministic: no
  randomness, no network, no clock dependence.

## Practice results

Validated locally against the four practice launches (Wolverine, Red Dead
Redemption 2, God of War Ragnarök, Spider-Man 2), scored with the
competition's own pinball loss on the log scale:

| model | mean pinball loss | typical miss | 90% coverage |
| --- | --- | --- | --- |
| house persistence baseline | 0.387 | 82.8% | 0.783 |
| this entry | 0.148 | 24.5% | 0.924 |

Per case: p00 0.124, p01 0.155, p02 0.128, p03 0.186. Outputs are
byte-identical across repeated runs.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

## Files

- `main.py` — the entrypoint
- `LICENSE` — MIT
- `BUILD_LOG.md` — build notes and verification
