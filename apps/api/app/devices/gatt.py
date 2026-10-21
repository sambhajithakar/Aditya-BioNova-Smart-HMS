"""Parsers for the standard Bluetooth SIG health characteristics (M8.2).

Implemented from the Bluetooth SIG Blood Pressure Service and Pulse Oximeter
Service specifications and the GATT Specification Supplement; no vendor
code. The Android app has a line-for-line equivalent
(apps/mobile/lib/devices/gatt.dart); both are checked against the same
synthetic vectors in packages/contracts/device_vectors.json.

The API parses the RAW bytes itself and never trusts values computed on the
phone. Output is a plain dict so it can be stored as JSON and compared with
the app's result:

    {"kind": "blood_pressure" | "spo2", "characteristic": "2a35" | ...,
     "values": {...integers in mmHg / % / bpm...},
     "exact": {...the device's own decimal strings, original unit...},
     "unit": "mmHg" | "kPa" | "%", "device_time": "YYYY-MM-DDTHH:MM:SS" | None,
     "user_id": int | None, "flags": [sorted status flag names]}

Synthetic vectors prove the two implementations agree with each other and
with this reading of the specification; conformance with real devices is
established only by hardware validation (docs/DEVICE_SUPPORT.md).
"""
from __future__ import annotations

KPA_TO_MMHG = 7.50062


class GattError(ValueError):
    """The payload is malformed or carries no usable measurement."""


# --- SFLOAT (IEEE 11073-20601 16-bit) --------------------------------------------
_SPECIAL = {0x07FF: "NaN", 0x0800: "NRes", 0x07FE: "+INF", 0x0802: "-INF",
            0x0801: "reserved"}


def sfloat(raw: int) -> tuple[int, int]:
    """(mantissa, exponent) of a 16-bit SFLOAT; GattError for special values."""
    if raw in _SPECIAL:
        raise GattError(f"device reported {_SPECIAL[raw]} instead of a value")
    mantissa = raw & 0x0FFF
    if mantissa >= 0x0800:
        mantissa -= 0x1000
    exponent = raw >> 12
    if exponent >= 0x8:
        exponent -= 0x10
    return mantissa, exponent


def as_float(m: int, e: int) -> float:
    # division for negative exponents: 10**k is exact, so both platforms agree
    return m * (10 ** e) if e >= 0 else m / (10 ** -e)


def as_decimal(m: int, e: int) -> str:
    """Exact decimal text of mantissa × 10^exponent (no float rounding)."""
    if e >= 0:
        return str(m * 10 ** e)
    sign = "-" if m < 0 else ""
    digits = str(abs(m)).rjust(-e + 1, "0")
    return f"{sign}{digits[:e]}.{digits[e:]}"


def half_up(v: float) -> int:
    """Round to the nearest integer, halves away from zero (both platforms)."""
    return int(v + 0.5) if v >= 0 else -int(-v + 0.5)


# --- reader -------------------------------------------------------------------------
class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data, self.pos = data, 0

    def take(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise GattError("payload is shorter than its flags announce")
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def u8(self) -> int:
        return self.take(1)[0]

    def u16(self) -> int:
        return int.from_bytes(self.take(2), "little")

    def u24(self) -> int:
        return int.from_bytes(self.take(3), "little")

    def sfloat(self) -> tuple[int, int]:
        return sfloat(self.u16())

    def date_time(self) -> tuple[str | None, bool]:
        """Date Time (0x2A08). Returns (iso, known); a 0 year/month/day means
        the device does not know the date."""
        year = self.u16()
        month, day, hh, mm, ss = self.take(5)
        if year == 0 or month == 0 or day == 0:
            return None, False
        if not (1582 <= year <= 9999 and 1 <= month <= 12 and 1 <= day <= 31
                and hh < 24 and mm < 60 and ss < 60):
            raise GattError("device time stamp is out of range")
        return f"{year:04d}-{month:02d}-{day:02d}T{hh:02d}:{mm:02d}:{ss:02d}", True

    def done(self) -> None:
        if self.pos != len(self.data):
            raise GattError("payload is longer than its flags announce")


def _bits(value: int, names: dict[int, str]) -> list[str]:
    return [name for bit, name in names.items() if value & (1 << bit)]


# --- Blood Pressure Measurement (0x2A35) -----------------------------------------------
_BP_STATUS = {0: "body_movement", 1: "cuff_too_loose", 2: "irregular_pulse",
              5: "improper_position"}
_BP_PULSE_RANGE = {1: "pulse_above_range", 2: "pulse_below_range"}


def parse_blood_pressure(data: bytes) -> dict:
    r = _Reader(data)
    flags = r.u8()
    if flags & 0xE0:
        raise GattError("reserved flag bits are set")
    kpa = bool(flags & 0x01)
    sys_, dia, mean = r.sfloat(), r.sfloat(), r.sfloat()
    device_time, out_flags = None, []
    if flags & 0x02:
        device_time, known = r.date_time()
        if not known:
            out_flags.append("device_clock_not_set")
    pulse = r.sfloat() if flags & 0x04 else None
    user_id = r.u8() if flags & 0x08 else None
    if flags & 0x10:
        status = r.u16()
        out_flags += _bits(status, _BP_STATUS)
        if rng := _BP_PULSE_RANGE.get((status >> 3) & 0x3):
            out_flags.append(rng)
    r.done()

    def mmhg(v: tuple[int, int]) -> int:
        f = as_float(*v)
        return half_up(f * KPA_TO_MMHG if kpa else f)

    unit = "kPa" if kpa else "mmHg"
    values = {"systolic": mmhg(sys_), "diastolic": mmhg(dia), "mean_arterial": mmhg(mean)}
    exact = {"systolic": as_decimal(*sys_), "diastolic": as_decimal(*dia),
             "mean_arterial": as_decimal(*mean)}
    if pulse is not None:
        values["pulse"] = half_up(as_float(*pulse))
        exact["pulse"] = as_decimal(*pulse)
    if user_id == 0xFF:  # "unknown user" in the specification
        user_id = None
    return {"kind": "blood_pressure", "characteristic": "2a35", "values": values,
            "exact": exact, "unit": unit, "device_time": device_time,
            "user_id": user_id, "flags": sorted(set(out_flags))}


# --- Pulse Oximeter (0x2A5E spot-check, 0x2A5F continuous) -------------------------------
_PLX_MEAS = {5: "measurement_ongoing", 6: "early_estimate", 7: "validated",
             8: "fully_qualified", 9: "from_device_storage", 10: "demonstration_data",
             11: "testing_data", 12: "calibration_ongoing", 13: "measurement_unavailable",
             14: "questionable_measurement", 15: "invalid_measurement"}
_PLX_DEVICE = {0: "extended_display_update", 1: "equipment_malfunction",
               2: "signal_processing_irregularity", 3: "inadequate_signal",
               4: "poor_signal", 5: "low_perfusion", 6: "erratic_signal",
               7: "nonpulsatile_signal", 8: "questionable_pulse", 9: "signal_analysis_ongoing",
               10: "sensor_interference", 11: "sensor_unconnected", 12: "unknown_sensor",
               13: "sensor_displaced", 14: "sensor_malfunction", 15: "sensor_disconnected"}


def _plx_tail(r: _Reader, has_meas: bool, has_dev: bool, has_pai: bool,
              exact: dict, flags: list[str]) -> None:
    if has_meas:
        flags += _bits(r.u16(), _PLX_MEAS)
    if has_dev:
        flags += _bits(r.u24(), _PLX_DEVICE)
    if has_pai:
        try:
            exact["perfusion_index"] = as_decimal(*r.sfloat())
        except GattError:
            flags.append("perfusion_index_unavailable")


def _plx_result(char: str, spo2: tuple[int, int], pr: tuple[int, int], exact: dict,
                device_time: str | None, flags: list[str]) -> dict:
    return {"kind": "spo2", "characteristic": char,
            "values": {"spo2": half_up(as_float(*spo2)), "pulse": half_up(as_float(*pr))},
            "exact": {"spo2": as_decimal(*spo2), "pulse": as_decimal(*pr), **exact},
            "unit": "%", "device_time": device_time, "user_id": None,
            "flags": sorted(set(flags))}


def parse_plx_spot_check(data: bytes) -> dict:
    r = _Reader(data)
    flags = r.u8()
    if flags & 0xE0:
        raise GattError("reserved flag bits are set")
    spo2, pr = r.sfloat(), r.sfloat()
    device_time, out_flags, exact = None, [], {}
    if flags & 0x01:
        device_time, known = r.date_time()
        if not known:
            out_flags.append("device_clock_not_set")
    _plx_tail(r, bool(flags & 0x02), bool(flags & 0x04), bool(flags & 0x08), exact, out_flags)
    if flags & 0x10:
        out_flags.append("device_clock_not_set")
    r.done()
    return _plx_result("2a5e", spo2, pr, exact, device_time, out_flags)


def parse_plx_continuous(data: bytes) -> dict:
    """Uses the 'normal' SpO2/PR pair; fast and slow pairs are skipped."""
    r = _Reader(data)
    flags = r.u8()
    if flags & 0xE0:
        raise GattError("reserved flag bits are set")
    spo2, pr = r.sfloat(), r.sfloat()
    for present in (flags & 0x01, flags & 0x02):  # SpO2PR-Fast, SpO2PR-Slow
        if present:
            r.take(4)
    out_flags: list[str] = []
    exact: dict = {}
    _plx_tail(r, bool(flags & 0x04), bool(flags & 0x08), bool(flags & 0x10), exact, out_flags)
    r.done()
    return _plx_result("2a5f", spo2, pr, exact, None, out_flags)


PARSERS = {"2a35": parse_blood_pressure, "2a5e": parse_plx_spot_check,
           "2a5f": parse_plx_continuous}


def parse(characteristic: str, raw_hex: str) -> dict:
    char = characteristic.lower().removeprefix("0x")
    if char not in PARSERS:
        raise GattError(f"unsupported characteristic {characteristic}")
    try:
        data = bytes.fromhex(raw_hex)
    except ValueError as exc:
        raise GattError("raw payload is not hexadecimal") from exc
    if not 1 <= len(data) <= 64:
        raise GattError("raw payload length is not plausible")
    return PARSERS[char](data)


# --- capture policy (shared with the app; enforced again by the API) -------------------
REFUSE_FLAGS = frozenset({
    # not a finished measurement of this patient, right now
    "measurement_ongoing", "measurement_unavailable", "invalid_measurement",
    "from_device_storage", "demonstration_data", "testing_data", "calibration_ongoing",
    "equipment_malfunction", "sensor_unconnected", "sensor_disconnected",
    "sensor_malfunction",
})


def refusal_reason(parsed: dict) -> str | None:
    bad = sorted(set(parsed["flags"]) & REFUSE_FLAGS)
    return f"device marks this reading as: {', '.join(bad)}" if bad else None
