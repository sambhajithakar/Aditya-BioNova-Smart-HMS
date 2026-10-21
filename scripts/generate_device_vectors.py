#!/usr/bin/env python3
"""Write packages/contracts/device_vectors.json (M8.2).

SYNTHETIC test vectors for the Blood Pressure (0x2A35) and Pulse Oximeter
(0x2A5E / 0x2A5F) characteristics. Each payload is ENCODED here, field by
field, from the layout in the Bluetooth SIG specifications; the expected
result is written out by hand next to it. The API's Python parser and the
Android app's Dart parser must both reproduce every expectation.

These vectors are not captured from real devices.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "packages" / "contracts" / "device_vectors.json"


def sf(mantissa: int, exponent: int = 0) -> bytes:
    return struct.pack("<H", ((exponent & 0xF) << 12) | (mantissa & 0x0FFF))


def raw16(v: int) -> bytes:
    return struct.pack("<H", v)


def dt(y: int, mo: int, d: int, h: int, mi: int, s: int) -> bytes:
    return struct.pack("<HBBBBB", y, mo, d, h, mi, s)


def u16(v: int) -> bytes:
    return struct.pack("<H", v)


def u24(v: int) -> bytes:
    return v.to_bytes(3, "little")


def ok(name, char, payload, kind, values, exact, unit, flags=(), device_time=None,
       user_id=None):
    return {"name": name, "characteristic": char, "hex": payload.hex(),
            "expect": {"kind": kind, "characteristic": char, "values": values,
                       "exact": exact, "unit": unit, "device_time": device_time,
                       "user_id": user_id, "flags": sorted(flags)}}


def bad(name, char, payload, error_contains):
    return {"name": name, "characteristic": char, "hex": payload.hex(),
            "error": error_contains}


BP, SPOT, CONT = "2a35", "2a5e", "2a5f"
V = []

# --- blood pressure ---------------------------------------------------------------------
V.append(ok("bp minimal mmHg", BP, bytes([0x00]) + sf(120) + sf(80) + sf(93),
            "blood_pressure", {"systolic": 120, "diastolic": 80, "mean_arterial": 93},
            {"systolic": "120", "diastolic": "80", "mean_arterial": "93"}, "mmHg"))
V.append(ok("bp all fields", BP,
            bytes([0x1E]) + sf(1325, -1) + sf(845, -1) + sf(1005, -1)
            + dt(2026, 10, 21, 9, 30, 5) + sf(72) + bytes([3]) + u16(0x0005),
            "blood_pressure",
            {"systolic": 133, "diastolic": 85, "mean_arterial": 101, "pulse": 72},
            {"systolic": "132.5", "diastolic": "84.5", "mean_arterial": "100.5", "pulse": "72"},
            "mmHg", flags=["body_movement", "irregular_pulse"],
            device_time="2026-10-21T09:30:05", user_id=3))
V.append(ok("bp in kPa converted to mmHg", BP,
            bytes([0x01]) + sf(160, -1) + sf(107, -1) + sf(125, -1),
            "blood_pressure", {"systolic": 120, "diastolic": 80, "mean_arterial": 94},
            {"systolic": "16.0", "diastolic": "10.7", "mean_arterial": "12.5"}, "kPa"))
V.append(ok("bp pulse range and cuff and position", BP,
            bytes([0x14]) + sf(141) + sf(92) + sf(108) + sf(118) + u16(0x0022 | (1 << 3)),
            "blood_pressure",
            {"systolic": 141, "diastolic": 92, "mean_arterial": 108, "pulse": 118},
            {"systolic": "141", "diastolic": "92", "mean_arterial": "108", "pulse": "118"},
            "mmHg", flags=["cuff_too_loose", "improper_position", "pulse_above_range"]))
V.append(ok("bp unknown device clock and unknown user", BP,
            bytes([0x0A]) + sf(110) + sf(70) + sf(83) + dt(0, 0, 0, 0, 0, 0) + bytes([0xFF]),
            "blood_pressure", {"systolic": 110, "diastolic": 70, "mean_arterial": 83},
            {"systolic": "110", "diastolic": "70", "mean_arterial": "83"}, "mmHg",
            flags=["device_clock_not_set"]))
V.append(bad("bp NaN systolic", BP, bytes([0x00]) + raw16(0x07FF) + sf(80) + sf(93), "NaN"))
V.append(bad("bp NRes", BP, bytes([0x00]) + sf(120) + raw16(0x0800) + sf(93), "NRes"))
V.append(bad("bp +INF", BP, bytes([0x00]) + sf(120) + sf(80) + raw16(0x07FE), "+INF"))
V.append(bad("bp truncated", BP, bytes([0x04]) + sf(120) + sf(80) + sf(93), "shorter"))
V.append(bad("bp trailing bytes", BP, bytes([0x00]) + sf(120) + sf(80) + sf(93) + b"\x00",
             "longer"))
V.append(bad("bp reserved flags", BP, bytes([0x80]) + sf(120) + sf(80) + sf(93), "reserved"))
V.append(bad("bp impossible time stamp", BP,
             bytes([0x02]) + sf(120) + sf(80) + sf(93) + dt(2026, 13, 1, 0, 0, 0),
             "out of range"))

# --- pulse oximeter, spot-check ---------------------------------------------------------
V.append(ok("spot minimal", SPOT, bytes([0x00]) + sf(97) + sf(72), "spo2",
            {"spo2": 97, "pulse": 72}, {"spo2": "97", "pulse": "72"}, "%"))
V.append(ok("spot all fields", SPOT,
            bytes([0x0F]) + sf(955, -1) + sf(681, -1) + dt(2026, 10, 21, 9, 31, 0)
            + u16((1 << 7) | (1 << 14)) + u24((1 << 5) | (1 << 4)) + sf(24, -1),
            "spo2", {"spo2": 96, "pulse": 68},
            {"spo2": "95.5", "pulse": "68.1", "perfusion_index": "2.4"}, "%",
            flags=["low_perfusion", "poor_signal", "questionable_measurement", "validated"],
            device_time="2026-10-21T09:31:00"))
V.append(ok("spot device clock not set flag", SPOT, bytes([0x10]) + sf(99) + sf(60),
            "spo2", {"spo2": 99, "pulse": 60}, {"spo2": "99", "pulse": "60"}, "%",
            flags=["device_clock_not_set"]))
V.append(ok("spot from storage is reported (and refused by policy)", SPOT,
            bytes([0x02]) + sf(94) + sf(80) + u16(1 << 9), "spo2",
            {"spo2": 94, "pulse": 80}, {"spo2": "94", "pulse": "80"}, "%",
            flags=["from_device_storage"]))
V.append(ok("spot unavailable perfusion index", SPOT,
            bytes([0x08]) + sf(98) + sf(75) + raw16(0x07FF), "spo2",
            {"spo2": 98, "pulse": 75}, {"spo2": "98", "pulse": "75"}, "%",
            flags=["perfusion_index_unavailable"]))
V.append(bad("spot NaN SpO2", SPOT, bytes([0x00]) + raw16(0x07FF) + sf(72), "NaN"))
V.append(bad("spot -INF pulse", SPOT, bytes([0x00]) + sf(97) + raw16(0x0802), "-INF"))
V.append(bad("spot truncated status", SPOT, bytes([0x02]) + sf(97) + sf(72) + b"\x01",
             "shorter"))

# --- pulse oximeter, continuous ---------------------------------------------------------
V.append(ok("continuous normal only", CONT, bytes([0x00]) + sf(98) + sf(64), "spo2",
            {"spo2": 98, "pulse": 64}, {"spo2": "98", "pulse": "64"}, "%"))
V.append(ok("continuous with fast, slow, status, PAI", CONT,
            bytes([0x1F]) + sf(96) + sf(70) + sf(95) + sf(71) + sf(97) + sf(69)
            + u16(1 << 5) + u24(1 << 2) + sf(31, -1),
            "spo2", {"spo2": 96, "pulse": 70},
            {"spo2": "96", "pulse": "70", "perfusion_index": "3.1"}, "%",
            flags=["measurement_ongoing", "signal_processing_irregularity"]))
V.append(bad("continuous truncated fast pair", CONT, bytes([0x01]) + sf(96) + sf(70) + sf(95),
             "shorter"))

# --- unsupported -------------------------------------------------------------------------
V.append(bad("unknown characteristic", "2a1c", bytes([0x00, 0x01, 0x02]), "unsupported"))

doc = {"description": "SYNTHETIC vectors for the M8.2 GATT parsers (not captured from "
                      "devices). Generated by scripts/generate_device_vectors.py.",
       "vectors": V}
OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"wrote {OUT.relative_to(OUT.parents[2])}: {len(V)} vectors")
