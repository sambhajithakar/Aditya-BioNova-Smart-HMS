"""Scheduler entry point for appointment / follow-up reminders.

    python -m app.comms.reminder_job --org <uuid> [--org <uuid> ...]
    python -m app.comms.reminder_job --all-active

Schedule it with what the host already has — no new infrastructure, e.g. a
crontab line ``7 * * * * cd /srv/hms/apps/api && python -m
app.comms.reminder_job --all-active`` or a Kubernetes CronJob with the same
command. Runs are idempotent (dedupe per appointment + template + start
time) and respect each clinic's quiet hours, consent and quotas, so running
hourly — or twice by accident — never double-sends.

Each clinic is processed in its own transaction as the NON-owner ``hms_app``
role with that clinic's RLS context, exactly like an API request.
``--all-active`` lists active organisation ids through the migration
(owner) connection — ids only, no tenant data is read that way.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid

from sqlalchemy import create_engine, text

from ..config import get_settings
from ..db import SessionLocal, set_request_context
from .engine import run_reminders


def active_org_ids() -> list[uuid.UUID]:
    eng = create_engine(get_settings().migration_database_url, future=True)
    try:
        with eng.connect() as conn:
            return [r[0] for r in conn.execute(text(
                "SELECT o.id FROM organizations o JOIN subscriptions s "
                "ON s.organization_id = o.id WHERE o.status = 'active' "
                "AND s.status IN ('trialing','active','past_due')")).all()]
    finally:
        eng.dispose()


def run_for_org(org_id: uuid.UUID) -> dict:
    db = SessionLocal()
    try:
        set_request_context(db, org_id=str(org_id))
        summary = run_reminders(db, org_id, trigger="scheduler")
        db.commit()
        return summary
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--org", action="append", type=uuid.UUID, default=[])
    ap.add_argument("--all-active", action="store_true")
    args = ap.parse_args(argv)
    orgs = list(args.org) + (active_org_ids() if args.all_active else [])
    if not orgs:
        ap.error("pass --org <uuid> or --all-active")
    failed = 0
    for org_id in dict.fromkeys(orgs):
        try:
            s = run_for_org(org_id)
            print(json.dumps({"organization_id": str(org_id), "sent": s["sent"],
                              "by_status": s["by_status"], "quiet_hours": s["quiet_hours"]}))
        except Exception as exc:  # keep going for the other clinics
            failed += 1
            print(json.dumps({"organization_id": str(org_id), "error": type(exc).__name__}),
                  file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
