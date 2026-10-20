import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import type { Me } from "./api";
import { NAV } from "./nav";
import { baseDictionaries, dictionaries } from "./i18n";
import { saasDictionaries } from "./i18n-saas";
import {
  FEATURE_KEYS,
  LIMIT_KEYS,
  MFA_POLICY_ROLES,
  ONBOARDING_STEPS,
  SUBSCRIPTION_STATUSES,
  TICKET_CATEGORIES,
  TICKET_PRIORITIES,
  TICKET_STATUSES,
  dateInputToIso,
  daysUntil,
  filenameFromDisposition,
  formatPaise,
  hasFeature,
  isMfaEnrollmentError,
  isValidGstin,
  isValidPincode,
  isoToDateInput,
  mfaRedirectTarget,
  normalizeGstin,
  paiseToRupeesInput,
  parseLimit,
  parseRupeesToPaise,
  serverMessage,
  subscriptionBanner,
  usageMeter,
  visibleNav,
} from "./saas";

const ALL_PERMS = [
  "patient.read",
  "appointment.read",
  "queue.read",
  "encounter.read",
  "billing.read",
  "pharmacy.read",
  "lab.read",
  "bed.read",
  "inventory.read",
  "expense.read",
  "report.read",
  "member.read",
  "org.read",
  "branch.read",
  "subscription.read",
  "support.read",
  "audit.read",
  "org.offboard",
];

const me = (over: Partial<Me> = {}): Me => ({
  user: { id: "u", email: "e", full_name: "Dr A", status: "active" },
  organization: { id: "o", name: "Org", slug: "org", status: "active" },
  membership_id: "m",
  branch_id: null,
  role: "owner",
  permissions: ALL_PERMS,
  ...over,
});

describe("money (paise ↔ ₹)", () => {
  it("formats integer paise as Indian rupees", () => {
    expect(formatPaise(149900)).toBe("₹1,499");
    expect(formatPaise(0)).toBe("₹0");
    expect(formatPaise(149950)).toBe("₹1,499.50");
    expect(formatPaise(149905)).toBe("₹1,499.05");
    expect(formatPaise(12345600)).toBe("₹1,23,456"); // lakh grouping
  });
  it("null / undefined price is 'not configured'", () => {
    expect(formatPaise(null)).toBeNull();
    expect(formatPaise(undefined)).toBeNull();
  });
  it("parses rupee input to paise without float error", () => {
    expect(parseRupeesToPaise("1499")).toEqual({ ok: true, paise: 149900 });
    expect(parseRupeesToPaise("1499.5")).toEqual({ ok: true, paise: 149950 });
    expect(parseRupeesToPaise("0.29")).toEqual({ ok: true, paise: 29 });
    expect(parseRupeesToPaise("₹ 1,23,456.78")).toEqual({ ok: true, paise: 12345678 });
    expect(parseRupeesToPaise("  ")).toEqual({ ok: true, paise: null });
  });
  it("rejects malformed amounts", () => {
    for (const bad of ["-1", "1.234", "abc", "1e3", "12.", "1 499"]) {
      expect(parseRupeesToPaise(bad).ok, bad).toBe(false);
    }
  });
  it("round-trips paise to the editable rupee string", () => {
    expect(paiseToRupeesInput(149900)).toBe("1499");
    expect(paiseToRupeesInput(149905)).toBe("1499.05");
    expect(paiseToRupeesInput(null)).toBe("");
    for (const p of [0, 1, 99, 100, 149950, 99999999]) {
      expect(parseRupeesToPaise(paiseToRupeesInput(p))).toEqual({ ok: true, paise: p });
    }
  });
});

describe("GSTIN / PIN code validation (contract regexes)", () => {
  it("accepts well-formed GSTINs and empty", () => {
    expect(isValidGstin("27ABCDE1234F1Z5")).toBe(true);
    expect(isValidGstin("29AAACB1234C1ZV")).toBe(true);
    expect(isValidGstin("")).toBe(true);
    expect(isValidGstin(null)).toBe(true);
  });
  it("rejects malformed GSTINs", () => {
    for (const bad of [
      "27ABCDE1234F1Z", // 14 chars
      "27abcde1234f1z5", // lower case (normalise first)
      "27ABCDE1234F0Z5", // entity code 0
      "27ABCDE1234F1X5", // 14th must be Z
      "A7ABCDE1234F1Z5",
    ]) {
      expect(isValidGstin(bad), bad).toBe(false);
    }
    expect(isValidGstin(normalizeGstin(" 27abcde1234f1z5 "))).toBe(true);
  });
  it("PIN code: 6 digits, not starting with 0", () => {
    expect(isValidPincode("411038")).toBe(true);
    expect(isValidPincode("")).toBe(true);
    expect(isValidPincode("011038")).toBe(false);
    expect(isValidPincode("41103")).toBe(false);
    expect(isValidPincode("4110381")).toBe(false);
    expect(isValidPincode("41103a")).toBe(false);
  });
  it("limit inputs are whole non-negative numbers", () => {
    expect(parseLimit("0")).toBe(0);
    expect(parseLimit(" 25 ")).toBe(25);
    expect(parseLimit("")).toBeUndefined();
    expect(parseLimit("-1")).toBeUndefined();
    expect(parseLimit("2.5")).toBeUndefined();
  });
});

describe("usage meter", () => {
  it("unlimited when limit is null", () => {
    expect(usageMeter({ limit: null, used: 12 })).toEqual({
      unlimited: true,
      used: 12,
      limit: null,
      percent: 0,
      state: "ok",
    });
  });
  it("percent and state thresholds", () => {
    expect(usageMeter({ limit: 10, used: 3 })).toMatchObject({ percent: 30, state: "ok" });
    expect(usageMeter({ limit: 10, used: 8 })).toMatchObject({ percent: 80, state: "warn" });
    expect(usageMeter({ limit: 10, used: 10 })).toMatchObject({ percent: 100, state: "full" });
    expect(usageMeter({ limit: 10, used: 14 })).toMatchObject({ percent: 100, state: "full" });
    expect(usageMeter({ limit: 0, used: 0 })).toMatchObject({ percent: 100, state: "full" });
  });
});

describe("feature-gated navigation", () => {
  const ruralFeatures = [
    "patients",
    "appointments",
    "opd_queue",
    "consultation",
    "billing",
    "reports_basic",
  ];

  it("hides Pharmacy, Lab, IPD, Inventory, Expenses for a rural_clinic edition", () => {
    const keys = visibleNav(NAV, me({ features: ruralFeatures })).map((n) => n.key);
    expect(keys).toContain("billing");
    expect(keys).toContain("queue");
    for (const hidden of ["pharmacy", "lab", "ipd", "inventory", "expenses"]) {
      expect(keys).not.toContain(hidden);
    }
    // settings entries are permission-gated only
    expect(keys).toEqual(expect.arrayContaining(["members", "organization", "subscription", "security"]));
  });

  it("still applies permissions on top of features", () => {
    const keys = visibleNav(NAV, me({ permissions: ["patient.read"], features: [...FEATURE_KEYS] })).map(
      (n) => n.key,
    );
    expect(keys).toEqual(["dashboard", "patients", "security"]);
  });

  it("maps every gated module to the contract feature key", () => {
    const map = Object.fromEntries(NAV.filter((n) => n.feature).map((n) => [n.key, n.feature]));
    expect(map).toEqual({
      appointments: "appointments",
      queue: "opd_queue",
      consultation: "consultation",
      billing: "billing",
      pharmacy: "pharmacy",
      lab: "laboratory",
      ipd: "ipd",
      inventory: "inventory",
      expenses: "expenses",
      reports: "reports_basic",
      copilot: "ai_copilot",
    });
    for (const f of Object.values(map)) expect(FEATURE_KEYS).toContain(f);
  });

  it("older payloads without `features` are not gated; no member means nothing gated passes", () => {
    expect(hasFeature(me(), "pharmacy")).toBe(true);
    expect(hasFeature(null, "pharmacy")).toBe(false);
    expect(hasFeature(null, undefined)).toBe(true);
  });
});

describe("MFA-enrolment redirect", () => {
  it("sends every page except /settings/security to the security page", () => {
    const m = me({ mfa_enrollment_required: true });
    expect(mfaRedirectTarget(m, "/dashboard")).toBe("/settings/security?mfa=required");
    expect(mfaRedirectTarget(m, "/platform/plans")).toBe("/settings/security?mfa=required");
    expect(mfaRedirectTarget(m, null)).toBe("/settings/security?mfa=required");
    expect(mfaRedirectTarget(m, "/settings/security")).toBeNull();
  });
  it("no redirect when enrolment is not required", () => {
    expect(mfaRedirectTarget(me({ mfa_enrollment_required: false }), "/dashboard")).toBeNull();
    expect(mfaRedirectTarget(me(), "/dashboard")).toBeNull();
    expect(mfaRedirectTarget(null, "/dashboard")).toBeNull();
  });
  it("recognises the API's 403 mfa_enrollment_required", () => {
    expect(isMfaEnrollmentError(new ApiError(403, "mfa_enrollment_required"))).toBe(true);
    expect(isMfaEnrollmentError(new ApiError(403, "Feature not included in your plan: pharmacy"))).toBe(
      false,
    );
    expect(isMfaEnrollmentError(new Error("x"))).toBe(false);
  });
});

describe("subscription banner + server messages", () => {
  it("banner only for trial / past_due / read_only / suspended / cancelled", () => {
    expect(subscriptionBanner(me({ subscription_status: "active" }))).toBeNull();
    expect(subscriptionBanner(me())).toBeNull();
    for (const s of ["trialing", "past_due", "read_only", "suspended", "cancelled"] as const) {
      expect(subscriptionBanner(me({ subscription_status: s }))).toBe(s);
    }
  });
  it("shows the server's 402 / 403 strings verbatim", () => {
    const ro = new ApiError(402, "Subscription is read-only: trial expired");
    const feat = new ApiError(403, "Feature not included in your plan: pharmacy");
    const lim = new ApiError(403, "Plan limit reached: max_branches (1). Upgrade your plan.");
    expect(serverMessage(ro, "x")).toBe("Subscription is read-only: trial expired");
    expect(serverMessage(feat, "x")).toBe("Feature not included in your plan: pharmacy");
    expect(serverMessage(lim, "x")).toBe("Plan limit reached: max_branches (1). Upgrade your plan.");
    expect(serverMessage(new ApiError(422, [{ loc: ["body", "gstin"], msg: "bad" }]), "x")).toBe(
      "gstin: bad",
    );
    expect(serverMessage(new ApiError(500, { a: 1 }), "fallback")).toBe("fallback");
    expect(serverMessage(new TypeError("net"), "fallback")).toBe("fallback");
  });
});

describe("dates + download names", () => {
  it("days until a timestamp (ceil, negative once past)", () => {
    const now = Date.parse("2026-10-20T10:00:00Z");
    expect(daysUntil("2026-10-27T10:00:00Z", now)).toBe(7);
    expect(daysUntil("2026-10-20T11:00:00Z", now)).toBe(1);
    expect(daysUntil("2026-10-19T10:00:00Z", now)).toBe(-1);
    expect(daysUntil(null, now)).toBeNull();
    expect(daysUntil("nope", now)).toBeNull();
  });
  it("date inputs are India-time calendar days", () => {
    expect(isoToDateInput("2026-10-20T20:00:00Z")).toBe("2026-10-21"); // 01:30 IST next day
    expect(dateInputToIso("2026-11-30")).toBe("2026-11-30T23:59:59+05:30");
    expect(dateInputToIso("")).toBeNull();
    expect(isoToDateInput(dateInputToIso("2026-11-30"))).toBe("2026-11-30");
  });
  it("takes the server filename but strips path characters", () => {
    expect(filenameFromDisposition('attachment; filename="sunrise-export.zip"', "f.zip")).toBe(
      "sunrise-export.zip",
    );
    expect(filenameFromDisposition("attachment; filename*=UTF-8''a%2F..%2Fb.zip", "f.zip")).toBe(
      "a_.._b.zip",
    );
    expect(filenameFromDisposition(null, "f.zip")).toBe("f.zip");
    expect(filenameFromDisposition('attachment; filename=".."', "f.zip")).toBe("f.zip");
  });
});

describe("M7.1 i18n", () => {
  it("EN / मराठी / हिंदी additions have identical key sets", () => {
    const en = Object.keys(saasDictionaries.en).sort();
    expect(Object.keys(saasDictionaries.mr).sort()).toEqual(en);
    expect(Object.keys(saasDictionaries.hi).sort()).toEqual(en);
  });
  it("additions never silently override an existing key", () => {
    const clash = Object.keys(saasDictionaries.en).filter((k) => k in baseDictionaries.en);
    expect(clash).toEqual([]);
  });
  it("dynamic key families are complete", () => {
    const d = dictionaries.en;
    for (const k of FEATURE_KEYS) expect(d).toHaveProperty(`feature_${k}`);
    for (const k of LIMIT_KEYS) expect(d).toHaveProperty(`limit_${k}`);
    for (const k of SUBSCRIPTION_STATUSES) expect(d).toHaveProperty(`subStatus_${k}`);
    for (const k of TICKET_CATEGORIES) expect(d).toHaveProperty(`ticketCat_${k}`);
    for (const k of TICKET_PRIORITIES) expect(d).toHaveProperty(`ticketPri_${k}`);
    for (const k of TICKET_STATUSES) expect(d).toHaveProperty(`ticketStatus_${k}`);
    for (const k of MFA_POLICY_ROLES) expect(d).toHaveProperty(`role_${k}`);
    for (const s of ONBOARDING_STEPS) expect(d).toHaveProperty(`step_${s.key}`);
    for (const n of NAV) expect(d).toHaveProperty(n.label ?? n.key);
    for (const c of ["monthly", "annual"]) expect(d).toHaveProperty(`cycle_${c}`);
    for (const s of ["customer", "vendor"]) expect(d).toHaveProperty(`side_${s}`);
  });
});
