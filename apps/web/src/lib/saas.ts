/**
 * M7.1 commercial SaaS layer (contract: m71_contract.md): editions, feature
 * gating, plan limits, subscription status, tenant administration, support
 * tickets and the platform (vendor) console.
 *
 * Pure helpers live here so they can be unit-tested without React: money in
 * paise, GSTIN / pincode validation, usage meters, feature-gated navigation,
 * the MFA-enrolment redirect rule and server-message extraction.
 */
import { ApiError } from "./api";
import type { Me } from "./api";

// --- stable identifiers -------------------------------------------------------
export const PLAN_CODES = [
  "rural_clinic",
  "clinic_starter",
  "clinic_plus_ai",
  "multi_specialty_clinic",
  "hospital_core",
  "hospital_advanced",
  "enterprise",
] as const;

export const FEATURE_KEYS = [
  "patients",
  "appointments",
  "opd_queue",
  "consultation",
  "billing",
  "pharmacy",
  "laboratory",
  "ipd",
  "nursing",
  "inventory",
  "expenses",
  "reports_basic",
  "reports_advanced",
  "multi_branch",
  "departments",
  "emergency",
  "ot",
  "insurance_tpa",
  "mobile_offline",
  "comms_email",
  "comms_sms",
  "comms_whatsapp",
  "medical_devices",
  "ai_scribe",
  "ai_copilot",
  "ai_agents",
  "ai_rag",
  "ai_document",
  "ai_forecast",
  "abdm",
  "fhir_api",
  "api_access",
  "custom_roles",
  "audit_export",
  "priority_support",
] as const;

export const LIMIT_KEYS = [
  "max_users",
  "max_branches",
  "max_beds",
  "ai_credits_monthly",
  "sms_monthly",
  "whatsapp_monthly",
] as const;

/** Stored subscription statuses (the platform editor can set any of them). */
export const SUBSCRIPTION_STATUSES = [
  "trialing",
  "active",
  "past_due",
  "read_only",
  "suspended",
  "cancelled",
] as const;
export type SubscriptionStatus = (typeof SUBSCRIPTION_STATUSES)[number];

/** Roles that can be put under the organisation's MFA policy. */
export const MFA_POLICY_ROLES = [
  "owner",
  "admin",
  "doctor",
  "nurse",
  "receptionist",
  "pharmacist",
  "lab_technician",
  "billing",
  "auditor",
  "support",
] as const;

export const TICKET_CATEGORIES = [
  "technical",
  "billing",
  "account",
  "feature_request",
  "data_request",
  "other",
] as const;
export const TICKET_PRIORITIES = ["low", "normal", "high", "urgent"] as const;
export const TICKET_STATUSES = [
  "open",
  "in_progress",
  "waiting_on_customer",
  "resolved",
  "closed",
] as const;

export const ONBOARDING_STEPS: { key: string; href: string }[] = [
  { key: "profile", href: "/settings/organization" },
  { key: "branch", href: "/settings/branches" },
  { key: "staff", href: "/settings/members" },
  { key: "mfa_owner", href: "/settings/security" },
  { key: "mfa_policy", href: "/settings/organization#mfa-policy" },
  { key: "edition", href: "/settings/subscription" },
];

// --- wire types ---------------------------------------------------------------
export type Limits = Record<string, number | null>;

export type PlanOut = {
  code: string;
  name: string;
  description: string;
  tier: number;
  price_monthly_paise: number | null;
  price_annual_paise: number | null;
  currency: "INR";
  trial_days: number;
  features: string[];
  limits: Limits;
};

export type PlatformPlanOut = PlanOut & {
  is_active: boolean;
  is_public: boolean;
  sort_order: number;
};

export type UsageEntry = { limit: number | null; used: number };

export type SubscriptionOut = {
  plan: PlanOut;
  status: SubscriptionStatus;
  effective_status: SubscriptionStatus;
  billing_cycle: "monthly" | "annual";
  trial_ends_at: string | null;
  current_period_end: string | null;
  read_only_reason: string | null;
  features: string[];
  usage: Record<string, UsageEntry>;
};

export type OrganizationProfile = {
  id: string;
  name: string;
  slug: string;
  status: string;
  legal_name: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  pincode: string | null;
  phone: string | null;
  email: string | null;
  gstin: string | null;
  registration_number: string | null;
  letterhead_note: string | null;
  default_language: "en" | "mr" | "hi";
  timezone: string;
  mfa_required_roles: string[];
  offboarding_requested_at: string | null;
  created_at: string;
};

export type Onboarding = { completed: boolean; steps: { key: string; done: boolean }[] };

export type BranchOut = {
  id: string;
  name: string;
  code: string;
  status: string;
  address: string | null;
  phone: string | null;
  gstin: string | null;
  created_at: string;
};

export type SupportTicket = {
  id: string;
  number: string | number;
  subject: string;
  category: string;
  priority: string;
  status: string;
  created_at: string;
  updated_at: string;
  created_by_name: string | null;
  organization_name?: string;
};

export type SupportMessage = {
  id: string;
  author_name: string | null;
  author_side: "customer" | "vendor";
  body: string;
  created_at: string;
  internal?: boolean;
};

export type SupportTicketDetail = SupportTicket & { messages: SupportMessage[] };

export type AuditEvent = {
  id: number;
  organization_id: string | null;
  actor_user_id: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  metadata: Record<string, unknown>;
  correlation_id: string | null;
  created_at: string;
};

export type PlatformOverview = {
  tenants_by_status: Record<string, number>;
  tenants_by_plan: Record<string, number>;
  trials_expiring_7d: number;
  open_tickets: number;
  mrr_paise: number;
  unpriced_active_subscriptions: number;
};

export type PlatformTenant = {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string;
  plan_code: string | null;
  subscription_status: string | null;
  effective_status: string | null;
  trial_ends_at: string | null;
  users: number;
  branches: number;
  beds: number;
  patients: number;
  offboarding_requested_at: string | null;
};

export type SubscriptionEvent = {
  id: string;
  from_plan: string | null;
  to_plan: string | null;
  from_status: string | null;
  to_status: string | null;
  reason: string | null;
  actor_name: string | null;
  created_at: string;
};

export type PlatformTenantDetail = PlatformTenant & {
  subscription: SubscriptionOut | null;
  events: SubscriptionEvent[];
};

export type Catalog = {
  features: { key: string; label: string }[];
  limits: { key: string; label: string }[];
};

// --- money --------------------------------------------------------------------
const INR = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

/** 149900 → "₹1,499"; 149950 → "₹1,499.50"; null → null ("not configured"). */
export function formatPaise(paise: number | null | undefined): string | null {
  if (paise === null || paise === undefined || !Number.isFinite(paise)) return null;
  const rupees = paise / 100;
  const s = INR.format(rupees);
  // keep two decimals when there are paise so ₹1,499.5 reads ₹1,499.50
  return paise % 100 !== 0 && /\.\d$/.test(s) ? `${s}0` : s;
}

export type ParsedRupees = { ok: true; paise: number | null } | { ok: false };

/**
 * Operator input in rupees → integer paise. Empty means "no price" (null);
 * otherwise a non-negative amount with at most two decimals.
 */
export function parseRupeesToPaise(input: string): ParsedRupees {
  const s = input.trim().replace(/,/g, "").replace(/^₹\s*/, "");
  if (s === "") return { ok: true, paise: null };
  if (!/^\d{1,9}(\.\d{1,2})?$/.test(s)) return { ok: false };
  const [whole, frac = ""] = s.split(".");
  return { ok: true, paise: Number(whole) * 100 + Number(frac.padEnd(2, "0")) };
}

/** Integer paise → editable rupee string ("1499" / "1499.50" / ""). */
export function paiseToRupeesInput(paise: number | null | undefined): string {
  if (paise === null || paise === undefined) return "";
  const whole = Math.floor(paise / 100);
  const frac = paise % 100;
  return frac === 0 ? String(whole) : `${whole}.${String(frac).padStart(2, "0")}`;
}

// --- validation ---------------------------------------------------------------
export const GSTIN_RE = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;
export const PINCODE_RE = /^[1-9][0-9]{5}$/;

/** Empty is allowed (optional field); otherwise must match the contract regex. */
export function isValidGstin(v: string | null | undefined): boolean {
  const s = (v ?? "").trim();
  return s === "" || GSTIN_RE.test(s);
}

export function isValidPincode(v: string | null | undefined): boolean {
  const s = (v ?? "").trim();
  return s === "" || PINCODE_RE.test(s);
}

/** "27abcde1234f1z5 " → "27ABCDE1234F1Z5" (what the user meant). */
export function normalizeGstin(v: string): string {
  return v.trim().toUpperCase();
}

/** Limit input: "" → invalid, "unlimited" handled by the caller's toggle. */
export function parseLimit(input: string): number | undefined {
  const s = input.trim();
  if (!/^\d{1,9}$/.test(s)) return undefined;
  return Number(s);
}

// --- usage meters -------------------------------------------------------------
export type Meter = {
  unlimited: boolean;
  used: number;
  limit: number | null;
  /** 0..100, clamped; 0 when unlimited */
  percent: number;
  state: "ok" | "warn" | "full";
};

export function usageMeter(u: UsageEntry): Meter {
  const used = Math.max(0, u.used ?? 0);
  if (u.limit === null || u.limit === undefined) {
    return { unlimited: true, used, limit: null, percent: 0, state: "ok" };
  }
  const limit = Math.max(0, u.limit);
  const percent = limit === 0 ? 100 : Math.min(100, Math.round((used / limit) * 100));
  const state = used >= limit ? "full" : percent >= 80 ? "warn" : "ok";
  return { unlimited: false, used, limit, percent, state };
}

// --- dates --------------------------------------------------------------------
const DAY_MS = 86_400_000;

/** Whole days until `iso` (ceil); negative once past; null when no date. */
export function daysUntil(iso: string | null | undefined, now: number = Date.now()): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return Math.ceil((t - now) / DAY_MS);
}

/** ISO datetime → yyyy-mm-dd in India time, for <input type="date">. */
export function isoToDateInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(t));
}

/** yyyy-mm-dd → end of that day in India time (ISO with offset); "" → null. */
export function dateInputToIso(d: string): string | null {
  return /^\d{4}-\d{2}-\d{2}$/.test(d) ? `${d}T23:59:59+05:30` : null;
}

// --- me / nav gating ----------------------------------------------------------
export type NavItem = { key: string; href: string; perm?: string; feature?: string };

/** Features absent (older backend) means "not gated". */
export function hasFeature(me: Me | null, feature: string | undefined): boolean {
  if (!feature) return true;
  if (!me) return false;
  if (!Array.isArray(me.features)) return true;
  return me.features.includes(feature);
}

export function visibleNav<T extends NavItem>(items: T[], me: Me | null): T[] {
  return items.filter(
    (i) => (!i.perm || (!!me && me.permissions.includes(i.perm))) && hasFeature(me, i.feature),
  );
}

export const MFA_SETUP_PATH = "/settings/security";

/**
 * Where a member who must enrol MFA is sent: every page except the security
 * settings page redirects there (with ?mfa=required for the explanation).
 */
export function mfaRedirectTarget(me: Me | null, pathname: string | null): string | null {
  if (!me?.mfa_enrollment_required) return null;
  const p = pathname || "/";
  if (p === MFA_SETUP_PATH || p.startsWith(`${MFA_SETUP_PATH}/`)) return null;
  return `${MFA_SETUP_PATH}?mfa=required`;
}

export type SubscriptionBanner = "trialing" | "past_due" | "read_only" | "suspended" | "cancelled";

export function subscriptionBanner(me: Me | null): SubscriptionBanner | null {
  const s = me?.subscription_status;
  return s === "trialing" ||
    s === "past_due" ||
    s === "read_only" ||
    s === "suspended" ||
    s === "cancelled"
    ? s
    : null;
}

// --- errors -------------------------------------------------------------------
export function isMfaEnrollmentError(err: unknown): boolean {
  return err instanceof ApiError && err.status === 403 && err.detail === "mfa_enrollment_required";
}

/**
 * The server's own message when it is a string — which covers the M7.1
 * 402 "Subscription is read-only: …", 403 "Feature not included in your
 * plan: …" and 403 "Plan limit reached: …" responses — else the fallback.
 * FastAPI 422 lists are summarised by their first message.
 */
export function serverMessage(err: unknown, fallback: string): string {
  if (!(err instanceof ApiError)) return fallback;
  if (typeof err.detail === "string" && err.detail) return err.detail;
  if (Array.isArray(err.detail)) {
    const first = err.detail[0] as { msg?: unknown; loc?: unknown } | undefined;
    if (first && typeof first.msg === "string") {
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : null;
      return field ? `${String(field)}: ${first.msg}` : first.msg;
    }
  }
  return fallback;
}

/** Content-Disposition filename, else a safe default. */
export function filenameFromDisposition(header: string | null, fallback: string): string {
  if (header) {
    const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
    if (star) {
      try {
        return sanitizeFilename(decodeURIComponent(star[1]), fallback);
      } catch {
        /* fall through */
      }
    }
    const plain = /filename="?([^";]+)"?/i.exec(header);
    if (plain) return sanitizeFilename(plain[1], fallback);
  }
  return fallback;
}

function sanitizeFilename(name: string, fallback: string): string {
  const s = name.replace(/[\\/:*?"<>|\u0000-\u001f]/g, "_").trim();
  return s && s !== "." && s !== ".." ? s : fallback;
}

/** Only allow values from a known list (for selects fed by user/URL input). */
export function oneOf<T extends string>(v: string | null | undefined, list: readonly T[], d: T): T {
  return (list as readonly string[]).includes(v ?? "") ? (v as T) : d;
}
