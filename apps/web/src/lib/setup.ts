/**
 * Smart Setup Wizard, QR check-in and printer setup: wire types and pure
 * helpers (unit-tested in setup.test.ts). The server re-validates
 * everything; these helpers only give owners instant, plain feedback.
 */

// --- wire types ---------------------------------------------------------------------
export const WIZARD_STEPS = [
  "identity",
  "branch",
  "staff",
  "language",
  "working_hours",
  "fees",
  "prescription",
  "billing",
  "printer",
  "schedule",
  "edition",
] as const;
export type WizardStepKey = (typeof WIZARD_STEPS)[number];
export type StepStatus = "done" | "skipped" | "todo";

export type WizardStep = { key: WizardStepKey; status: StepStatus; data_ready: boolean };
export type WizardState = {
  steps: WizardStep[];
  current_step: WizardStepKey;
  finished: boolean;
  finished_at: string | null;
  should_show: boolean;
  progress_percent: number;
};

export type PrescriptionSettings = {
  header_text: string;
  footer_text: string;
  show_registration_number: boolean;
  paper_size: "A4" | "A5";
  language: "en" | "mr" | "hi" | "trilingual";
};
export const PAYMENT_METHODS = ["cash", "upi", "card", "insurance", "other"] as const;
export type PaymentMethod = (typeof PAYMENT_METHODS)[number];
export type BillingSettings = {
  invoice_prefix: string;
  show_gstin: boolean;
  default_payment_methods: PaymentMethod[];
  receipt_footer: string;
};
export const SLOT_LENGTHS = [5, 10, 15, 20, 30, 45, 60] as const;
export type ScheduleSettings = {
  slot_minutes: number;
  max_per_slot: number;
  online_booking_enabled: boolean;
};
export type OrgSettingsDoc = {
  version: 1;
  prescription: PrescriptionSettings;
  billing: BillingSettings;
  schedule: ScheduleSettings;
};
export type OrgSettingsOut = { schema_version: number; settings: OrgSettingsDoc; updated_at: string | null };

export type WorkingSession = {
  weekday: number;
  opens_at: string; // "HH:MM" (server may answer "HH:MM:SS")
  closes_at: string;
  break_starts_at: string | null;
  break_ends_at: string | null;
};
export type WorkingHoursOut = { branch_id: string; sessions: WorkingSession[] };

export type Fee = {
  provider_user_id: string | null;
  consultation_fee: string;
  follow_up_fee: string | null;
  follow_up_valid_days: number | null;
  updated_at: string;
};
export type FeesOut = { default: Fee | null; providers: Fee[] };

export type Slot = { starts_at: string; ends_at: string; booked: number; available: boolean };
export type SlotsOut = {
  branch_id: string;
  date: string;
  provider_user_id: string | null;
  configured: boolean;
  slot_minutes: number;
  max_per_slot: number;
  slots: Slot[];
};

export type CheckinIssue = { appointment_id: string; token: string; expires_at: string };
export type CheckinVerify = {
  status: "ready" | "already_checked_in";
  appointment_id: string;
  patient_display_name: string;
  appointment_starts_at: string;
  branch_name: string;
  queue_token_number: number | null;
};
export type CheckinConfirm = {
  status: "checked_in" | "already_checked_in";
  appointment_id: string;
  queue_entry: { id: string; token_number: number; status: string; service_date: string };
};
export type KioskCheckin = { status: "checked_in" | "already_checked_in"; token_number: number };

export const PRINTER_KINDS = ["a4", "a5", "thermal_80mm", "thermal_58mm"] as const;
export type PrinterKind = (typeof PRINTER_KINDS)[number];
export const PRINT_DOCUMENTS = ["prescription", "receipt", "lab_report"] as const;
export type PrintDocument = (typeof PRINT_DOCUMENTS)[number];
export type PrinterProfile = {
  id: string;
  name: string;
  kind: PrinterKind;
  default_for: PrintDocument[];
  margin_top_mm: string | number;
  margin_right_mm: string | number;
  margin_bottom_mm: string | number;
  margin_left_mm: string | number;
  font_scale: string | number;
  notes: string;
  created_at: string;
  updated_at: string;
};
export type PrinterDefaults = Record<PrintDocument, PrinterProfile | null>;

// --- wizard ---------------------------------------------------------------------------
/** The step to open: the server's current step, else the first one to do. */
export function resumeStep(state: WizardState | null): WizardStepKey {
  if (!state) return WIZARD_STEPS[0];
  if ((WIZARD_STEPS as readonly string[]).includes(state.current_step)) return state.current_step;
  return state.steps.find((s) => s.status === "todo")?.key ?? WIZARD_STEPS[0];
}

export function neighbourStep(key: WizardStepKey, dir: 1 | -1): WizardStepKey | null {
  const i = WIZARD_STEPS.indexOf(key) + dir;
  return i >= 0 && i < WIZARD_STEPS.length ? WIZARD_STEPS[i] : null;
}

// --- working hours --------------------------------------------------------------------
const HHMM = /^([01]\d|2[0-3]):([0-5]\d)(:[0-5]\d)?$/;

export function minutesOf(t: string | null | undefined): number | null {
  const m = t ? HHMM.exec(t) : null;
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}

export function hhmm(t: string | null | undefined): string {
  return t ? t.slice(0, 5) : "";
}

export type HoursError = { weekday: number; code: "range" | "break" | "breakHalf" | "overlap" | "time" };

/** Mirrors the API's rules: valid times, opens < closes, break inside the
 * session, no overlapping sessions on one day. */
export function workingHoursErrors(sessions: WorkingSession[]): HoursError[] {
  const errors: HoursError[] = [];
  for (const s of sessions) {
    const o = minutesOf(s.opens_at);
    const c = minutesOf(s.closes_at);
    if (o === null || c === null) {
      errors.push({ weekday: s.weekday, code: "time" });
      continue;
    }
    if (o >= c) {
      errors.push({ weekday: s.weekday, code: "range" });
      continue;
    }
    const hasBs = !!s.break_starts_at;
    const hasBe = !!s.break_ends_at;
    if (hasBs !== hasBe) {
      errors.push({ weekday: s.weekday, code: "breakHalf" });
      continue;
    }
    if (hasBs) {
      const bs = minutesOf(s.break_starts_at);
      const be = minutesOf(s.break_ends_at);
      if (bs === null || be === null || !(o < bs && bs < be && be < c)) {
        errors.push({ weekday: s.weekday, code: "break" });
      }
    }
  }
  if (errors.length) return errors;
  for (let d = 0; d < 7; d++) {
    const day = sessions
      .filter((s) => s.weekday === d)
      .sort((a, b) => (minutesOf(a.opens_at) ?? 0) - (minutesOf(b.opens_at) ?? 0));
    for (let i = 1; i < day.length; i++) {
      if ((minutesOf(day[i].opens_at) ?? 0) < (minutesOf(day[i - 1].closes_at) ?? 0)) {
        errors.push({ weekday: d, code: "overlap" });
      }
    }
  }
  return errors;
}

/** Sensible pre-filled week for a small Indian clinic: Mon–Sat 9–6, lunch 1–2. */
export function defaultWeek(): WorkingSession[] {
  return [0, 1, 2, 3, 4, 5].map((weekday) => ({
    weekday,
    opens_at: "09:00",
    closes_at: "18:00",
    break_starts_at: "13:00",
    break_ends_at: "14:00",
  }));
}

/** Normalise times to "HH:MM" and drop empty breaks before sending. */
export function cleanSessions(sessions: WorkingSession[]): WorkingSession[] {
  return sessions.map((s) => ({
    weekday: s.weekday,
    opens_at: hhmm(s.opens_at),
    closes_at: hhmm(s.closes_at),
    break_starts_at: s.break_starts_at ? hhmm(s.break_starts_at) : null,
    break_ends_at: s.break_ends_at ? hhmm(s.break_ends_at) : null,
  }));
}

// --- check-in codes -------------------------------------------------------------------
const CODE_RE = /^[A-Z2-7]{26}$/;

/** What staff type or a scanner reads -> canonical token, or null. Spaces,
 * hyphens and case are ignored; 0/1/8 are read as O/I/B (not in base32). */
export function normalizeCheckinCode(input: string): string | null {
  const cleaned = (input || "")
    .replace(/[\s\-_.]/g, "")
    .toUpperCase()
    .replace(/0/g, "O")
    .replace(/1/g, "I")
    .replace(/8/g, "B");
  return CODE_RE.test(cleaned) ? cleaned : null;
}

/** Group a token for reading aloud / typing: "ABCD EFGH … YZ". */
export function formatCheckinCode(token: string): string {
  return token.replace(/(.{4})(?=.)/g, "$1 ");
}

// --- money ------------------------------------------------------------------------------
/** "350", "350.5", "350.50" -> "350.50"; "" -> null; invalid -> undefined. */
export function parseFee(input: string): string | null | undefined {
  const v = input.trim();
  if (v === "") return null;
  if (!/^\d{1,7}(\.\d{1,2})?$/.test(v)) return undefined;
  const n = Number(v);
  if (n > 1_000_000) return undefined;
  return n.toFixed(2);
}

export function feeInput(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "";
  const n = Number(v);
  return Number.isFinite(n) ? (Number.isInteger(n) ? String(n) : n.toFixed(2)) : "";
}

// --- printers -----------------------------------------------------------------------------
export const PAPER: Record<PrinterKind, { widthMm: number; heightMm: number | null; cssSize: string }> = {
  a4: { widthMm: 210, heightMm: 297, cssSize: "A4" },
  a5: { widthMm: 148, heightMm: 210, cssSize: "A5" },
  // roll paper: height follows the content
  thermal_80mm: { widthMm: 80, heightMm: null, cssSize: "80mm auto" },
  thermal_58mm: { widthMm: 58, heightMm: null, cssSize: "58mm auto" },
};

function mm(v: string | number | undefined, fallback: number): number {
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 && n <= 50 ? n : fallback;
}

export type PageGeometry = {
  kind: PrinterKind;
  size: string;
  margins: [number, number, number, number];
  fontScale: number;
  contentWidthMm: number;
};

export function pageGeometry(profile: PrinterProfile | null, fallback: PrinterKind = "a4"): PageGeometry {
  const kind = profile && PRINTER_KINDS.includes(profile.kind) ? profile.kind : fallback;
  const thermal = kind.startsWith("thermal");
  const def = thermal ? 3 : 12;
  const margins: [number, number, number, number] = [
    mm(profile?.margin_top_mm, def),
    mm(profile?.margin_right_mm, def),
    mm(profile?.margin_bottom_mm, def),
    mm(profile?.margin_left_mm, def),
  ];
  const fs = Number(profile?.font_scale ?? 1);
  const fontScale = Number.isFinite(fs) && fs >= 0.5 && fs <= 2 ? fs : 1;
  const paper = PAPER[kind];
  return {
    kind,
    size: paper.cssSize,
    margins,
    fontScale,
    contentWidthMm: Math.max(10, paper.widthMm - margins[1] - margins[3]),
  };
}

/** `@page` + sheet rules for a print route. Only numbers and known keywords
 * are interpolated, so the result is safe to inline in a <style> element. */
export function pageCss(g: PageGeometry): string {
  const [t, r, b, l] = g.margins;
  return [
    `@media print { @page { size: ${g.size}; margin: ${t}mm ${r}mm ${b}mm ${l}mm; } }`,
    `.print-sheet { font-size: ${(g.fontScale * 100).toFixed(0)}%; }`,
    `@media print { .print-sheet { width: ${g.contentWidthMm}mm; max-width: none; } }`,
    g.kind.startsWith("thermal")
      ? ".print-sheet { max-width: " + g.contentWidthMm + "mm; padding: 0.5rem; }"
      : "",
  ].join("\n");
}

/** Fill "{name}" placeholders in a translated string. */
export function fill(text: string, vars: Record<string, string | number>): string {
  return text.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

/** The default profile for a document, falling back to a sensible kind. */
export function profileFor(defaults: PrinterDefaults | null, doc: PrintDocument): PrinterProfile | null {
  return defaults?.[doc] ?? null;
}
