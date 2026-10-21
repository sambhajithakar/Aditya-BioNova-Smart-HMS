"""Clinic-local calendar helpers (M7.0).

Timestamps are stored in UTC, but "today" — the OPD service day, daily
report windows — is a CLINIC calendar day. For an Indian clinic the UTC
date is wrong between 00:00 and 05:30 IST, so every "today"/day-window
computation goes through this module.

The zone comes from ``CLINIC_TIMEZONE`` (IANA name, default
``Asia/Kolkata``). It is read from the environment here rather than from
``config.Settings`` so this module stays self-contained; an invalid name
falls back to the default instead of failing requests.
"""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_CLINIC_TIMEZONE = "Asia/Kolkata"


# IST has no DST: a fixed offset is exact if the system tz database is
# missing (slim container images without tzdata)
_IST_FIXED = timezone(timedelta(hours=5, minutes=30), "IST")


def clinic_tz() -> tzinfo:
    name = os.environ.get("CLINIC_TIMEZONE", DEFAULT_CLINIC_TIMEZONE)
    for candidate in (name, DEFAULT_CLINIC_TIMEZONE):
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return _IST_FIXED


def clinic_today(now: datetime | None = None) -> date:
    """The clinic's calendar date at ``now`` (default: current time)."""
    moment = now or datetime.now(timezone.utc)
    return moment.astimezone(clinic_tz()).date()


def clinic_day_bounds(day: date) -> tuple[datetime, datetime]:
    """[start, end) of a clinic calendar day as UTC-aware datetimes."""
    tz = clinic_tz()
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)
