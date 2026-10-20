/**
 * Prescription item builder model + validation (C1).
 *
 * No silent defaults: every clinical field starts EMPTY and must be filled
 * by the prescriber. Limits mirror the backend RxItemIn schema
 * (dose/frequency 1..100 chars, duration 1..365 days, quantity ≤100 chars,
 * instructions ≤500 chars) plus the M7 `dispense_quantity` (int 1..10000,
 * optional).
 */

export const FREQUENCIES = [
  "OD",
  "BD",
  "TDS",
  "QID",
  "HS",
  "SOS",
  "STAT",
  "Q4H",
  "Q6H",
  "Q8H",
  "Weekly",
] as const;

/** Must match the backend's allowed routes (schemas._ROUTES). */
export const ROUTES = [
  "oral",
  "sublingual",
  "topical",
  "inhalation",
  "nasal",
  "ophthalmic",
  "otic",
  "injectable",
  "rectal",
  "other",
] as const;

export type RxDraftItem = {
  key: string;
  drug_id: string;
  drug_name: string;
  dose: string;
  route: string;
  frequency: string;
  duration_days: string;
  quantity: string;
  instructions: string;
  dispense_quantity: string;
};

export type RxField =
  | "dose"
  | "route"
  | "frequency"
  | "duration_days"
  | "quantity"
  | "instructions"
  | "dispense_quantity";

/** i18n keys for each validation failure. */
export type RxErrorKey =
  | "rxErrRequired"
  | "rxErrTooLong"
  | "rxErrDuration"
  | "rxErrDispenseQty";

export type RxItemErrors = Partial<Record<RxField, RxErrorKey>>;

/** Shape sent to POST /prescriptions (RxItemIn). */
export type RxItemIn = {
  drug_id: string;
  dose: string;
  route: string;
  frequency: string;
  duration_days: number;
  quantity: string;
  instructions: string;
  dispense_quantity?: number;
};

let counter = 0;

export function emptyRxItem(drug: { id: string; generic_name: string }): RxDraftItem {
  counter += 1;
  return {
    key: `${drug.id}-${Date.now()}-${counter}`,
    drug_id: drug.id,
    drug_name: drug.generic_name,
    dose: "",
    route: "",
    frequency: "",
    duration_days: "",
    quantity: "",
    instructions: "",
    dispense_quantity: "",
  };
}

const INT_RE = /^\d+$/;

export function validateRxItem(it: RxDraftItem): RxItemErrors {
  const e: RxItemErrors = {};
  const dose = it.dose.trim();
  if (!dose) e.dose = "rxErrRequired";
  else if (dose.length > 100) e.dose = "rxErrTooLong";

  if (!it.route.trim()) e.route = "rxErrRequired";
  else if (!(ROUTES as readonly string[]).includes(it.route.trim())) e.route = "rxErrRequired";

  const freq = it.frequency.trim();
  if (!freq) e.frequency = "rxErrRequired";
  else if (freq.length > 100) e.frequency = "rxErrTooLong";

  const dur = it.duration_days.trim();
  if (!dur) e.duration_days = "rxErrRequired";
  else if (!INT_RE.test(dur) || Number(dur) < 1 || Number(dur) > 365) e.duration_days = "rxErrDuration";

  if (it.quantity.trim().length > 100) e.quantity = "rxErrTooLong";
  if (it.instructions.trim().length > 500) e.instructions = "rxErrTooLong";

  const dq = it.dispense_quantity.trim();
  if (dq && (!INT_RE.test(dq) || Number(dq) < 1 || Number(dq) > 10000)) {
    e.dispense_quantity = "rxErrDispenseQty";
  }
  return e;
}

export function isRxItemValid(it: RxDraftItem): boolean {
  return Object.keys(validateRxItem(it)).length === 0;
}

/** Convert a VALID draft row to the API payload (dispense_quantity omitted when blank). */
export function toRxItemIn(it: RxDraftItem): RxItemIn {
  const out: RxItemIn = {
    drug_id: it.drug_id,
    dose: it.dose.trim(),
    route: it.route.trim(),
    frequency: it.frequency.trim(),
    duration_days: Number(it.duration_days.trim()),
    quantity: it.quantity.trim(),
    instructions: it.instructions.trim(),
  };
  const dq = it.dispense_quantity.trim();
  if (dq) out.dispense_quantity = Number(dq);
  return out;
}
