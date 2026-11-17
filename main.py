"""Hour-by-hour Twitch viewer forecast for a big game launch day.

The program reads one case (schema "makefun/twitch-ccu-case/v1"): the
category's viewer count up to the end of the release day's first hour, that
hour's print included, plus the hourly curves of past big launches shipped
with the case as comparables. It writes, for each of hours 2 to 24, five
quantiles of that hour's viewer count.

Method, in outline. Work in log space, where a launch's audience moves
multiplicatively. For every comparable launch, take its release-day curve
as a function of its own hour-1 print: for each hour h, log viewers_h is
modelled as a + b * log viewers_1. The two coefficients are fitted per
hour by a weighted ridge regression over the comparable launches, with a
Gaussian weight that favours launches whose hour-1 print is close to this
case's (log-scale bandwidth 2.0): big launches curve differently from
small ones, and the shape near the target's own scale is what matters.
The 5% / 25% / 75% / 95% quantiles come from the leave-one-out residuals
of that fit, per hour: their empirical quantiles, smoothed across
neighbouring hours, shrunk 0.4x toward the median (the raw residual
spread is far wider than the median is wrong, so the honest band is
narrower than the raw cross-launch spread). The median itself is the
ridge prediction. Launches that are not real launches (the GTA VI
category's own pre-release history, which is shipped as a comparable)
and early-access-contaminated curves are left out of the fit.

Everything is deterministic: no randomness, no wall-clock or dict-order
dependence, fixed float arithmetic, one fixed output format. Standard
library only, no network.
"""

import json
import math
import os
from datetime import datetime
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]

# Ridge penalty on the slope (the intercept is unpenalised).
RIDGE_LAMBDA = 3.0
# Gaussian kernel bandwidth on log hour-1 viewers: how close in scale a
# comparable launch must be to count fully.
SCALE_BANDWIDTH = 2.0
# How far the residual-quantile band is shrunk toward the median.
SPREAD_SHRINK = 0.4
# Fallback spread (log units per sqrt hour) if the comparable fit fails.
FALLBACK_SIGMA = 0.15


def parse_time(text):
    """An ISO 8601 UTC timestamp as a datetime."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def hour_of(moment, day_start):
    """Whole-hour offset of `moment` from `day_start`, 1-based."""
    return int((moment - day_start).total_seconds() // 3600) + 1


def release_day_curve(comparable):
    """A comparable launch's release-day curve in log space.

    Returns (log hour-1 viewers, {hour: log viewers} for hours 2..24),
    or None when the launch cannot be used: no hour-1 point, a missing
    hour, a non-positive count, the GTA VI category's own pre-release
    history (not a launch), or an early-access-contaminated curve.
    """
    name = comparable.get("name", "")
    if "Grand Theft Auto VI" in name:
        return None
    if "early-access-contaminated" in (comparable.get("unlock") or ""):
        return None
    day_start = parse_time(comparable["day_start"])
    by_hour = {}
    for point in comparable.get("hourly") or []:
        viewers = point.get("viewers")
        if viewers is None or viewers <= 0:
            continue
        by_hour[hour_of(parse_time(point["from"]), day_start)] = viewers
    first = by_hour.get(1)
    if first is None:
        return None
    curve = {}
    for hour in range(2, 25):
        viewers = by_hour.get(hour)
        if viewers is None:
            return None
        curve[hour] = math.log(viewers)
    return math.log(first), curve


def solve_linear(matrix, vector):
    """Solve a small dense linear system by Gaussian elimination."""
    n = len(vector)
    rows = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(rows[r][col]))
        rows[col], rows[pivot] = rows[pivot], rows[col]
        for r in range(col + 1, n):
            factor = rows[r][col] / rows[col][col]
            for c in range(col, n + 1):
                rows[r][c] -= factor * rows[col][c]
    out = [0.0] * n
    for i in range(n - 1, -1, -1):
        out[i] = (rows[i][n] - sum(rows[i][j] * out[j] for j in range(i + 1, n))) / rows[i][i]
    return out


def weighted_ridge(xs, ys, weights, penalty):
    """Fit y ~ a + b*x by weighted ridge (penalty on b only)."""
    s_w = sum(weights)
    s_wx = sum(w * x for w, x in zip(weights, xs))
    s_wxx = sum(w * x * x for w, x in zip(weights, xs))
    s_wy = sum(w * y for w, y in zip(weights, ys))
    s_wxy = sum(w * x * y for w, x, y in zip(weights, xs, ys))
    matrix = [[s_w, s_wx], [s_wx, s_wxx + penalty]]
    vector = [s_wy, s_wxy]
    return solve_linear(matrix, vector)


def empirical_quantile(sorted_values, tau):
    """Linear-interpolation quantile of an ascending list."""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    pos = tau * (n - 1)
    low = int(math.floor(pos))
    high = min(low + 1, n - 1)
    frac = pos - low
    return sorted_values[low] * (1.0 - frac) + sorted_values[high] * frac


def smooth_three(values):
    """Three-point moving average; the ends keep their own value averaged
    with the single neighbour they have."""
    out = []
    for i, value in enumerate(values):
        window = values[max(0, i - 1):min(len(values), i + 2)]
        out.append(sum(window) / len(window))
    return out


def round2(value):
    """Round to 2 decimals, half up, returning an int when whole."""
    scaled = value * 100.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    rounded = whole / 100.0
    return int(rounded) if rounded.is_integer() else rounded


def forecast_hours(case):
    """The 23 forecast rows for one case, hours 2 to 24."""
    known = next(k for k in case["known"] if k["hour"] == 1)
    p1 = max(1, known["viewers"])
    log_p1 = math.log(p1)

    launches = []
    for comparable in case.get("comparables") or []:
        curve = release_day_curve(comparable)
        if curve is not None:
            launches.append(curve)
    if not launches:
        raise ValueError("no usable comparable launches")

    # A launch counts more the closer its hour-1 scale is to this case's.
    weights = [
        math.exp(-((log_first - log_p1) ** 2) / (2.0 * SCALE_BANDWIDTH ** 2))
        for log_first, _ in launches
    ]
    xs = [log_first for log_first, _ in launches]

    medians = {}
    residual_bands = {tau: [] for tau in LEVELS}
    hours = list(range(2, 25))
    for hour in hours:
        ys = [curve[hour] for _, curve in launches]
        intercept, slope = weighted_ridge(xs, ys, weights, RIDGE_LAMBDA)
        medians[hour] = intercept + slope * log_p1
        # Leave-one-out residuals: what the fit misses on a launch it
        # did not see, the honest spread of a fresh launch's curve.
        residuals = []
        for i in range(len(launches)):
            rest_x = [x for j, x in enumerate(xs) if j != i]
            rest_y = [y for j, y in enumerate(ys) if j != i]
            rest_w = [w for j, w in enumerate(weights) if j != i]
            a, b = weighted_ridge(rest_x, rest_y, rest_w, RIDGE_LAMBDA)
            residuals.append(ys[i] - (a + b * xs[i]))
        residuals.sort()
        for tau in LEVELS:
            residual_bands[tau].append(empirical_quantile(residuals, tau))

    smoothed = {tau: smooth_three(residual_bands[tau]) for tau in LEVELS}
    # Keep the band honest on both sides of the median: after smoothing,
    # the residual quantiles of neighbouring levels can touch or cross,
    # which would collapse one side of the band. Enforce a minimum log
    # step of 0.02 between consecutive levels, with the 25% quantile
    # below the median and the 75% above it.
    for i in range(len(hours)):
        lo25 = min(smoothed[0.25][i], -0.02)
        lo05 = min(smoothed[0.05][i], lo25 - 0.02)
        hi75 = max(smoothed[0.75][i], 0.02)
        hi95 = max(smoothed[0.95][i], hi75 + 0.02)
        smoothed[0.05][i] = lo05
        smoothed[0.25][i] = lo25
        smoothed[0.75][i] = hi75
        smoothed[0.95][i] = hi95
    rows = []
    for i, hour in enumerate(hours):
        centre = medians[hour]
        quantiles = []
        for tau in LEVELS:
            if tau == 0.5:
                value = centre
            else:
                value = centre + SPREAD_SHRINK * smoothed[tau][i]
            quantiles.append(value)
        quantiles.sort()
        rows.append({
            "hour": hour,
            "q": [round2(min(1e9, max(1e-9, math.exp(v)))) for v in quantiles],
        })
    return rows


def persistence_hours(p1):
    """Fallback forecast: every hour stays at the hour-1 print, with a
    spread widening like a random walk in log space."""
    rows = []
    for hour in range(2, 25):
        spread = FALLBACK_SIGMA * math.sqrt(hour - 1)
        quantiles = [round2(p1 * math.exp(z * spread)) for z in Z]
        rows.append({"hour": hour, "q": sorted(quantiles)})
    return rows


def forecast_case(case):
    """One case's forecast object, falling back to persistence if the
    comparable fit cannot be built, so the case is always valid."""
    try:
        hours = forecast_hours(case)
    except Exception:
        known = next((k for k in case["known"] if k["hour"] == 1), None)
        p1 = max(1, known["viewers"]) if known else 1
        hours = persistence_hours(p1)
    return {"hours": hours}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        out_path = OUTPUT_DIR / f"{path.stem}.out"
        out_path.write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
