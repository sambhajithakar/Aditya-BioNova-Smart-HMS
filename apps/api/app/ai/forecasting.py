"""Statistical forecasting engine (phase AI-1, docs/AI_ARCHITECTURE.md §6).

Pure Python (stdlib only) so it runs on a 4 GB clinic server with no model
download and no provider: this is a **statistical model**, not an AI service,
and the API labels it so. Everything is deterministic for a given history.

Daily series
    * ``seasonal_naive``       — same weekday last week (the baseline)
    * ``seasonal_mean_4w``     — mean of the same weekday over the last 4 weeks
    * ``holt_winters``         — additive Holt-Winters, damped trend, weekly
                                 seasonality; α/β/γ by grid search on in-sample
                                 one-step squared error
    Model choice = lowest MAE on a rolling-origin backtest; the baseline's
    metrics are always reported next to the selected model's.

Intermittent demand (pharmacy)
    * ``moving_average_28d``   — baseline
    * ``ses``                  — simple exponential smoothing of daily units
    * ``sba``                  — Croston with the Syntetos-Boylan correction

Intervals are **empirical**: quantiles of the selected method's backtest
errors (pooled over folds and horizon steps), so their width reflects how
wrong the method actually was on this tenant's own history.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Sequence

SEASON = 7
ENGINE_VERSION = "ai1-stat-1.0"

ForecastFn = Callable[[Sequence[float], int], list[float]]


# --- daily-series methods ------------------------------------------------------------
def seasonal_naive(y: Sequence[float], h: int, m: int = SEASON) -> list[float]:
    if len(y) < m:
        last = y[-1] if y else 0.0
        return [float(last)] * h
    tail = list(y[-m:])
    return [float(tail[i % m]) for i in range(h)]


def seasonal_mean(y: Sequence[float], h: int, m: int = SEASON, weeks: int = 4) -> list[float]:
    k = min(weeks, len(y) // m) or 1
    out = []
    for i in range(h):
        # value for step i shares the weekday of y[-m + (i % m)]
        idx = [len(y) - m + (i % m) - w * m for w in range(k)]
        vals = [y[j] for j in idx if 0 <= j < len(y)]
        out.append(sum(vals) / len(vals) if vals else 0.0)
    return out


@dataclass
class HWFit:
    alpha: float
    beta: float
    gamma: float
    phi: float
    level: float
    trend: float
    season: list[float]
    sse: float
    residuals: list[float] = field(default_factory=list)


def _hw_run(y: Sequence[float], m: int, a: float, b: float, g: float, phi: float,
            keep_residuals: bool = False) -> HWFit:
    first = y[:m]
    second = y[m:2 * m]
    level = sum(first) / m
    trend = (sum(second) / m - level) / m if len(second) == m else 0.0
    season = [v - level for v in first]
    sse = 0.0
    resid: list[float] = []
    for t in range(m, len(y)):
        s = season[t % m]
        pred = level + phi * trend + s
        err = y[t] - pred
        sse += err * err
        if keep_residuals:
            resid.append(err)
        new_level = a * (y[t] - s) + (1 - a) * (level + phi * trend)
        trend = b * (new_level - level) + (1 - b) * phi * trend
        season[t % m] = g * (y[t] - new_level) + (1 - g) * s
        level = new_level
    # rotate seasonal states so index 0 == the step after the last observation
    n = len(y)
    rotated = [season[(n + i) % m] for i in range(m)]
    return HWFit(a, b, g, phi, level, trend, rotated, sse, resid)


_ALPHAS = (0.05, 0.1, 0.2, 0.3, 0.5)
_BETAS = (0.0, 0.02, 0.1)
_GAMMAS = (0.05, 0.15, 0.3)
_PHI = 0.9


def fit_holt_winters(y: Sequence[float], m: int = SEASON) -> HWFit:
    if len(y) < 2 * m:
        raise ValueError("Holt-Winters needs at least two full seasons")
    best: HWFit | None = None
    for a in _ALPHAS:
        for b in _BETAS:
            for g in _GAMMAS:
                fit = _hw_run(y, m, a, b, g, _PHI)
                if best is None or fit.sse < best.sse - 1e-9:
                    best = fit
    assert best is not None
    return _hw_run(y, m, best.alpha, best.beta, best.gamma, best.phi, keep_residuals=True)


def hw_forecast(fit: HWFit, h: int) -> list[float]:
    out = []
    damp = 0.0
    for i in range(h):
        damp += fit.phi ** (i + 1)
        out.append(fit.level + damp * fit.trend + fit.season[i % len(fit.season)])
    return out


def holt_winters(y: Sequence[float], h: int, m: int = SEASON) -> list[float]:
    return hw_forecast(fit_holt_winters(y, m), h)


DAILY_METHODS: dict[str, ForecastFn] = {
    "seasonal_naive": lambda y, h: seasonal_naive(y, h),
    "seasonal_mean_4w": lambda y, h: seasonal_mean(y, h),
    "holt_winters": lambda y, h: holt_winters(y, h),
}
DAILY_BASELINE = "seasonal_naive"
METHOD_LABELS = {
    "seasonal_naive": "Seasonal naive: same weekday last week (baseline)",
    "seasonal_mean_4w": "Average of the same weekday over the last 4 weeks",
    "holt_winters": "Holt-Winters additive, damped trend, weekly seasonality",
    "naive_last": "Last observed value carried forward (baseline)",
    "moving_average_28d": "Average daily use over the last 28 days (baseline)",
    "ses": "Simple exponential smoothing of daily use",
    "sba": "Croston / Syntetos-Boylan approximation for intermittent demand",
}


# --- intermittent-demand methods ---------------------------------------------------------
def moving_average(y: Sequence[float], h: int, window: int = 28) -> list[float]:
    tail = list(y[-window:]) or [0.0]
    rate = sum(tail) / len(tail)
    return [rate] * h


def ses(y: Sequence[float], h: int) -> list[float]:
    best_sse, best_level = None, 0.0
    for a in (0.05, 0.1, 0.2, 0.3):
        level = sum(y[:7]) / max(1, len(y[:7]))
        sse = 0.0
        for v in y[7:]:
            sse += (v - level) ** 2
            level = a * v + (1 - a) * level
        if best_sse is None or sse < best_sse:
            best_sse, best_level = sse, level
    return [max(0.0, best_level)] * h


def sba(y: Sequence[float], h: int, alpha: float = 0.1) -> list[float]:
    nz = [i for i, v in enumerate(y) if v > 0]
    if not nz:
        return [0.0] * h
    z = y[nz[0]]
    p = float(nz[0] + 1)
    last = nz[0]
    for i in nz[1:]:
        z = alpha * y[i] + (1 - alpha) * z
        p = alpha * (i - last) + (1 - alpha) * p
        last = i
    rate = (1 - alpha / 2) * z / p
    return [max(0.0, rate)] * h


DEMAND_METHODS: dict[str, ForecastFn] = {
    "moving_average_28d": lambda y, h: moving_average(y, h),
    "ses": ses,
    "sba": lambda y, h: sba(y, h),
}
DEMAND_BASELINE = "moving_average_28d"


def naive_last(y: Sequence[float], h: int) -> list[float]:
    return [float(y[-1]) if y else 0.0] * h


# --- metrics & backtest ------------------------------------------------------------------
def mae(actual: Sequence[float], pred: Sequence[float]) -> float:
    return sum(abs(a - p) for a, p in zip(actual, pred)) / max(1, len(actual))


def rmse(actual: Sequence[float], pred: Sequence[float]) -> float:
    return math.sqrt(sum((a - p) ** 2 for a, p in zip(actual, pred)) / max(1, len(actual)))


def mape(actual: Sequence[float], pred: Sequence[float]) -> float | None:
    """Mean absolute percentage error over days with a non-zero actual (closed
    days would divide by zero); None when every actual is zero."""
    pairs = [(a, p) for a, p in zip(actual, pred) if a > 0]
    if not pairs:
        return None
    return 100.0 * sum(abs(a - p) / a for a, p in pairs) / len(pairs)


def quantile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


@dataclass
class Backtest:
    method: str
    folds: int
    horizon: int
    mae: float
    rmse: float
    mape: float | None
    mase: float | None
    errors: list[float]  # actual - forecast, pooled

    def metrics(self) -> dict:
        r = lambda v: None if v is None else round(v, 3)  # noqa: E731
        return {"method": self.method, "folds": self.folds, "horizon_days": self.horizon,
                "mae": r(self.mae), "rmse": r(self.rmse), "mape_percent": r(self.mape),
                "mase": r(self.mase)}


def fold_origins(n: int, h: int, min_train: int, max_folds: int = 8,
                 step: int = SEASON) -> list[int]:
    """Training-end indices for a rolling-origin backtest (oldest first)."""
    origins = []
    end = n - h
    while end >= min_train and len(origins) < max_folds:
        origins.append(end)
        end -= step
    return sorted(origins)


def backtest(y: Sequence[float], fn: ForecastFn, name: str, h: int, origins: list[int],
             clip_zero: bool = True, scale: float | None = None) -> Backtest:
    actual_all: list[float] = []
    pred_all: list[float] = []
    for end in origins:
        pred = fn(y[:end], h)
        if clip_zero:
            pred = [max(0.0, p) for p in pred]
        actual_all.extend(y[end:end + h])
        pred_all.extend(pred[:len(y[end:end + h])])
    m = mae(actual_all, pred_all)
    return Backtest(name, len(origins), h, m, rmse(actual_all, pred_all),
                    mape(actual_all, pred_all),
                    (m / scale) if scale else None,
                    [a - p for a, p in zip(actual_all, pred_all)])


def naive_scale(y: Sequence[float], m: int = SEASON) -> float | None:
    """In-sample MAE of the seasonal naive one-step forecast (MASE denominator)."""
    diffs = [abs(y[t] - y[t - m]) for t in range(m, len(y))]
    s = sum(diffs) / len(diffs) if diffs else 0.0
    return s or None


@dataclass
class SeriesForecast:
    method: str
    method_label: str
    candidates: list[dict]
    baseline: dict
    selected: dict
    points: list[float]
    lo80: list[float]
    hi80: list[float]
    lo95: list[float]
    hi95: list[float]
    params: dict


def forecast_series(y: Sequence[float], h: int, methods: dict[str, ForecastFn],
                    baseline: str, min_train: int, max_folds: int = 8) -> SeriesForecast:
    """Backtest every candidate, pick the lowest MAE (ties → the baseline/simpler
    method listed first), refit on the full history and attach empirical
    prediction intervals from the winner's backtest errors."""
    y = [float(v) for v in y]
    origins = fold_origins(len(y), h, min_train, max_folds)
    if not origins:
        raise ValueError("not enough history for a backtest")
    scale = naive_scale(y)
    results = {name: backtest(y, fn, name, h, origins, scale=scale)
               for name, fn in methods.items()}
    order = list(methods)
    best = min(order, key=lambda k: (round(results[k].mae, 6), order.index(k)))
    points = [max(0.0, p) for p in methods[best](y, h)]
    errs = results[best].errors
    q = {k: quantile(errs, k) for k in (0.025, 0.1, 0.9, 0.975)}
    params: dict = {}
    if best == "holt_winters":
        fit = fit_holt_winters(y)
        params = {"alpha": fit.alpha, "beta": fit.beta, "gamma": fit.gamma, "phi": fit.phi,
                  "season_length": SEASON}
    return SeriesForecast(
        method=best, method_label=METHOD_LABELS.get(best, best),
        candidates=[results[k].metrics() for k in order],
        baseline=results[baseline].metrics(), selected=results[best].metrics(),
        points=[round(p, 2) for p in points],
        lo80=[round(max(0.0, p + q[0.1]), 2) for p in points],
        hi80=[round(max(0.0, p + q[0.9]), 2) for p in points],
        lo95=[round(max(0.0, p + q[0.025]), 2) for p in points],
        hi95=[round(max(0.0, p + q[0.975]), 2) for p in points],
        params=params,
    )


# --- census from admissions -------------------------------------------------------------
def daily_census(intervals: Sequence[tuple[int, int | None]], n_days: int) -> list[float]:
    """Occupied beds at the end of each day 0..n_days-1 from (admit_day,
    discharge_day|None) pairs expressed as day offsets."""
    delta = [0] * (n_days + 1)
    for admit, discharge in intervals:
        a = max(0, admit)
        d = n_days if discharge is None else min(n_days, discharge)
        if a < d:
            delta[a] += 1
            delta[d] -= 1
    out, cur = [], 0
    for i in range(n_days):
        cur += delta[i]
        out.append(float(cur))
    return out
