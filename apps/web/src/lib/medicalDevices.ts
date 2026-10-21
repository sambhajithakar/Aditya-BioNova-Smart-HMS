/**
 * Medical device readings (M8.2) as served by /device-readings. The API
 * parses the raw Bluetooth payload itself; the web only displays and lets a
 * clinician accept or reject. Nothing is ever accepted automatically.
 */
export type DeviceKind = "bp_monitor" | "pulse_oximeter";

export type MedicalDevice = {
  id: string;
  kind: DeviceKind;
  label: string;
  manufacturer: string;
  model: string;
  serial: string;
  firmware: string;
  branch_id: string | null;
  is_simulator: boolean;
  status: "active" | "retired";
  created_at: string;
  retired_at: string | null;
  hardware_validated: boolean;
};

export type DeviceReading = {
  id: string;
  device_id: string;
  device_label: string;
  device_is_simulator: boolean;
  patient_id: string;
  encounter_id: string;
  kind: "blood_pressure" | "spo2";
  values: Record<string, number>;
  exact: Record<string, string>;
  unit: string;
  flags: string[];
  raw_hex: string;
  raw_sha256: string;
  source: "ble" | "simulator";
  device_time: string | null;
  captured_at: string;
  received_at: string;
  clock_skew: boolean;
  status: "pending_review" | "accepted" | "rejected";
  decision: {
    decision: string;
    reason: string;
    surface: string;
    vitals_id: string | null;
    decided_at: string;
  } | null;
};

/** "BP 133/85 mmHg · pulse 72/min" — values as the server parsed them. */
export function readingSummary(r: Pick<DeviceReading, "kind" | "values">): string {
  const v = r.values;
  const main =
    r.kind === "blood_pressure" ? `BP ${v.systolic}/${v.diastolic} mmHg` : `SpO2 ${v.spo2} %`;
  return v.pulse === undefined ? main : `${main} · pulse ${v.pulse}/min`;
}

/** The device's own unit when it was not mmHg (kPa readings keep their exact text). */
export function originalUnitNote(r: Pick<DeviceReading, "unit" | "exact" | "kind">): string | null {
  if (r.kind !== "blood_pressure" || r.unit !== "kPa") return null;
  return `device: ${r.exact.systolic}/${r.exact.diastolic} kPa`;
}

const SIM_ADDRESS = /^SIM-[0-9A-F]{8}$/i;
const BLE_ADDRESS = /^([0-9A-F]{2}:){5}[0-9A-F]{2}$/i;

/** Validates the address typed when registering a device from the web. */
export function addressKind(address: string): "ble" | "simulator" | null {
  const a = address.trim();
  if (SIM_ADDRESS.test(a)) return "simulator";
  if (BLE_ADDRESS.test(a)) return "ble";
  return null;
}
