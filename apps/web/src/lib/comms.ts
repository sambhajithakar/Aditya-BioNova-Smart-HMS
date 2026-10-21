/**
 * Communications v2 + follow-up CRM: API types and pure helpers (template
 * preview, placeholder checks, worklist buckets). The server is the authority
 * — these helpers only mirror its rules for instant feedback in the editor.
 */

export const CHANNELS = ["sms", "whatsapp", "email"] as const;
export type Channel = (typeof CHANNELS)[number];
export const PURPOSES = ["appointment_reminder", "follow_up", "missed_appointment", "generic"] as const;
export const TEMPLATE_LANGS = ["en", "mr", "hi"] as const;
export const DELIVERY_STATUSES = [
  "sent_mock",
  "sent",
  "queued",
  "suppressed",
  "failed",
  "skipped_no_consent",
  "skipped_quota",
  "skipped_quiet_hours",
  "skipped_no_recipient",
  "skipped_no_template",
] as const;
export const CONSENT_SOURCES = [
  "registration_form",
  "patient_request",
  "patient_reply",
  "staff_update",
] as const;
export const FOLLOWUP_BUCKETS = ["due_today", "overdue", "upcoming", "closed"] as const;
export type FollowUpBucket = (typeof FOLLOWUP_BUCKETS)[number];
/** Suggested non-clinical labels; the reason never appears in a patient message. */
export const FOLLOWUP_REASONS = [
  "Review visit",
  "Routine check-up",
  "Dressing change",
  "Report review",
  "Vaccination due",
];

/** Mirrors app/comms/templates.py (ALLOWED / DISALLOWED_PLACEHOLDERS). */
export const ALLOWED_PLACEHOLDERS = [
  "patient_first_name",
  "clinic_name",
  "clinic_phone",
  "branch_name",
  "doctor_name",
  "appointment_date",
  "appointment_time",
  "follow_up_date",
] as const;
export const DISALLOWED_PLACEHOLDERS = [
  "diagnosis", "diagnoses", "condition", "disease", "symptoms", "complaint",
  "medicine", "medicines", "medication", "medications", "prescription", "drug", "dose",
  "lab_result", "lab_results", "test_result", "result", "report", "allergies",
  "notes", "clinical_notes", "reason", "appointment_reason", "follow_up_reason",
  "procedure", "treatment", "uhid", "patient_full_name", "patient_name",
  "date_of_birth", "age", "address", "phone", "patient_phone", "abha", "aadhaar",
];

/** Synthetic sample values — never real patient data. */
export const SAMPLE_VALUES: Record<string, string> = {
  patient_first_name: "Asha",
  clinic_name: "Demo Clinic",
  clinic_phone: "+91 90000 00000",
  branch_name: "Main Branch",
  doctor_name: "Dr. Demo",
  appointment_date: "15 Jan 2026",
  appointment_time: "10:30 AM",
  follow_up_date: "22 Jan 2026",
};

export const MAX_BODY: Record<Channel, number> = { sms: 1000, whatsapp: 1024, email: 2000 };

const TOKEN_RE = /\{([^{}]*)\}/g;

export function placeholdersIn(text: string): string[] {
  return [...(text ?? "").matchAll(TOKEN_RE)].map((m) => m[1].trim());
}

export type PlaceholderProblem = { kind: "disallowed" | "unknown" | "braces"; name?: string };

export function placeholderProblems(text: string): PlaceholderProblem[] {
  const out: PlaceholderProblem[] = [];
  const rest = (text ?? "").replace(TOKEN_RE, "");
  if (rest.includes("{") || rest.includes("}")) out.push({ kind: "braces" });
  const seen = new Set<string>();
  for (const name of placeholdersIn(text)) {
    if (seen.has(name)) continue;
    seen.add(name);
    if (DISALLOWED_PLACEHOLDERS.includes(name.toLowerCase())) out.push({ kind: "disallowed", name });
    else if (!(ALLOWED_PLACEHOLDERS as readonly string[]).includes(name))
      out.push({ kind: "unknown", name });
  }
  return out;
}

/** Fill whitelisted placeholders; anything else stays visible as typed. */
export function renderTemplate(text: string, values: Record<string, string> = SAMPLE_VALUES): string {
  return (text ?? "").replace(TOKEN_RE, (whole, raw: string) => {
    const name = raw.trim();
    return (ALLOWED_PLACEHOLDERS as readonly string[]).includes(name) ? (values[name] ?? "") : whole;
  });
}

/** SMS segments: GSM-7 160 chars, UCS-2 (e.g. Devanagari) 70 chars per segment. */
export function smsSegments(text: string): number {
  if (!text) return 0;
  const per = /^[\x00-\x7F]*$/.test(text) ? 160 : 70;
  return Math.max(1, Math.ceil([...text].length / per));
}

/** Local (browser) calendar date as YYYY-MM-DD. */
export function isoDay(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function followUpBucket(dueDate: string, status: string, today: string): FollowUpBucket {
  if (status === "completed" || status === "cancelled") return "closed";
  if (dueDate < today) return "overdue";
  if (dueDate === today) return "due_today";
  return "upcoming";
}

export const FOLLOWUP_ACTIONS: Record<string, string[]> = {
  planned: ["book", "complete", "missed", "cancel"],
  reminded: ["book", "complete", "missed", "cancel"],
  booked: ["complete", "missed", "cancel"],
  missed: ["book", "cancel"],
  completed: [],
  cancelled: [],
};

export function isSkip(status: string): boolean {
  return status.startsWith("skipped_");
}

// ------------------------------------------------------------------ API types
export type CommsTemplate = {
  id: string;
  channel: Channel;
  purpose: string;
  language: string;
  name: string;
  subject: string;
  body: string;
  dlt_template_id: string | null;
  whatsapp_template_name: string | null;
  is_active: boolean;
  is_default: boolean;
  placeholders: string[];
  updated_at: string;
};

export type CommsSettings = {
  monthly_spend_cap_paise: number | null;
  quiet_start_hour: number;
  quiet_end_hour: number;
  reminder_hours_ahead: number;
  reminder_channels: Channel[];
  updated_at?: string;
};

export type ChannelUsage = {
  channel: Channel;
  entitled: boolean;
  provider: string;
  mock: boolean;
  live: boolean;
  used: number;
  limit: number | null;
  cost_paise: number;
  cost_per_message_paise: number;
};

export type CommsOverview = {
  period: string;
  live_enabled: boolean;
  mock_notice: string;
  channels: ChannelUsage[];
  spend_paise: number;
  spend_cap_paise: number | null;
  consent: { channel: Channel; opted_in: number; opted_out: number; unknown: number }[];
  active_patients: number;
  settings: CommsSettings;
  in_quiet_hours: boolean;
};

export type Delivery = {
  id: number;
  channel: Channel;
  purpose: string;
  language: string | null;
  template_id: string | null;
  patient_id: string | null;
  appointment_id: string | null;
  follow_up_id: string | null;
  recipient_masked: string | null;
  provider: string;
  status: string;
  cost_paise: number;
  trigger: string;
  error: string | null;
  created_at: string;
};

export type DeliveryPage = { items: Delivery[]; total: number; limit: number; offset: number };

export type ReminderRun = {
  window_start: string;
  window_end: string;
  channels: Channel[];
  quiet_hours: boolean;
  appointments: number;
  follow_ups: number;
  sent: number;
  by_status: Record<string, number>;
  mock_notice: string;
};

export type SendResult = {
  results: { channel: Channel; status: string; log_id: number | null }[];
  mock_notice: string;
};

export type PatientComms = {
  patient_id: string;
  preferred_language: string | null;
  email: string | null;
  phone_masked: string | null;
  consents: {
    channel: Channel;
    status: "opted_in" | "opted_out" | null;
    source: string | null;
    recorded_at: string | null;
    actor_name: string | null;
  }[];
  history: { channel: Channel; status: string; source: string; recorded_at: string; actor_name: string | null }[];
};

export type FollowUp = {
  id: string;
  patient_id: string;
  patient_name: string;
  patient_uhid: string;
  branch_id: string | null;
  due_date: string;
  reason: string;
  status: string;
  bucket: FollowUpBucket;
  assigned_user_id: string | null;
  assigned_name: string | null;
  created_by_name: string | null;
  appointment_id: string | null;
  appointment_starts_at: string | null;
  status_note: string;
  reminded_at: string | null;
  closed_at: string | null;
  created_at: string;
};

export type MissedAppointment = {
  appointment_id: string;
  patient_id: string;
  patient_name: string;
  patient_uhid: string;
  starts_at: string;
  status: string;
  provider_name: string | null;
  notified: boolean;
  open_follow_up_id: string | null;
};
