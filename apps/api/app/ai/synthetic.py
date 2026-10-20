"""Seeded synthetic histories for tests and the AI-1 evaluation
(docs/AI_EVALUATION.md). No real patient data is used anywhere: every series
here is generated from a known mechanism so accuracy claims can be checked.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from .noshow import Appt

# relative OPD load by weekday Mon..Sun (Sunday = half-day clinic)
WEEKLY_PATTERN = (1.25, 1.05, 1.0, 1.0, 1.1, 0.9, 0.35)


def opd_daily_visits(n_days: int, seed: int = 7, base: float = 40.0,
                     trend_per_day: float = 0.03, noise_sd: float = 0.08,
                     pattern=WEEKLY_PATTERN, start_weekday: int = 0) -> list[float]:
    """Weekly-seasonal counts with a gentle trend and multiplicative noise."""
    rng = random.Random(seed)
    out = []
    for t in range(n_days):
        level = base + trend_per_day * t
        mu = level * pattern[(start_weekday + t) % 7]
        out.append(float(max(0, round(mu * math.exp(rng.gauss(0, noise_sd))))))
    return out


def intermittent_demand(n_days: int, seed: int = 11, p_demand: float = 0.35,
                        mean_size: float = 6.0) -> list[float]:
    rng = random.Random(seed)
    return [float(max(1, round(rng.expovariate(1 / mean_size)))) if rng.random() < p_demand
            else 0.0 for _ in range(n_days)]


def admissions(n_days: int, seed: int = 5, per_day: float = 3.0,
               mean_los: float = 4.0, weekend_factor: float = 0.6):
    """(admit_day, discharge_day|None) pairs; discharge None = still admitted."""
    rng = random.Random(seed)
    out = []
    for d in range(n_days):
        lam = per_day * (weekend_factor if d % 7 in (5, 6) else 1.0)
        # Poisson by inversion
        k, p, L = 0, 1.0, math.exp(-lam)
        while True:
            p *= rng.random()
            if p <= L:
                break
            k += 1
        for _ in range(k):
            los = max(1, round(rng.expovariate(1 / mean_los)))
            dis = d + los
            out.append((d, dis if dis < n_days else None))
    return out


def appointments(n: int, seed: int = 3, n_patients: int = 300,
                 start: datetime = datetime(2025, 1, 6, 9, 0),
                 days: int = 360, future: int = 40) -> list[Appt]:
    """Appointments whose no-show probability follows a known logistic
    mechanism: longer lead time, Saturdays, evening slots and a per-patient
    propensity raise it. The last ``future`` appointments are still to come."""
    rng = random.Random(seed)
    propensity = [rng.gauss(0, 0.9) for _ in range(n_patients)]
    rows: list[Appt] = []
    for i in range(n):
        pk = rng.randrange(n_patients)
        day = int(i * days / n)
        hour = rng.choice((9, 10, 11, 12, 14, 15, 17, 18))
        starts = start + timedelta(days=day, hours=hour - 9)
        lead = rng.choice((0, 0, 1, 2, 3, 5, 7, 10, 14, 21, 30))
        created = starts - timedelta(days=lead, hours=rng.randint(1, 6))
        z = (-2.6 + 0.55 * math.log1p(lead) + (0.6 if starts.weekday() == 5 else 0.0)
             + (0.5 if hour >= 16 else 0.0) + propensity[pk])
        p = 1 / (1 + math.exp(-z))
        no_show = None if i >= n - future else (rng.random() < p)
        rows.append(Appt(key=f"a{i}", patient_key=f"p{pk}", created_at=created,
                         starts_at=starts, no_show=no_show))
    return rows
