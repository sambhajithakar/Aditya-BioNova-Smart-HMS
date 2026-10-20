"use client";

/**
 * Software subscription billing (M7.2, tenant view): buy / renew an edition
 * (monthly or annual) or an AI credit pack, pay through Razorpay TEST mode or
 * the local payment simulator, see orders, GST invoices / credit notes, AI
 * credit balance, retry failed payments and request refunds (the vendor
 * approves). Amounts always come from the server.
 */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Messages, fmtDate, fmtDateTime, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { newIdempotencyKey } from "@/lib/idempotency";
import { useLang } from "@/lib/lang";
import { useCan, useMe } from "@/lib/me";
import { formatPaise, serverMessage } from "@/lib/saas";
import {
  BillingCatalog,
  CreditsOut,
  OrderCreated,
  PaymentResult,
  SaasInvoice,
  SaasOrder,
  SaasPayment,
  SaasRefund,
  annualSavingPaise,
  canRetry,
  priceWithGst,
  razorpayCheckout,
  refundablePaise,
  taxLines,
} from "@/lib/saasBilling";

const money = (p: number | null | undefined) => formatPaise(p ?? null) ?? "—";

function BillingBody() {
  const { t } = useLang();
  const can = useCan();
  const me = useMe();
  const pay = can("billing.saas.pay");
  const refundPerm = can("billing.saas.refund_request");
  const { busy, error, notice, setError, setNotice, act } = useAction();
  const [cat, setCat] = useState<BillingCatalog | null>(null);
  const [orders, setOrders] = useState<SaasOrder[]>([]);
  const [invoices, setInvoices] = useState<SaasInvoice[]>([]);
  const [payments, setPayments] = useState<SaasPayment[]>([]);
  const [refunds, setRefunds] = useState<SaasRefund[]>([]);
  const [credits, setCredits] = useState<CreditsOut | null>(null);
  const [cycle, setCycle] = useState<"monthly" | "annual">("monthly");
  const [openInvoice, setOpenInvoice] = useState<SaasInvoice | null>(null);
  const [refundDraft, setRefundDraft] = useState<{ payment: SaasPayment; amount: string; reason: string } | null>(
    null,
  );

  const load = useCallback(async () => {
    try {
      const [c, o, i, p, r, cr] = await Promise.all([
        api.get<BillingCatalog>("/saas/catalog"),
        api.get<SaasOrder[]>("/saas/orders"),
        api.get<SaasInvoice[]>("/saas/invoices"),
        api.get<SaasPayment[]>("/saas/payments"),
        api.get<SaasRefund[]>("/saas/refunds"),
        api.get<CreditsOut>("/saas/credits"),
      ]);
      setCat(c);
      setOrders(o);
      setInvoices(i);
      setPayments(p);
      setRefunds(r);
      setCredits(cr);
    } catch (err) {
      setError(serverMessage(err, t("loadFailed")));
    }
  }, [setError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  /** Complete a payment for an order: simulator in development, Razorpay
   * test checkout in sandbox mode. The server verifies the signature. */
  async function complete(created: OrderCreated, outcome: "success" | "failure" = "success") {
    const { order, checkout } = created;
    let res: PaymentResult;
    if (checkout.mode === "simulator") {
      res = await api.post<PaymentResult>(`/saas/orders/${order.id}/simulate`, { outcome });
    } else {
      const r = await razorpayCheckout(checkout, order.description, {
        name: me?.user.full_name,
        email: me?.user.email,
      });
      res = await api.post<PaymentResult>(`/saas/orders/${order.id}/verify`, {
        provider_payment_id: r.razorpay_payment_id,
        signature: r.razorpay_signature,
      });
    }
    setNotice(res.order.status === "paid" ? t("billPaid") : `${t("billPaymentFailed")}: ${res.order.failure_reason ?? ""}`);
    await load();
  }

  const buy = (body: Record<string, string>, outcome: "success" | "failure" = "success") =>
    act(async () => {
      const created = await api.post<OrderCreated>("/saas/orders", body, newIdempotencyKey());
      await complete(created, outcome);
    });

  const retry = (o: SaasOrder) =>
    act(async () => {
      const created = await api.post<OrderCreated>(`/saas/orders/${o.id}/retry`, {}, newIdempotencyKey());
      await complete(created);
    });

  const submitRefund = () =>
    act(async () => {
      if (!refundDraft) return;
      const paise = Math.round(Number(refundDraft.amount) * 100);
      await api.post<SaasRefund>("/saas/refunds", {
        payment_id: refundDraft.payment.id,
        amount_paise: paise,
        reason: refundDraft.reason,
      });
      setRefundDraft(null);
      setNotice(t("billRefundRequested"));
      await load();
    });

  const simulator = cat?.mode === "simulator";

  return (
    <main className="page">
      <h1 style={{ marginTop: 0 }}>{t("billTitle")}</h1>
      <p className="muted">
        {t("billIntro")} <Link href="/settings/subscription">{t("billSeeSubscription")}</Link>
      </p>
      {cat && (
        <p className="notice" data-testid="billing-mode">
          <strong>{cat.mode === "simulator" ? t("billModeSimulator") : cat.mode === "sandbox" ? t("billModeSandbox") : t("billModeUnavailable")}</strong>{" "}
          — {t("billGstNote").replace("{rate}", String(cat.gst_rate_bp / 100))}
        </p>
      )}
      <Messages error={error} notice={notice} />

      {credits && (
        <section className="card" data-testid="ai-credits">
          <h2 style={{ marginTop: 0 }}>{t("billCredits")}</h2>
          <p>
            {t("billCreditsLine")
              .replace("{period}", credits.period)
              .replace("{allowance}", credits.plan_allowance === null ? "∞" : String(credits.plan_allowance))
              .replace("{purchased}", String(credits.purchased))
              .replace("{used}", String(credits.used))
              .replace("{remaining}", credits.remaining === null ? "∞" : String(credits.remaining))}
          </p>
        </section>
      )}

      {cat && (
        <section className="card" style={{ marginTop: "1rem" }}>
          <h2 style={{ marginTop: 0 }}>{t("billEditions")}</h2>
          <label className="field" style={{ maxWidth: 240 }}>
            {t("billCycle")}
            <select aria-label={t("billCycle")} value={cycle} onChange={(e) => setCycle(e.target.value as "monthly" | "annual")}>
              <option value="monthly">{t("billMonthly")}</option>
              <option value="annual">{t("billAnnual")}</option>
            </select>
          </label>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("billEdition")}</th>
                  <th>{t("billPrice")}</th>
                  <th>{t("billWithGst")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {cat.plans.map((p) => {
                  const base = cycle === "monthly" ? p.price_monthly_paise : p.price_annual_paise;
                  const saving = cycle === "annual" ? annualSavingPaise(p) : 0;
                  return (
                    <tr key={p.code} data-testid={`plan-${p.code}`}>
                      <td>
                        {p.name}
                        {saving > 0 && <div className="muted">{t("billSave").replace("{amount}", money(saving))}</div>}
                      </td>
                      <td>{base ? money(base) : t("billNotPriced")}</td>
                      <td>{base ? money(priceWithGst(base, cat.gst_rate_bp)) : "—"}</td>
                      <td>
                        {pay && base ? (
                          <button
                            type="button"
                            className="primary"
                            disabled={busy}
                            onClick={() => void buy({ kind: "subscription", plan_code: p.code, billing_cycle: cycle })}
                          >
                            {t("billPayNow")}
                          </button>
                        ) : null}
                        {pay && base && simulator ? (
                          <button
                            type="button"
                            className="ghost"
                            disabled={busy}
                            onClick={() =>
                              void buy({ kind: "subscription", plan_code: p.code, billing_cycle: cycle }, "failure")
                            }
                          >
                            {t("billSimulateDecline")}
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <h3>{t("billCreditPacks")}</h3>
          <ul>
            {cat.credit_packs.map((k) => (
              <li key={k.code} data-testid={`pack-${k.code}`}>
                {k.name}: {k.price_paise ? `${money(k.price_paise)} + GST` : t("billNotPriced")}{" "}
                {pay && k.purchasable && (
                  <button
                    type="button"
                    className="ghost"
                    disabled={busy}
                    onClick={() => void buy({ kind: "ai_credits", pack_code: k.code })}
                  >
                    {t("billBuy")}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card" style={{ marginTop: "1rem" }}>
        <h2 style={{ marginTop: 0 }}>{t("billOrders")}</h2>
        {orders.length === 0 ? (
          <p className="muted">{t("billNone")}</p>
        ) : (
          <div className="table-wrap">
            <table data-testid="orders">
              <thead>
                <tr>
                  <th>{t("billDate")}</th>
                  <th>{t("billItem")}</th>
                  <th>{t("billTotal")}</th>
                  <th>{t("billStatus")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id}>
                    <td>{fmtDateTime(o.created_at)}</td>
                    <td>{o.description}</td>
                    <td>{money(o.total_paise)}</td>
                    <td>
                      <span className="badge">{t(`billStatus_${o.status}`)}</span>
                      {o.failure_reason && <div className="muted">{o.failure_reason}</div>}
                    </td>
                    <td>
                      {pay && canRetry(o) && (
                        <button type="button" className="ghost" disabled={busy} onClick={() => void retry(o)}>
                          {t("billRetry")}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card" style={{ marginTop: "1rem" }}>
        <h2 style={{ marginTop: 0 }}>{t("billInvoices")}</h2>
        {invoices.length === 0 ? (
          <p className="muted">{t("billNone")}</p>
        ) : (
          <ul data-testid="invoices">
            {invoices.map((i) => (
              <li key={i.id}>
                <button type="button" className="ghost" onClick={() => setOpenInvoice(i)}>
                  {i.number}
                </button>{" "}
                — {i.kind === "credit_note" ? t("billCreditNote") : t("billInvoice")} · {fmtDate(i.issued_at)} ·{" "}
                {money(i.total_paise)}
              </li>
            ))}
          </ul>
        )}
      </section>

      {openInvoice && (
        <section className="card print-area" style={{ marginTop: "1rem" }} data-testid="invoice-view">
          <h2 style={{ marginTop: 0 }}>
            {openInvoice.kind === "credit_note" ? t("billCreditNote") : t("billTaxInvoice")} {openInvoice.number}
          </h2>
          <p>
            <strong>{openInvoice.seller.name}</strong>
            {openInvoice.seller.gstin ? ` · GSTIN ${openInvoice.seller.gstin}` : ` · ${t("billSellerGstinMissing")}`}
            <br />
            {t("billBilledTo")}: {openInvoice.buyer.name}
            {openInvoice.buyer.gstin ? ` · GSTIN ${openInvoice.buyer.gstin}` : ""}
            <br />
            {openInvoice.buyer.address}
          </p>
          {openInvoice.period_end && (
            <p className="muted">
              {t("billPeriod")}: {fmtDate(openInvoice.period_start)} – {fmtDate(openInvoice.period_end)}
            </p>
          )}
          <table>
            <tbody>
              {openInvoice.lines.map((l, n) => (
                <tr key={n}>
                  <td>
                    {l.description} (SAC {l.sac})
                  </td>
                  <td>{money(l.amount_paise)}</td>
                </tr>
              ))}
              {taxLines(openInvoice.tax_breakdown).map(([label, paise]) => (
                <tr key={label}>
                  <td>{label}</td>
                  <td>{money(paise)}</td>
                </tr>
              ))}
              <tr>
                <th>{t("billTotal")}</th>
                <th>{money(openInvoice.total_paise)}</th>
              </tr>
            </tbody>
          </table>
          <p>
            <button type="button" onClick={() => window.print()}>
              {t("billPrint")}
            </button>{" "}
            <button type="button" className="ghost" onClick={() => setOpenInvoice(null)}>
              {t("billClose")}
            </button>
          </p>
        </section>
      )}

      <section className="card" style={{ marginTop: "1rem" }}>
        <h2 style={{ marginTop: 0 }}>{t("billPayments")}</h2>
        {payments.length === 0 ? (
          <p className="muted">{t("billNone")}</p>
        ) : (
          <ul>
            {payments.map((p) => {
              const left = refundablePaise(p, refunds);
              return (
                <li key={p.id}>
                  {fmtDateTime(p.created_at)} · {money(p.amount_paise)} · {p.status}
                  {p.error ? ` (${p.error})` : ""} · <code>{p.provider_payment_id}</code>{" "}
                  {refundPerm && left > 0 && (
                    <button
                      type="button"
                      className="ghost"
                      onClick={() => setRefundDraft({ payment: p, amount: (left / 100).toFixed(2), reason: "" })}
                    >
                      {t("billRequestRefund")}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {refundDraft && (
          <div className="stack" data-testid="refund-form">
            <label className="field">
              {t("billRefundAmount")}
              <input
                inputMode="decimal"
                value={refundDraft.amount}
                onChange={(e) => setRefundDraft({ ...refundDraft, amount: e.target.value })}
              />
            </label>
            <label className="field">
              {t("billRefundReason")}
              <input value={refundDraft.reason} onChange={(e) => setRefundDraft({ ...refundDraft, reason: e.target.value })} />
            </label>
            <p className="muted">{t("billRefundApprovalNote")}</p>
            <div>
              <button type="button" className="primary" disabled={busy || refundDraft.reason.length < 5} onClick={() => void submitRefund()}>
                {t("billSubmitRefund")}
              </button>{" "}
              <button type="button" className="ghost" onClick={() => setRefundDraft(null)}>
                {t("billClose")}
              </button>
            </div>
          </div>
        )}
        {refunds.length > 0 && (
          <>
            <h3>{t("billRefunds")}</h3>
            <ul>
              {refunds.map((r) => (
                <li key={r.id}>
                  {fmtDate(r.created_at)} · {money(r.amount_paise)} · {t(`billRefund_${r.status}`)} — {r.reason}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
      <p className="muted" style={{ marginTop: "1.5rem" }}>
        {t("billSeparateNote")}
      </p>
    </main>
  );
}

export default function BillingPage() {
  return (
    <AppShell active="saasBilling">
      <BillingBody />
    </AppShell>
  );
}
