import { describe, expect, it } from "vitest";
import { addressKind, originalUnitNote, readingSummary } from "./medicalDevices";

describe("medical device helpers (M8.2)", () => {
  it("summarises the server's parsed values", () => {
    expect(readingSummary({ kind: "blood_pressure", values: { systolic: 133, diastolic: 85, pulse: 72 } }))
      .toBe("BP 133/85 mmHg · pulse 72/min");
    expect(readingSummary({ kind: "spo2", values: { spo2: 97, pulse: 70 } })).toBe("SpO2 97 % · pulse 70/min");
    expect(readingSummary({ kind: "blood_pressure", values: { systolic: 120, diastolic: 80 } }))
      .toBe("BP 120/80 mmHg");
  });

  it("keeps the device's own kPa text visible", () => {
    expect(originalUnitNote({ kind: "blood_pressure", unit: "kPa",
      exact: { systolic: "16.0", diastolic: "10.7" } })).toBe("device: 16.0/10.7 kPa");
    expect(originalUnitNote({ kind: "blood_pressure", unit: "mmHg", exact: {} })).toBeNull();
  });

  it("tells a Bluetooth address from a simulator id", () => {
    expect(addressKind("aa:bb:cc:dd:ee:ff")).toBe("ble");
    expect(addressKind(" SIM-0000B001 ")).toBe("simulator");
    expect(addressKind("sim-0000b001")).toBe("simulator");
    expect(addressKind("AA-BB-CC")).toBeNull();
    expect(addressKind("SIM-123")).toBeNull();
  });
});
