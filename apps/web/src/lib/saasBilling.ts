/**
 * SaaS subscription billing (M7.2) — types for /saas/* and pure helpers.
 * This is the clinic paying the vendor for the software; patient billing is
 * a different module (/billing) and never mixes with these records.
 */
export type BillingMode = "sandbox" | "simulator" | "unavailable";

export type CatalogPlan = {
  code: string;
  name: string;
  tier: number;
  price_monthly_paise: number | null;
  price_annual_paise: number | null;
  purchasable: boolean;
};

export type CatalogPack = {
  code: string;
  name: string;
  credits: number;
  price_paise: number | null;
  purchasable: boolean;
};

export type BillingCatalog = {
  provider: string;
  mode: BillingMode;
  gst_rate_bp: number;
  currency: string;
  plans: CatalogPlan[];
  credit_packs: CatalogPack[];
  notice: string;
};

export type SaasOrder = {
  id: string;
  kind: "subscription" | "ai_credits";
  description: string;
  billing_cycle: "monthly" | "annual" | null;
  credits: number | null;
  amount_paise: number;
  tax_paise: number;
  total_paise: number;
  currency: string;
  provider: string;
  provider_order_id: string;
  status: "created" | "paid" | "failed" | "expired" | "cancelled";
  failure_reason: string | null;
  created_at: string;
  paid_at: string | null;
};

export type CheckoutParams = {
  provider: string;
  mode: BillingMode;
  key_id: string;
  provider_order_id: string;
  amount: number;
  currency: string;
};

export type OrderCreated = { order: SaasOrder; checkout: CheckoutParams };
export type PaymentResult = { outcome: string; order: SaasOrder };

export type SaasPayment = {
  id: string;
  order_id: string;
  provider_payment_id: string;
  amount_paise: number;
  status: "captured" | "failed";
  method: string | null;
  source: string;
  error: string | null;
  created_at: string;
};

export type TaxBreakdown =
  | { type: "intra_state"; cgst_bp: number; sgst_bp: number; cgst_paise: number; sgst_paise: number }
  | { type: "inter_state"; igst_bp: number; igst_paise: number };

export type SaasInvoice = {
  id: string;
  number: string;
  kind: "invoice" | "credit_note";
  order_id: string;
  related_invoice_id: string | null;
  issued_at: string;
  period_start: string | null;
  period_end: string | null;
  seller: { name: string; gstin: string | null; state: string; address: string };
  buyer: { name: string; gstin: string | null; state: string | null; address: string };
  lines: { description: string; sac: string; quantity: number; amount_paise: number }[];
  subtotal_paise: number;
  tax_breakdown: TaxBreakdown;
  tax_paise: number;
  total_paise: number;
  currency: string;
};

export type SaasRefund = {
  id: string;
  organization_id: string;
  payment_id: string;
  amount_paise: number;
  reason: string;
  status: "requested" | "rejected" | "processed" | "failed";
  requested_by: string | null;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
  provider_refund_id: string | null;
  error: string | null;
  created_at: string;
};

export type CreditsOut = {
  period: string;
  plan_allowance: number | null;
  purchased: number;
  used: number;
  remaining: number | null;
};

export type ReconciliationIssue = { kind: string } & Record<string, string>;

/** GST in paise, rounded half-up — mirrors the server (display only; the
 * server's amount is always the one charged). */
export function gstOn(amountPaise: number, rateBp: number): number {
  return Math.floor((amountPaise * rateBp + 5000) / 10000);
}

/** Price a plan or pack would cost including GST, or null when not for sale. */
export function priceWithGst(paise: number | null, rateBp: number): number | null {
  if (!paise) return null;
  return paise + gstOn(paise, rateBp);
}

/** Annual saving vs paying monthly for 12 months (0 when not cheaper). */
export function annualSavingPaise(plan: CatalogPlan): number {
  if (!plan.price_monthly_paise || !plan.price_annual_paise) return 0;
  return Math.max(0, plan.price_monthly_paise * 12 - plan.price_annual_paise);
}

/** Human tax lines for an invoice: [label, paise][] */
export function taxLines(tb: TaxBreakdown): [string, number][] {
  if (tb.type === "intra_state") {
    return [
      [`CGST ${tb.cgst_bp / 100}%`, tb.cgst_paise],
      [`SGST ${tb.sgst_bp / 100}%`, tb.sgst_paise],
    ];
  }
  return [[`IGST ${tb.igst_bp / 100}%`, tb.igst_paise]];
}

/** Paise still refundable on a captured payment given existing refund rows. */
export function refundablePaise(payment: SaasPayment, refunds: SaasRefund[]): number {
  const taken = refunds
    .filter((r) => r.payment_id === payment.id && (r.status === "requested" || r.status === "processed"))
    .reduce((s, r) => s + r.amount_paise, 0);
  return payment.status === "captured" ? Math.max(0, payment.amount_paise - taken) : 0;
}

export function canRetry(order: SaasOrder): boolean {
  return order.status === "failed" || order.status === "expired" || order.status === "cancelled";
}

// --- Razorpay test-mode hosted checkout -------------------------------------------
type RazorpayResponse = {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
};
type RazorpayCtor = new (opts: Record<string, unknown>) => {
  open: () => void;
  on: (ev: string, cb: (e: unknown) => void) => void;
};

const CHECKOUT_SRC = "https://checkout.razorpay.com/v1/checkout.js";

/** Load Razorpay's checkout script once (only in sandbox mode; the deployment
 * must set RAZORPAY_CHECKOUT=1 so the CSP allows its payment frame). */
export function loadRazorpay(): Promise<RazorpayCtor> {
  const w = window as unknown as { Razorpay?: RazorpayCtor };
  if (w.Razorpay) return Promise.resolve(w.Razorpay);
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = CHECKOUT_SRC;
    s.async = true;
    s.onload = () => (w.Razorpay ? resolve(w.Razorpay) : reject(new Error("Razorpay unavailable")));
    s.onerror = () => reject(new Error("Could not load Razorpay checkout"));
    document.head.appendChild(s);
  });
}

/** Open the test-mode checkout; resolves with the signed response the server
 * must verify (the browser never decides that a payment succeeded). */
export async function razorpayCheckout(
  c: CheckoutParams,
  description: string,
  prefill: { name?: string; email?: string },
): Promise<RazorpayResponse> {
  const Razorpay = await loadRazorpay();
  return new Promise((resolve, reject) => {
    const rz = new Razorpay({
      key: c.key_id,
      order_id: c.provider_order_id,
      amount: c.amount,
      currency: c.currency,
      name: "Aditya BioNova Smart HMS",
      description,
      prefill,
      handler: (r: RazorpayResponse) => resolve(r),
      modal: { ondismiss: () => reject(new Error("dismissed")) },
    });
    rz.on("payment.failed", () => reject(new Error("failed")));
    rz.open();
  });
}
