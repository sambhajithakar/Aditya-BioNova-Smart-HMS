"""Forecast services: RLS-scoped queries in the caller's transaction → the
pure-Python engines in ``forecasting`` / ``noshow`` → API dicts.

Every response carries ``inference: "statistical"`` and a "statistical model"
label, the method, training window, backtest metrics of the selected model
AND of the baseline, prediction intervals, and ``insufficient_data`` (with
what is required) when history is too short. Each computation is recorded in
``ai_model_runs`` (model versioning).
"""
from __future__ import annotations

import math
import statistics
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import Principal
from ..models import Admission, Appointment, Bed, Branch, DrugCatalog, InventoryItem, \
    InventoryMovement, OpdQueueEntry, StockBatch, StockMovement, Ward
from ..timeutil import clinic_today, clinic_tz
from . import forecasting as F
from . import noshow as N
from .common import record_model_run

LABEL = "statistical model"
MIN_OPD_DAYS = 56          # 8 weeks for weekly seasonality (§6.1)
MIN_BED_DAYS = 180         # ~6 months of admissions (§6.1)
MIN_DEMAND_DAYS = 84       # 12 weeks …
MIN_DEMAND_ACTIVE_WEEKS = 6  # … with ≥ 6 weeks of non-zero use (§6.1)
MAX_HISTORY_DAYS = 365


def _local_date(ts: datetime) -> date:
    return ts.astimezone(clinic_tz()).date()


def _insufficient(kind: str, required: str, available: str, earliest: date | None,
                  **extra) -> dict:
    return {"status": "insufficient_data", "kind": kind, "label": LABEL,
            "inference": "statistical", "required": required, "available": available,
            "earliest_available_on": earliest.isoformat() if earliest else None, **extra}


def _series_payload(kind: str, fc: F.SeriesForecast, start: date, end: date,
                    y: list[float], h: int, run_id: uuid.UUID, **extra) -> dict:
    days = [(end + timedelta(days=i + 1)) for i in range(h)]
    hist_from = max(0, len(y) - 56)
    return {
        "status": "ok", "kind": kind, "label": LABEL, "inference": "statistical",
        "engine_version": F.ENGINE_VERSION, "model_run_id": str(run_id),
        "method": fc.method, "method_label": fc.method_label, "params": fc.params,
        "training_window": {"start": start.isoformat(), "end": end.isoformat(),
                            "days": len(y)},
        "backtest": {"selected": fc.selected, "baseline": fc.baseline,
                     "candidates": fc.candidates,
                     "beats_baseline": fc.selected["mae"] < fc.baseline["mae"]},
        "interval_method": "empirical quantiles of the selected method's rolling-origin "
                           "backtest errors (80% and 95%)",
        "history": [{"date": (start + timedelta(days=i)).isoformat(), "value": y[i]}
                    for i in range(hist_from, len(y))],
        "forecast": [{"date": d.isoformat(), "point": p, "lo80": a, "hi80": b,
                      "lo95": c, "hi95": e}
                     for d, p, a, b, c, e in zip(days, fc.points, fc.lo80, fc.hi80, fc.lo95,
                                                 fc.hi95)],
        **extra,
    }


def _run(db, principal, kind, scope, fc: F.SeriesForecast | None, status_, start, end, n,
         version=F.ENGINE_VERSION):
    return record_model_run(
        db, principal, kind=kind, scope=scope, engine_version=version,
        method=fc.method if fc else "", status_=status_, params=fc.params if fc else {},
        metrics=fc.selected if fc else {}, baseline_metrics=fc.baseline if fc else {},
        data_start=start, data_end=end, n_obs=n)


# --- OPD demand ----------------------------------------------------------------------------
def opd_demand(db: Session, principal: Principal, branch_id: uuid.UUID | None,
               horizon: int = 14) -> list[dict]:
    org = principal.organization_id
    today = clinic_today()
    end = today - timedelta(days=1)                    # last COMPLETE day
    since = today - timedelta(days=MAX_HISTORY_DAYS)
    bconds = [Branch.organization_id == org]
    bconds.append(Branch.id == branch_id if branch_id else Branch.status == "active")
    branches = db.execute(select(Branch.id, Branch.name).where(*bconds)
                          .order_by(Branch.name)).all()
    rows = db.execute(
        select(OpdQueueEntry.branch_id, OpdQueueEntry.service_date, func.count())
        .where(OpdQueueEntry.organization_id == org, OpdQueueEntry.status != "cancelled",
               OpdQueueEntry.service_date >= since, OpdQueueEntry.service_date <= end)
        .group_by(OpdQueueEntry.branch_id, OpdQueueEntry.service_date)).all()
    counts: dict[uuid.UUID, dict[date, int]] = defaultdict(dict)
    for b, d, c in rows:
        counts[b][d] = c
    out = []
    for bid, bname in branches:
        per_day = counts.get(bid, {})
        scope = str(bid)
        if not per_day:
            _run(db, principal, "opd_demand", scope, None, "insufficient_data", None, None, 0)
            out.append(_insufficient("opd_demand", f"{MIN_OPD_DAYS} days of OPD history",
                                     "0 days", None, branch_id=str(bid), branch_name=bname))
            continue
        start = min(per_day)
        y = [float(per_day.get(start + timedelta(days=i), 0))
             for i in range((end - start).days + 1)]
        if len(y) < MIN_OPD_DAYS:
            _run(db, principal, "opd_demand", scope, None, "insufficient_data", start, end,
                 len(y))
            out.append(_insufficient(
                "opd_demand", f"{MIN_OPD_DAYS} days of OPD history", f"{len(y)} days",
                start + timedelta(days=MIN_OPD_DAYS), branch_id=str(bid), branch_name=bname))
            continue
        fc = F.forecast_series(y, horizon, F.DAILY_METHODS, F.DAILY_BASELINE, min_train=28)
        run = _run(db, principal, "opd_demand", scope, fc, "ok", start, end, len(y))
        out.append(_series_payload("opd_demand", fc, start, end, y, horizon, run.id,
                                   branch_id=str(bid), branch_name=bname,
                                   unit="OPD visits per day"))
    return out


# --- bed occupancy -------------------------------------------------------------------------
def bed_occupancy(db: Session, principal: Principal, branch_id: uuid.UUID | None,
                  horizon: int = 14) -> dict:
    org = principal.organization_id
    today = clinic_today()
    end = today - timedelta(days=1)
    conds = [Admission.organization_id == org]
    if branch_id:
        conds.append(Admission.branch_id == branch_id)
    rows = db.execute(select(Admission.admitted_at, Admission.discharged_at)
                      .where(*conds)).all()
    bed_conds = [Bed.organization_id == org, Bed.status != "maintenance"]
    bed_q = select(func.count()).select_from(Bed)
    if branch_id:
        bed_q = bed_q.join(Ward, Ward.id == Bed.ward_id).where(Ward.branch_id == branch_id)
    beds_total = db.scalar(bed_q.where(*bed_conds)) or 0
    scope = str(branch_id) if branch_id else "all"
    if not rows:
        _run(db, principal, "bed_occupancy", scope, None, "insufficient_data", None, None, 0)
        return _insufficient("bed_occupancy", f"{MIN_BED_DAYS} days of admissions history",
                             "0 days", None, beds_total=beds_total)
    start = max(min(_local_date(a) for a, _ in rows), today - timedelta(days=MAX_HISTORY_DAYS))
    n_days = (end - start).days + 1
    intervals = [((_local_date(a) - start).days,
                  None if d is None else (_local_date(d) - start).days) for a, d in rows]
    y = F.daily_census(intervals, max(0, n_days))
    if n_days < MIN_BED_DAYS:
        _run(db, principal, "bed_occupancy", scope, None, "insufficient_data", start, end,
             max(0, n_days))
        return _insufficient("bed_occupancy", f"{MIN_BED_DAYS} days of admissions history",
                             f"{max(0, n_days)} days", start + timedelta(days=MIN_BED_DAYS),
                             beds_total=beds_total)
    methods = {"naive_last": F.naive_last, **F.DAILY_METHODS}
    fc = F.forecast_series(y, horizon, methods, "naive_last", min_train=56)
    run = _run(db, principal, "bed_occupancy", scope, fc, "ok", start, end, n_days)
    current = sum(1 for _, d in rows if d is None)
    pay = _series_payload("bed_occupancy", fc, start, end, y, horizon, run.id,
                          unit="occupied beds (end of day)", beds_total=beds_total,
                          current_census=current)
    if beds_total:
        for f in pay["forecast"]:
            f["occupancy_percent"] = round(100 * f["point"] / beds_total, 1)
    return pay


# --- consumption-based demand (pharmacy drugs, general inventory) --------------------------
def demand_forecast(series: list[float], on_hand_batches: list[tuple[date | None, int]],
                    today: date, lead_time_days: int, review_days: int,
                    first_day: date) -> dict:
    """Shared maths for drug/item demand. ``on_hand_batches`` = (expiry, qty)."""
    y = series
    active_weeks = sum(1 for w in range(0, len(y), 7) if sum(y[w:w + 7]) > 0)
    on_hand = sum(q for _, q in on_hand_batches)
    if len(y) < MIN_DEMAND_DAYS or active_weeks < MIN_DEMAND_ACTIVE_WEEKS:
        return _insufficient(
            "pharmacy_demand",
            f"{MIN_DEMAND_DAYS} days of stock history with ≥ {MIN_DEMAND_ACTIVE_WEEKS} weeks "
            "of use", f"{len(y)} days, {active_weeks} active weeks",
            first_day + timedelta(days=MIN_DEMAND_DAYS), on_hand=on_hand)
    window = y[-MAX_HISTORY_DAYS:]
    fc = F.forecast_series(window, 14, F.DEMAND_METHODS, F.DEMAND_BASELINE, min_train=28,
                           max_folds=4)
    rate = sum(fc.points) / len(fc.points)
    sd = statistics.pstdev(window[-56:]) if len(window) > 1 else 0.0
    # FEFO projection: what will expire before it can be used at this rate
    usable, consumed, expiring = 0, 0.0, 0
    for expiry, qty in sorted(on_hand_batches, key=lambda b: b[0] or date.max):
        days_left = (expiry - today).days if expiry else 10 ** 6
        capacity = max(0.0, rate * days_left - consumed)
        use = min(qty, int(capacity))
        usable += use
        consumed += use
        expiring += qty - use
    cover_days = round(usable / rate, 1) if rate > 0 else None
    horizon = lead_time_days + review_days
    safety = 1.65 * sd * math.sqrt(horizon)
    reorder_point = rate * lead_time_days + safety
    target = rate * horizon + safety
    suggested = max(0, math.ceil(target - usable)) if usable <= reorder_point else 0
    lo14 = sum(fc.lo80)
    hi14 = sum(fc.hi80)
    return {
        "status": "ok", "kind": "pharmacy_demand", "label": LABEL,
        "inference": "statistical", "method": fc.method, "method_label": fc.method_label,
        "backtest": {"selected": fc.selected, "baseline": fc.baseline,
                     "candidates": fc.candidates,
                     "beats_baseline": fc.selected["mae"] < fc.baseline["mae"]},
        "training_window": {"start": (today - timedelta(days=len(window))).isoformat(),
                            "end": (today - timedelta(days=1)).isoformat(),
                            "days": len(window)},
        "avg_daily_use": round(rate, 2),
        "next_14_days": {"point": round(rate * 14, 1), "lo80": round(lo14, 1),
                         "hi80": round(hi14, 1)},
        "on_hand": on_hand, "usable_on_hand": usable,
        "projected_expiring_unused": expiring, "days_of_cover": cover_days,
        "reorder_point": round(reorder_point, 1), "suggested_order_qty": suggested,
        "policy": {"lead_time_days": lead_time_days, "review_days": review_days,
                   "service_level": "≈95% (z = 1.65)"},
    }


def _daily(rows: list[tuple[datetime, int]], first: date, end: date) -> list[float]:
    per: dict[date, float] = defaultdict(float)
    for ts, q in rows:
        per[_local_date(ts)] += q
    return [per.get(first + timedelta(days=i), 0.0) for i in range((end - first).days + 1)]


def pharmacy_demand(db: Session, principal: Principal, branch_id: uuid.UUID | None,
                    lead_time_days: int = 7, review_days: int = 14,
                    drug_id: uuid.UUID | None = None) -> list[dict]:
    org = principal.organization_id
    today = clinic_today()
    end = today - timedelta(days=1)
    since = datetime.now(timezone.utc) - timedelta(days=MAX_HISTORY_DAYS + 1)
    conds = [StockBatch.organization_id == org]
    if branch_id:
        conds.append(StockBatch.branch_id == branch_id)
    if drug_id:
        conds.append(StockBatch.drug_id == drug_id)
    batches = db.execute(select(StockBatch.id, StockBatch.branch_id, StockBatch.drug_id,
                                StockBatch.expiry_date, StockBatch.quantity_on_hand,
                                StockBatch.status, StockBatch.received_at)
                         .where(*conds)).all()
    if not batches:
        return []
    batch_key = {b.id: (b.branch_id, b.drug_id) for b in batches}
    moves = db.execute(select(StockMovement.batch_id, StockMovement.created_at,
                              StockMovement.quantity, StockMovement.movement_type,
                              StockMovement.direction)
                       .where(StockMovement.organization_id == org,
                              StockMovement.batch_id.in_(list(batch_key)),
                              StockMovement.created_at >= since)).all()
    use: dict[tuple, list] = defaultdict(list)
    for m in moves:
        if m.movement_type == "dispense" and m.direction == "out":
            use[batch_key[m.batch_id]].append((m.created_at, m.quantity))
        elif m.movement_type == "return" and m.direction == "in":
            use[batch_key[m.batch_id]].append((m.created_at, -m.quantity))
    groups: dict[tuple, list] = defaultdict(list)
    first_seen: dict[tuple, date] = {}
    for b in batches:
        key = (b.branch_id, b.drug_id)
        groups[key].append(b)
        d = _local_date(b.received_at)
        first_seen[key] = min(first_seen.get(key, d), d)
    names = dict(db.execute(select(DrugCatalog.id, DrugCatalog.generic_name).where(
        DrugCatalog.id.in_({k[1] for k in groups}))).all())
    out = []
    for key, bs in sorted(groups.items(), key=lambda kv: names.get(kv[0][1], "")):
        first = max(first_seen[key], today - timedelta(days=MAX_HISTORY_DAYS))
        series = _daily(use.get(key, []), first, end) if first <= end else []
        series = [max(0.0, v) for v in series]
        on_hand = [(b.expiry_date, b.quantity_on_hand) for b in bs
                   if b.status == "active" and b.quantity_on_hand > 0
                   and b.expiry_date >= today]
        res = demand_forecast(series, on_hand, today, lead_time_days, review_days, first)
        record_model_run(
            db, principal, kind="pharmacy_demand", scope=f"{key[0]}:{key[1]}",
            engine_version=F.ENGINE_VERSION, method=res.get("method", ""),
            status_=res["status"], params=res.get("policy", {}),
            metrics=res.get("backtest", {}).get("selected", {}),
            baseline_metrics=res.get("backtest", {}).get("baseline", {}),
            data_start=first, data_end=end, n_obs=len(series))
        res.update({"item_type": "drug", "item_id": str(key[1]), "branch_id": str(key[0]),
                    "name": names.get(key[1], "?")})
        out.append(res)
    return out


def inventory_demand(db: Session, principal: Principal, branch_id: uuid.UUID | None,
                     lead_time_days: int = 7, review_days: int = 14) -> list[dict]:
    """Same maths for general (non-pharmacy) supplies from ``issue`` movements."""
    org = principal.organization_id
    today = clinic_today()
    end = today - timedelta(days=1)
    conds = [InventoryItem.organization_id == org, InventoryItem.status == "active"]
    if branch_id:
        conds.append(InventoryItem.branch_id == branch_id)
    items = db.execute(select(InventoryItem).where(*conds)).scalars().all()
    if not items:
        return []
    since = datetime.now(timezone.utc) - timedelta(days=MAX_HISTORY_DAYS + 1)
    moves = db.execute(select(InventoryMovement.item_id, InventoryMovement.created_at,
                              InventoryMovement.quantity, InventoryMovement.movement_type,
                              InventoryMovement.direction)
                       .where(InventoryMovement.organization_id == org,
                              InventoryMovement.item_id.in_([i.id for i in items]),
                              InventoryMovement.created_at >= since)).all()
    use: dict[uuid.UUID, list] = defaultdict(list)
    for m in moves:
        if m.movement_type == "issue" and m.direction == "out":
            use[m.item_id].append((m.created_at, m.quantity))
    out = []
    for it in items:
        first = max(_local_date(it.created_at), today - timedelta(days=MAX_HISTORY_DAYS))
        series = _daily(use.get(it.id, []), first, end) if first <= end else []
        res = demand_forecast(series, [(None, it.quantity_on_hand)], today, lead_time_days,
                              review_days, first)
        res["kind"] = "inventory_demand"
        res.update({"item_type": "inventory", "item_id": str(it.id),
                    "branch_id": str(it.branch_id), "name": it.name,
                    "reorder_level": it.reorder_level, "unit": it.unit})
        out.append(res)
    return out


# --- no-show risk --------------------------------------------------------------------------
def no_show(db: Session, principal: Principal, branch_id: uuid.UUID | None,
            days_ahead: int = 7) -> dict:
    org = principal.organization_id
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=days_ahead)
    conds = [Appointment.organization_id == org, Appointment.status != "cancelled",
             Appointment.starts_at >= now - timedelta(days=730), Appointment.starts_at < horizon]
    if branch_id:
        conds.append(Appointment.branch_id == branch_id)
    rows = db.execute(select(Appointment.id, Appointment.patient_id, Appointment.created_at,
                             Appointment.starts_at, Appointment.status).where(*conds)).all()
    tz = clinic_tz()
    appts = []
    for r in rows:
        if r.status in ("no_show",):
            outcome = True
        elif r.status in ("completed", "checked_in"):
            outcome = False
        elif r.status == "scheduled" and r.starts_at >= now:
            outcome = None
        else:
            continue  # past but never closed: unknown outcome, excluded
        appts.append(N.Appt(key=str(r.id), patient_key=str(r.patient_id),
                            created_at=r.created_at.astimezone(tz).replace(tzinfo=None),
                            starts_at=r.starts_at.astimezone(tz).replace(tzinfo=None),
                            no_show=outcome))
    res = N.train_and_score(appts)
    scope = str(branch_id) if branch_id else "all"
    finished = [a for a in appts if a.no_show is not None]
    start = min((a.starts_at.date() for a in finished), default=None)
    end_d = max((a.starts_at.date() for a in finished), default=None)
    run = record_model_run(
        db, principal, kind="no_show", scope=scope, engine_version=N.MODEL_VERSION,
        method=res.served, status_=res.status,
        params={"coefficients": res.coefficients or {}, "l2": 1.0,
                "features": list(N.FEATURES)},
        metrics=res.metrics or {}, baseline_metrics=res.baseline_metrics or {},
        data_start=start, data_end=end_d, n_obs=res.n_appointments)
    common = {"kind": "no_show", "label": LABEL, "inference": "statistical",
              "intended_use": "Reminder prioritisation only. Never used to refuse, delay or "
                              "deprioritise care.",
              "excluded_features": ["age", "gender", "locality", "religion", "caste",
                                    "payment history"]}
    if res.status != "ok":
        return {**_insufficient(
            "no_show", f"{N.MIN_APPOINTMENTS} finished appointments including "
                       f"{N.MIN_NO_SHOWS} no-shows",
            f"{res.n_appointments} finished, {res.n_no_shows} no-shows", None), **common}
    starts = {str(r.id): r for r in rows}
    preds = []
    for p in res.predictions or []:
        r = starts[p["appointment_key"]]
        preds.append({"appointment_id": p["appointment_key"],
                      "starts_at": r.starts_at.isoformat(), "risk": p["risk"],
                      "band": p["band"], "factors": p["factors"]})
    preds.sort(key=lambda p: -p["risk"])
    return {**common, "status": "ok", "model_run_id": str(run.id),
            "engine_version": N.MODEL_VERSION, "method": res.served,
            "method_label": ("L2-regularised logistic regression" if res.served ==
                             "logistic_regression" else
                             "Clinic no-show rate by weekday × booking lead time (baseline)"),
            "training_window": {"start": start.isoformat() if start else None,
                                "end": end_d.isoformat() if end_d else None,
                                "appointments": res.n_appointments,
                                "no_shows": res.n_no_shows},
            "backtest": {"split": "time-ordered: first 80% train, last 20% test",
                         "n_train": res.n_train, "n_test": res.n_test,
                         "selected": res.metrics if res.served == "logistic_regression"
                         else res.baseline_metrics,
                         "model": res.metrics, "baseline": res.baseline_metrics},
            "base_rate": res.base_rate, "coefficients": res.coefficients,
            "predictions": preds}
