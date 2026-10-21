"""Pure rules for clinic setup: working-hours validation, appointment slot
generation and check-in token handling. No database access here — the
routers call these and the unit tests exercise them directly."""
from __future__ import annotations

import base64
import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo

# --- working hours -------------------------------------------------------------


@dataclass(frozen=True)
class Session:
    weekday: int
    opens_at: time
    closes_at: time
    break_starts_at: time | None = None
    break_ends_at: time | None = None


def working_hours_errors(sessions: list[Session]) -> list[str]:
    """Human-readable problems with a week of sessions ([] when valid)."""
    errors: list[str] = []
    for s in sessions:
        label = f"day {s.weekday}"
        if not 0 <= s.weekday <= 6:
            errors.append(f"{label}: weekday must be 0 (Monday) to 6 (Sunday)")
            continue
        if s.opens_at >= s.closes_at:
            errors.append(f"{label}: closing time must be after opening time")
            continue
        if (s.break_starts_at is None) != (s.break_ends_at is None):
            errors.append(f"{label}: a break needs both a start and an end")
            continue
        if s.break_starts_at is not None:
            if not (s.opens_at < s.break_starts_at < s.break_ends_at < s.closes_at):
                errors.append(f"{label}: the break must lie inside opening hours")
    if errors:
        return errors
    by_day: dict[int, list[Session]] = {}
    for s in sessions:
        by_day.setdefault(s.weekday, []).append(s)
    for day, items in sorted(by_day.items()):
        items.sort(key=lambda s: s.opens_at)
        for prev, nxt in zip(items, items[1:]):
            if nxt.opens_at < prev.closes_at:
                errors.append(f"day {day}: sessions overlap "
                              f"({prev.opens_at:%H:%M}-{prev.closes_at:%H:%M} and "
                              f"{nxt.opens_at:%H:%M}-{nxt.closes_at:%H:%M})")
    return errors


# --- slots ---------------------------------------------------------------------


def generate_slots(day: date, sessions: list[Session], slot_minutes: int,
                   tz: tzinfo) -> list[tuple[datetime, datetime]]:
    """Bookable [start, end) slots (UTC-aware) on ``day`` in clinic zone ``tz``.

    Slots never straddle the lunch break or the end of a session; a trailing
    remainder shorter than ``slot_minutes`` is dropped."""
    if slot_minutes <= 0:
        raise ValueError("slot_minutes must be positive")
    step = timedelta(minutes=slot_minutes)
    out: list[tuple[datetime, datetime]] = []
    for s in sorted((s for s in sessions if s.weekday == day.weekday()),
                    key=lambda s: s.opens_at):
        windows = [(s.opens_at, s.closes_at)]
        if s.break_starts_at is not None and s.break_ends_at is not None:
            windows = [(s.opens_at, s.break_starts_at), (s.break_ends_at, s.closes_at)]
        for start_t, end_t in windows:
            cur = datetime.combine(day, start_t, tzinfo=tz)
            end = datetime.combine(day, end_t, tzinfo=tz)
            while cur + step <= end:
                out.append((cur.astimezone(timezone.utc), (cur + step).astimezone(timezone.utc)))
                cur += step
    return out


# --- check-in tokens -----------------------------------------------------------

# RFC 4648 base32 alphabet: upper-case letters and 2-7. 16 random bytes ->
# 26 characters (128 bits), which also fits QR "alphanumeric" mode.
_CODE_RE = re.compile(r"^[A-Z2-7]{26}$")


def new_checkin_token() -> tuple[str, str]:
    """(raw_token, sha256_hex). The raw token is random only — it encodes no
    patient, appointment or clinic data — and is shown to staff once."""
    raw = base64.b32encode(secrets.token_bytes(16)).decode("ascii").rstrip("=")
    return raw, hash_checkin_token(raw)


def normalize_checkin_code(code: str) -> str | None:
    """Accept what reception types or a scanner reads: case-insensitive,
    spaces / hyphens ignored, common look-alikes (0/O, 1/I, 8/B) mapped.
    Returns None when it cannot be a check-in code."""
    cleaned = re.sub(r"[\s\-_.]", "", code or "").upper()
    cleaned = cleaned.translate(str.maketrans({"0": "O", "1": "I", "8": "B"}))
    return cleaned if _CODE_RE.match(cleaned) else None


def hash_checkin_token(raw: str) -> str:
    return hashlib.sha256(b"hms-checkin:" + raw.encode("ascii")).hexdigest()
