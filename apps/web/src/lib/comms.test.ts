import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  ALLOWED_PLACEHOLDERS,
  CONSENT_SOURCES,
  DELIVERY_STATUSES,
  DISALLOWED_PLACEHOLDERS,
  FOLLOWUP_ACTIONS,
  FOLLOWUP_BUCKETS,
  PURPOSES,
  followUpBucket,
  isoDay,
  placeholderProblems,
  placeholdersIn,
  renderTemplate,
  smsSegments,
} from "./comms";
import { baseDictionaries, dictionaries } from "./i18n";
import { aiDictionaries } from "./i18n-ai";
import { commsDictionaries } from "./i18n-comms";
import { saasDictionaries } from "./i18n-saas";

describe("template preview", () => {
  it("fills whitelisted placeholders with synthetic sample values", () => {
    expect(renderTemplate("Hi {patient_first_name}, {clinic_name} at {appointment_time}")).toBe(
      "Hi Asha, Demo Clinic at 10:30 AM",
    );
    expect(renderTemplate("Hi { patient_first_name }", { patient_first_name: "Ravi" })).toBe("Hi Ravi");
  });

  it("leaves non-whitelisted placeholders visible instead of filling them", () => {
    expect(renderTemplate("Your {diagnosis} for {patient_first_name}")).toBe("Your {diagnosis} for Asha");
  });

  it("flags clinical, unknown and unbalanced placeholders", () => {
    expect(placeholderProblems("Hello {patient_first_name}")).toEqual([]);
    expect(placeholderProblems("About {diagnosis} and {Medicines}")).toEqual([
      { kind: "disallowed", name: "diagnosis" },
      { kind: "disallowed", name: "Medicines" },
    ]);
    expect(placeholderProblems("Hi {nickname}")).toEqual([{ kind: "unknown", name: "nickname" }]);
    expect(placeholderProblems("Hi {patient_first_name")).toEqual([{ kind: "braces" }]);
    expect(placeholdersIn("{a} {b} {a}")).toEqual(["a", "b", "a"]);
  });

  it("counts SMS parts (GSM 160 / Unicode 70)", () => {
    expect(smsSegments("")).toBe(0);
    expect(smsSegments("a".repeat(160))).toBe(1);
    expect(smsSegments("a".repeat(161))).toBe(2);
    expect(smsSegments("न".repeat(70))).toBe(1);
    expect(smsSegments("न".repeat(71))).toBe(2);
  });

  it("mirrors the server's placeholder rules exactly", () => {
    const py = readFileSync(join(__dirname, "../../../api/app/comms/templates.py"), "utf8");
    const allowedBlock = py.split("ALLOWED_PLACEHOLDERS: dict[str, str] = {")[1].split("}")[0];
    const allowed = [...allowedBlock.matchAll(/"(\w+)":/g)].map((m) => m[1]);
    expect([...ALLOWED_PLACEHOLDERS].sort()).toEqual(allowed.sort());
    const disBlock = py.split("DISALLOWED_PLACEHOLDERS = (")[1].split(")")[0];
    const disallowed = [...disBlock.matchAll(/"(\w+)"/g)].map((m) => m[1]);
    expect([...DISALLOWED_PLACEHOLDERS].sort()).toEqual(disallowed.sort());
  });
});

describe("follow-up worklist", () => {
  it("buckets by due date relative to today", () => {
    expect(followUpBucket("2026-01-10", "planned", "2026-01-10")).toBe("due_today");
    expect(followUpBucket("2026-01-09", "reminded", "2026-01-10")).toBe("overdue");
    expect(followUpBucket("2026-01-11", "booked", "2026-01-10")).toBe("upcoming");
    expect(followUpBucket("2026-01-01", "completed", "2026-01-10")).toBe("closed");
    expect(followUpBucket("2026-01-01", "cancelled", "2026-01-10")).toBe("closed");
  });

  it("offers no actions on closed follow-ups", () => {
    expect(FOLLOWUP_ACTIONS.completed).toEqual([]);
    expect(FOLLOWUP_ACTIONS.cancelled).toEqual([]);
    expect(FOLLOWUP_ACTIONS.booked).not.toContain("book");
  });

  it("formats local calendar days", () => {
    expect(isoDay(new Date(2026, 0, 5))).toBe("2026-01-05");
  });
});

describe("comms i18n", () => {
  it("has identical key sets in EN / मराठी / हिंदी", () => {
    const en = Object.keys(commsDictionaries.en).sort();
    expect(Object.keys(commsDictionaries.mr).sort()).toEqual(en);
    expect(Object.keys(commsDictionaries.hi).sort()).toEqual(en);
  });

  it("does not collide with existing keys", () => {
    const keys = Object.keys(commsDictionaries.en);
    for (const other of [baseDictionaries.en, saasDictionaries.en, aiDictionaries.en]) {
      expect(keys.filter((k) => k in other)).toEqual([]);
    }
  });

  it("covers every dynamic key family", () => {
    const d = dictionaries.en;
    for (const s of [...DELIVERY_STATUSES, "duplicate"]) expect(d).toHaveProperty(`dstatus_${s}`);
    for (const p of PURPOSES) expect(d).toHaveProperty(`purpose_${p}`);
    for (const s of CONSENT_SOURCES) expect(d).toHaveProperty(`consentSrc_${s}`);
    for (const b of FOLLOWUP_BUCKETS) expect(d).toHaveProperty(`fuBucket_${b}`);
    for (const s of Object.keys(FOLLOWUP_ACTIONS)) expect(d).toHaveProperty(`fuStatus_${s}`);
    for (const c of ["sms", "whatsapp", "email"]) expect(d).toHaveProperty(`channel_${c}`);
  });
});
