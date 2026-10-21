"""M8.2a: GATT parsers against the shared SYNTHETIC vectors (the Android
app's Dart parser runs the same file) plus the SFLOAT edge cases."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.devices import gatt

VECTORS = json.loads((Path(__file__).resolve().parents[3] / "packages" / "contracts"
                      / "device_vectors.json").read_text(encoding="utf-8"))["vectors"]


@pytest.mark.parametrize("v", VECTORS, ids=[v["name"] for v in VECTORS])
def test_shared_vectors(v):
    if "error" in v:
        with pytest.raises(gatt.GattError, match=v["error"].replace("+", r"\+")):
            gatt.parse(v["characteristic"], v["hex"])
    else:
        assert gatt.parse(v["characteristic"], v["hex"]) == v["expect"]


def test_sfloat_sign_extension_and_decimals():
    assert gatt.sfloat(0x0001) == (1, 0)
    assert gatt.sfloat(0x0FFF) == (-1, 0)              # 12-bit two's complement
    assert gatt.sfloat(0xF4B5) == (0x4B5, -1)          # exponent -1
    assert gatt.sfloat(0x2003) == (3, 2)
    assert gatt.as_decimal(1205, -1) == "120.5"
    assert gatt.as_decimal(5, -2) == "0.05"
    assert gatt.as_decimal(-15, -1) == "-1.5"
    assert gatt.as_decimal(3, 2) == "300"
    for special in (0x07FF, 0x0800, 0x07FE, 0x0802, 0x0801):
        with pytest.raises(gatt.GattError):
            gatt.sfloat(special)


def test_half_up_rounding():
    assert [gatt.half_up(x) for x in (0.5, 1.49, 132.5, 84.5, -1.5)] == [1, 1, 133, 85, -2]


def test_capture_policy_refuses_unusable_readings():
    stored = next(v for v in VECTORS if "storage" in v["name"])["expect"]
    assert "from_device_storage" in gatt.refusal_reason(stored)
    ongoing = next(v for v in VECTORS if v["name"].startswith("continuous with"))["expect"]
    assert "measurement_ongoing" in gatt.refusal_reason(ongoing)
    fine = next(v for v in VECTORS if v["name"] == "bp all fields")["expect"]
    assert gatt.refusal_reason(fine) is None   # movement / irregular pulse: shown, not refused


def test_input_hygiene():
    for hexs in ("zz", "", "00" * 65):
        with pytest.raises(gatt.GattError):
            gatt.parse("2a35", hexs)
    assert gatt.parse("0x2A35", VECTORS[0]["hex"])["values"]["systolic"] == 120
