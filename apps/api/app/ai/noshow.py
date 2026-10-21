"""Appointment no-show risk (phase AI-1/AI-5, docs/AI_ARCHITECTURE.md §6).

An interpretable **L2-regularised logistic regression** fitted by Newton/IRLS in
pure Python, compared on a time-ordered hold-out against the doc's baseline
(the tenant's no-show rate by weekday × lead-time bucket). The baseline is
served unless the model has a lower Brier score.

Features use only operational data that never leaves the server: lead time,
weekday, hour bucket, the patient's own past no-show rate (strictly from
EARLIER appointments) and "first visit". No age, gender, locality, religion,
caste or payment data. Scores are for **reminder prioritisation only** —
never to refuse, delay or deprioritise care.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

MODEL_VERSION = "noshow-logit-1.0"
MIN_APPOINTMENTS = 1000
MIN_NO_SHOWS = 100
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass
class Appt:
    key: str
    patient_key: str
    created_at: datetime
    starts_at: datetime        # clinic-local
    no_show: bool | None       # None = still to come


def lead_bucket(days: float) -> str:
    return "0-1d" if days < 2 else ("2-7d" if days < 8 else "8d+")


def hour_bucket(hour: int) -> str:
    return "morning" if hour < 12 else ("afternoon" if hour < 16 else "evening")


FEATURES = (["log_lead_days"] + [f"weekday_{d}" for d in WEEKDAYS[1:]]
            + ["hour_afternoon", "hour_evening", "prior_no_show_rate", "first_visit"])


def history_features(appts: Sequence[Appt], base_rate: float) -> dict[str, dict]:
    """Per-appointment raw features using only each patient's EARLIER
    appointments (time-respecting — no leakage from the future)."""
    by_patient: dict[str, list[Appt]] = {}
    for a in sorted(appts, key=lambda a: a.starts_at):
        by_patient.setdefault(a.patient_key, []).append(a)
    out: dict[str, dict] = {}
    for rows in by_patient.values():
        seen = shows = 0
        for a in rows:
            lead = max(0.0, (a.starts_at - a.created_at).total_seconds() / 86400)
            out[a.key] = {
                "lead_days": lead, "weekday": a.starts_at.weekday(),
                "hour": a.starts_at.hour, "prior": seen, "prior_no_shows": shows,
                # smoothed toward the tenant base rate (2 pseudo-visits)
                "prior_rate": (shows + 2 * base_rate) / (seen + 2),
            }
            if a.no_show is not None:
                seen += 1
                shows += int(a.no_show)
    return out


def vectorise(f: dict) -> list[float]:
    wd = [1.0 if f["weekday"] == i else 0.0 for i in range(1, 7)]
    hb = hour_bucket(f["hour"])
    return ([math.log1p(f["lead_days"])] + wd
            + [1.0 if hb == "afternoon" else 0.0, 1.0 if hb == "evening" else 0.0,
               f["prior_rate"], 1.0 if f["prior"] == 0 else 0.0])


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        if abs(m[c][c]) < 1e-12:
            continue
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                for k in range(c, n + 1):
                    m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0 for i in range(n)]


@dataclass
class LogitModel:
    means: list[float]
    stds: list[float]
    coef: list[float]          # on standardised features
    intercept: float
    l2: float

    def standardise(self, x: list[float]) -> list[float]:
        return [(v - m) / s for v, m, s in zip(x, self.means, self.stds)]

    def predict(self, x: list[float]) -> float:
        z = self.intercept + sum(c * v for c, v in zip(self.coef, self.standardise(x)))
        return _sigmoid(z)

    def contributions(self, x: list[float]) -> list[tuple[str, float]]:
        xs = self.standardise(x)
        return [(FEATURES[i], self.coef[i] * xs[i]) for i in range(len(FEATURES))]


def fit_logit(xs: list[list[float]], ys: list[int], l2: float = 1.0,
              iters: int = 25) -> LogitModel:
    n, d = len(xs), len(xs[0])
    means = [sum(r[j] for r in xs) / n for j in range(d)]
    stds = []
    for j in range(d):
        var = sum((r[j] - means[j]) ** 2 for r in xs) / n
        stds.append(math.sqrt(var) or 1.0)
    z = [[(r[j] - means[j]) / stds[j] for j in range(d)] + [1.0] for r in xs]
    w = [0.0] * (d + 1)
    for _ in range(iters):
        grad = [0.0] * (d + 1)
        hess = [[0.0] * (d + 1) for _ in range(d + 1)]
        for row, y in zip(z, ys):
            p = _sigmoid(sum(a * b for a, b in zip(w, row)))
            g = p - y
            wgt = p * (1 - p)
            for i in range(d + 1):
                grad[i] += g * row[i]
                ri = wgt * row[i]
                hrow = hess[i]
                for k in range(i, d + 1):
                    hrow[k] += ri * row[k]
        for i in range(d + 1):
            for k in range(i):
                hess[i][k] = hess[k][i]
        for i in range(d):  # no penalty on the intercept
            grad[i] += l2 * w[i]
            hess[i][i] += l2
        step = _solve(hess, grad)
        w = [a - b for a, b in zip(w, step)]
        if max(abs(s) for s in step) < 1e-7:
            break
    return LogitModel(means, stds, w[:d], w[d], l2)


# --- baseline & metrics ------------------------------------------------------------------
@dataclass
class RateBaseline:
    rates: dict[tuple[int, str], float]
    base: float

    def predict(self, f: dict) -> float:
        return self.rates.get((f["weekday"], lead_bucket(f["lead_days"])), self.base)


def fit_baseline(feats: list[dict], ys: list[int]) -> RateBaseline:
    base = sum(ys) / len(ys)
    cnt: dict[tuple[int, str], list[int]] = {}
    for f, y in zip(feats, ys):
        cnt.setdefault((f["weekday"], lead_bucket(f["lead_days"])), []).append(y)
    # 10 pseudo-observations at the overall rate keep sparse cells sane
    return RateBaseline({k: (sum(v) + 10 * base) / (len(v) + 10) for k, v in cnt.items()},
                        base)


def brier(ps: Sequence[float], ys: Sequence[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)


def log_loss(ps: Sequence[float], ys: Sequence[int]) -> float:
    eps = 1e-9
    return -sum(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps))
                for p, y in zip(ps, ys)) / len(ys)


def auc(ps: Sequence[float], ys: Sequence[int]) -> float | None:
    pos = [p for p, y in zip(ps, ys) if y]
    neg = [p for p, y in zip(ps, ys) if not y]
    if not pos or not neg:
        return None
    ranked = sorted([(p, 1) for p in pos] + [(p, 0) for p in neg])
    # average ranks for ties
    ranks, i = [0.0] * len(ranked), 0
    while i < len(ranked):
        j = i
        while j + 1 < len(ranked) and ranked[j + 1][0] == ranked[i][0]:
            j += 1
        for k in range(i, j + 1):
            ranks[k] = (i + j) / 2 + 1
        i = j + 1
    r_pos = sum(r for r, (_, lab) in zip(ranks, ranked) if lab)
    return (r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def ece(ps: Sequence[float], ys: Sequence[int], bins: int = 10) -> float:
    total, err = len(ys), 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, p in enumerate(ps) if lo <= p < hi or (b == bins - 1 and p == 1.0)]
        if idx:
            conf = sum(ps[i] for i in idx) / len(idx)
            acc = sum(ys[i] for i in idx) / len(idx)
            err += len(idx) / total * abs(conf - acc)
    return err


def _metrics(ps, ys) -> dict:
    a = auc(ps, ys)
    return {"brier": round(brier(ps, ys), 4), "log_loss": round(log_loss(ps, ys), 4),
            "auc": None if a is None else round(a, 4), "ece": round(ece(ps, ys), 4)}


# --- explanations ------------------------------------------------------------------------
def explain(f: dict, x: list[float], contribs: list[tuple[str, float]],
            top: int = 3) -> list[dict]:
    """Top contributing factors (coefficient × standardised value). Indicator
    features are only described when they are ACTIVE for this appointment."""
    raw = dict(zip(FEATURES, x))
    text = {
        "log_lead_days": f"Booked {f['lead_days']:.0f} day(s) ahead",
        "prior_no_show_rate": (f"Missed {f['prior_no_shows']} of {f['prior']} earlier "
                               "appointment(s)"),
        "first_visit": "First appointment with this clinic",
        "hour_afternoon": "Afternoon slot", "hour_evening": "Evening slot",
    }
    out = []
    for name, value in sorted(contribs, key=lambda kv: -abs(kv[1])):
        if (name.startswith("weekday_") or name.startswith("hour_")
                or name == "first_visit") and raw[name] == 0:
            continue
        if name == "prior_no_show_rate" and f["prior"] == 0:
            continue
        label = text.get(name) or (f"{name.split('_')[1]} appointment"
                                   if name.startswith("weekday_") else name)
        out.append({"factor": name, "description": label,
                    "effect": "raises risk" if value > 0 else "lowers risk",
                    "weight": round(value, 3)})
        if len(out) >= top:
            break
    return out


@dataclass
class NoShowResult:
    status: str                    # ok | insufficient_data
    served: str = ""               # logistic_regression | baseline_rate
    metrics: dict | None = None
    baseline_metrics: dict | None = None
    base_rate: float = 0.0
    coefficients: dict | None = None
    n_train: int = 0
    n_test: int = 0
    n_appointments: int = 0
    n_no_shows: int = 0
    predictions: list[dict] | None = None


def train_and_score(appts: Sequence[Appt], *, min_appointments: int = MIN_APPOINTMENTS,
                    min_no_shows: int = MIN_NO_SHOWS) -> NoShowResult:
    done = sorted([a for a in appts if a.no_show is not None], key=lambda a: a.starts_at)
    n_ns = sum(1 for a in done if a.no_show)
    if len(done) < min_appointments or n_ns < min_no_shows:
        return NoShowResult("insufficient_data", n_appointments=len(done), n_no_shows=n_ns)
    base_rate = n_ns / len(done)
    feats = history_features(appts, base_rate)
    split = int(len(done) * 0.8)
    train, test = done[:split], done[split:]
    ftr = [feats[a.key] for a in train]
    ytr = [int(a.no_show) for a in train]
    fte = [feats[a.key] for a in test]
    yte = [int(a.no_show) for a in test]
    model = fit_logit([vectorise(f) for f in ftr], ytr)
    base = fit_baseline(ftr, ytr)
    m_model = _metrics([model.predict(vectorise(f)) for f in fte], yte)
    m_base = _metrics([base.predict(f) for f in fte], yte)
    served = "logistic_regression" if m_model["brier"] < m_base["brier"] else "baseline_rate"
    # refit the served model on ALL finished appointments before scoring the future
    fall = [feats[a.key] for a in done]
    yall = [int(a.no_show) for a in done]
    model = fit_logit([vectorise(f) for f in fall], yall)
    base = fit_baseline(fall, yall)
    preds = []
    for a in sorted([a for a in appts if a.no_show is None], key=lambda a: a.starts_at):
        f = feats[a.key]
        x = vectorise(f)
        p = model.predict(x) if served == "logistic_regression" else base.predict(f)
        band = ("high" if p >= max(0.3, 2 * base_rate)
                else "medium" if p >= base_rate else "low")
        factors = (explain(f, x, model.contributions(x)) if served == "logistic_regression"
                   else [{"factor": "weekday_lead_bucket",
                          "description": f"{WEEKDAYS[f['weekday']]} appointment booked "
                                         f"{lead_bucket(f['lead_days'])} ahead "
                                         "(clinic history)", "effect": "base rate",
                          "weight": 0.0}])
        preds.append({"appointment_key": a.key, "risk": round(p, 3), "band": band,
                      "factors": factors})
    return NoShowResult(
        "ok", served=served, metrics=m_model, baseline_metrics=m_base,
        base_rate=round(base_rate, 4),
        coefficients={k: round(v, 4) for k, v in zip(FEATURES, model.coef)},
        n_train=len(train), n_test=len(test), n_appointments=len(done), n_no_shows=n_ns,
        predictions=preds)
