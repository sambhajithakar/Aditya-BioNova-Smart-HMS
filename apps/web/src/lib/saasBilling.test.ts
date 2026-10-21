import { describe, expect, it } from "vitest";
import { buildCsp } from "./csp";
import { billingDictionaries } from "./i18n-billing";
import {
  CatalogPlan,
  SaasPayment,
  SaasRefund,
  annualSavingPaise,
  canRetry,
  gstOn,
  priceWithGst,
  refundablePaise,
  taxLines,
} from "./saasBilling";

describe("SaaS billing helpers", () => {
  it("rounds GST half-up like the server", () => {
    expect(gstOn(99900, 1800)).toBe(17982);
    expect(gstOn(3, 1800)).toBe(1);
    expect(gstOn(1, 1800)).toBe(0);
    expect(priceWithGst(99900, 1800)).toBe(117882);
    expect(priceWithGst(null, 1800)).toBeNull();
    expect(priceWithGst(0, 1800)).toBeNull();
  });

  it("computes the annual saving only when annual is cheaper", () => {
    const p = { price_monthly_paise: 100000, price_annual_paise: 1000000 } as CatalogPlan;
    expect(annualSavingPaise(p)).toBe(200000);
    expect(annualSavingPaise({ ...p, price_annual_paise: 1300000 })).toBe(0);
    expect(annualSavingPaise({ ...p, price_annual_paise: null })).toBe(0);
  });

  it("renders CGST+SGST or IGST lines", () => {
    expect(taxLines({ type: "intra_state", cgst_bp: 900, sgst_bp: 900, cgst_paise: 8991, sgst_paise: 8991 })).toEqual([
      ["CGST 9%", 8991],
      ["SGST 9%", 8991],
    ]);
    expect(taxLines({ type: "inter_state", igst_bp: 1800, igst_paise: 17982 })).toEqual([["IGST 18%", 17982]]);
  });

  it("subtracts pending and processed refunds, never rejected ones", () => {
    const pay = { id: "p1", amount_paise: 1000, status: "captured" } as SaasPayment;
    const r = (amount_paise: number, status: SaasRefund["status"]) =>
      ({ payment_id: "p1", amount_paise, status }) as SaasRefund;
    expect(refundablePaise(pay, [r(300, "requested"), r(200, "processed"), r(400, "rejected")])).toBe(500);
    expect(refundablePaise({ ...pay, status: "failed" }, [])).toBe(0);
  });

  it("only failed, expired or cancelled orders can be retried", () => {
    expect(canRetry({ status: "failed" } as never)).toBe(true);
    expect(canRetry({ status: "paid" } as never)).toBe(false);
    expect(canRetry({ status: "created" } as never)).toBe(false);
  });

  it("has the same billing keys in every language", () => {
    const keys = Object.keys(billingDictionaries.en).sort();
    expect(Object.keys(billingDictionaries.mr).sort()).toEqual(keys);
    expect(Object.keys(billingDictionaries.hi).sort()).toEqual(keys);
  });
});

describe("CSP Razorpay opt-in", () => {
  it("adds no third-party origin by default", () => {
    expect(buildCsp("n")).not.toContain("razorpay");
  });
  it("allows only Razorpay's checkout frame when enabled", () => {
    const csp = buildCsp("n", false, true);
    expect(csp).toContain("frame-src https://api.razorpay.com https://checkout.razorpay.com");
    expect(csp).toMatch(/script-src 'self' 'nonce-n' 'strict-dynamic';/);
  });
});
