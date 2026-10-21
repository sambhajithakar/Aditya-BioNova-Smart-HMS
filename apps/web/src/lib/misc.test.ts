import { describe, expect, it } from "vitest";
import { buildCsp } from "./csp";
import { safeNext } from "./safe-next";
import { defaultBranchId, hasPermission } from "./me";
import { itemDrugName } from "./print";
import type { Branch, Me, RxItem } from "./api";

const me = (branch_id: string | null, permissions: string[] = []): Me => ({
  user: { id: "u", email: "e", full_name: "Dr A", status: "active" },
  organization: { id: "o", name: "Org", slug: "org", status: "active" },
  membership_id: "m",
  branch_id,
  role: "doctor",
  permissions,
});
const br = (id: string, status = "active"): Branch => ({ id, name: id, code: id, status });

describe("defaultBranchId", () => {
  it("prefers the member's own active branch over branches[0]", () => {
    expect(defaultBranchId(me("b2"), [br("b1"), br("b2")])).toBe("b2");
  });
  it("falls back to the first active branch", () => {
    expect(defaultBranchId(me(null), [br("b0", "inactive"), br("b1")])).toBe("b1");
    expect(defaultBranchId(me("gone"), [br("b1")])).toBe("b1");
  });
});

describe("hasPermission", () => {
  it("gates on the permission list", () => {
    expect(hasPermission(me(null, ["billing.read"]), "billing.read")).toBe(true);
    expect(hasPermission(me(null, ["billing.read"]), "billing.refund")).toBe(false);
    expect(hasPermission(null, "billing.read")).toBe(false);
    expect(hasPermission(null, undefined)).toBe(true);
  });
});

describe("safeNext", () => {
  it("allows only same-site relative paths", () => {
    expect(safeNext("/billing?x=1")).toBe("/billing?x=1");
    expect(safeNext("//evil.example")).toBe("/dashboard");
    expect(safeNext("https://evil.example")).toBe("/dashboard");
    expect(safeNext("/\\evil.example")).toBe("/dashboard");
    expect(safeNext(null)).toBe("/dashboard");
  });
});

describe("buildCsp", () => {
  it("locks scripts to the nonce and forbids framing/plugins in production", () => {
    const csp = buildCsp("abc", false);
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("script-src 'self' 'nonce-abc' 'strict-dynamic'");
    expect(csp).not.toContain("unsafe-eval");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("base-uri 'self'");
    expect(csp).toContain("form-action 'self'");
  });
  it("adds unsafe-eval only for next dev", () => {
    expect(buildCsp("abc", true)).toContain("'unsafe-eval'");
  });
});

describe("print drug names", () => {
  const base: RxItem = {
    id: "i",
    prescription_id: "p",
    drug_id: "d1",
    dose: "500 mg",
    route: "oral",
    frequency: "BD",
    duration_days: 3,
    quantity: "",
    instructions: "",
    seq: 1,
  };
  it("uses the Rx detail names (M7) even when the catalog lacks the drug", () => {
    const n = itemDrugName({ ...base, drug_name: "Crocin", generic_name: "Paracetamol", strength: "500 mg" }, {});
    expect(n.name).toBe("Crocin");
    expect(n.detail).toBe("Paracetamol · 500 mg");
  });
  it("falls back to the catalog for pre-M7 responses", () => {
    const n = itemDrugName(base, { d1: { id: "d1", generic_name: "Amoxicillin", brand_hint: "Mox", drug_class: "" } });
    expect(n).toEqual({ name: "Amoxicillin", detail: "Mox" });
    expect(itemDrugName(base, {}).name).toBe("—");
  });
});
