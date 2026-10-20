"use client";

/**
 * Billing desk (M3): draft invoices with server-computed totals, issue,
 * take payments (manual or sandbox gateway), refund, and open the
 * printable receipt. Illegal transitions surface the API's 409s verbatim.
 */
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { PatientPicker } from "@/components/PatientPicker";
import {
  ApiError,
  Branch,
  Invoice,
  InvoiceDetail,
  PageOf,
  Patient,
  Payment,
  Receipt,
  Refund,
  api,
} from "@/lib/api";
import { defaultBranchId, useCan, useMe } from "@/lib/me";
import { useIdempotencyKey, useInFlight } from "@/lib/idempotency";
import { t } from "@/lib/i18n";
import { useLang } from "@/lib/lang";
import { NeedsConnection, useOnline } from "@/components/device/online";

type Line = {
  item_type: string;
  description: string;
  quantity: number;
  unit_price: number;
  tax_rate: number;
};

const EMPTY_LINE: Line = {
  item_type: "consultation",
  description: "",
  quantity: 1,
  unit_price: 0,
  tax_rate: 0,
};

export default function BillingPage() {
  return (
    <AppShell active="billing">
      <Billing />
    </AppShell>
  );
}

function Billing() {
  const { lang } = useLang();
  const me = useMe();
  const can = useCan();
  const online = useOnline(); // payments / refunds are server-finalised: never offline
  const { busy, run } = useInFlight();
  const payKey = useIdempotencyKey();
  const [refundFor, setRefundFor] = useState<Payment | null>(null);
  const [refundAmount, setRefundAmount] = useState("");
  const [refundReason, setRefundReason] = useState("");
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [selected, setSelected] = useState<InvoiceDetail | null>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [patientId, setPatientId] = useState("");
  const [discount, setDiscount] = useState("0");
  const [lines, setLines] = useState<Line[]>([{ ...EMPTY_LINE }]);
  const [payAmount, setPayAmount] = useState("");
  const [payMethod, setPayMethod] = useState("cash");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);


  const load = useCallback(async () => {
    try {
      const [invPage, patientPage, branchList] = await Promise.all([
        api.get<PageOf<Invoice>>("/billing/invoices?limit=50"),
        api.get<PageOf<Patient>>("/patients?limit=100"), // labels only; picking uses server search
        api.get<Branch[]>("/branches"),
      ]);
      setInvoices(invPage.items);
      setPatients(patientPage.items);
      setBranches(branchList.filter((b) => b.status === "active"));
    } catch {
      setError(t("loadFailed", lang));
    }
  }, [lang]);

  useEffect(() => {
    void load();
  }, [load]);

  async function openInvoice(id: string) {
    setError(null);
    setReceipt(null);
    try {
      const detail = await api.get<InvoiceDetail>(`/billing/invoices/${id}`);
      setSelected(detail);
      setPayAmount(Math.max(0, Number(detail.total) - Number(detail.amount_paid)).toFixed(2));
      payKey.reset(); // a different invoice is a new payment attempt
    } catch (err) {
      setError(err instanceof ApiError ? String(err.message) : "Load failed");
    }
  }

  async function createInvoice() {
    if (!patientId) return setError(t("pickPatientFirst", lang));
    const items = lines
      .filter((l) => l.description.trim())
      .map((l) => ({
        item_type: l.item_type,
        description: l.description,
        quantity: Number(l.quantity) || 1,
        unit_price: Number(l.unit_price) || 0,
        tax_rate: Number(l.tax_rate) || 0,
      }));
    if (items.length === 0) return setError(t("addOneLine", lang));
    setError(null);
    await run(async () => {
    try {
      const inv = await api.post<Invoice>("/billing/invoices", {
        patient_id: patientId,
        branch_id: defaultBranchId(me, branches),
        discount: Number(discount) || 0,
        items,
      });
      setLines([{ ...EMPTY_LINE }]);
      setDiscount("0");
      setNotice(`${t("invoice", lang)} ${inv.invoice_number}`);
      await load();
      await openInvoice(inv.id);
    } catch (err) {
      setError(err instanceof ApiError ? String(err.message) : t("actionFailed", lang));
    }
    });
  }

  async function act(path: string, body: unknown = {}) {
    setError(null);
    await run(async () => {
      try {
        await api.post(`/billing${path}`, body);
        await load();
        if (selected) await openInvoice(selected.id);
      } catch (err) {
        setError(err instanceof ApiError ? String(err.message) : t("actionFailed", lang));
      }
    });
  }

  async function takePayment(gateway: "manual" | "sandbox") {
    if (!selected) return;
    const amount = Number(payAmount);
    if (!Number.isFinite(amount) || amount <= 0) return setError(t("checkInput", lang));
    setError(null);
    await run(async () => {
      try {
        // H13: one random key per payment attempt (manual cash/UPI/card too),
        // kept across retries of the same attempt, retired on success.
        await payKey.run((key) =>
          api.post(
            `/billing/invoices/${selected.id}/payments`,
            { amount, method: payMethod, gateway },
            key,
          ),
        );
        setNotice(t("paymentRecorded", lang));
        await load();
        await openInvoice(selected.id);
      } catch (err) {
        setError(err instanceof ApiError ? String(err.message) : t("actionFailed", lang));
      }
    });
  }

  async function submitRefund() {
    if (!selected || !refundFor) return;
    const amount = Number(refundAmount);
    if (!Number.isFinite(amount) || amount <= 0 || refundReason.trim().length < 3) {
      return setError(t("refundInvalid", lang));
    }
    setError(null);
    await run(async () => {
      try {
        await api.post<Refund>(`/billing/payments/${refundFor.id}/refund`, {
          amount,
          reason: refundReason.trim(),
        });
        setNotice(t("refundRecorded", lang));
        setRefundFor(null);
        setRefundAmount("");
        setRefundReason("");
        await load();
        await openInvoice(selected.id);
      } catch (err) {
        setError(err instanceof ApiError ? String(err.message) : t("actionFailed", lang));
      }
    });
  }

  async function confirmSandbox(paymentId: string) {
    await act(`/payments/${paymentId}/confirm`);
  }

  async function loadReceipt() {
    if (!selected) return;
    setError(null);
    try {
      setReceipt(await api.get<Receipt>(`/billing/invoices/${selected.id}/receipt`));
    } catch (err) {
      setError(err instanceof ApiError ? String(err.message) : "Receipt failed");
    }
  }

  const patientName = (id: string) => {
    const p = patients.find((x) => x.id === id);
    return p ? `${p.uhid} — ${p.full_name}` : id.slice(0, 8);
  };

  const lineTotal = (l: Line) =>
    (Number(l.quantity) || 0) * (Number(l.unit_price) || 0) *
    (1 + (Number(l.tax_rate) || 0) / 100);

  return (
      <main className="page">
        <h1 style={{ marginTop: 0 }}>{t("billing", lang)}</h1>

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {notice && <p className="notice">{notice}</p>}

        <section className="card">
          <h3 style={{ marginTop: 0 }}>{t("newInvoice", lang)}</h3>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            <PatientPicker id="bi-p" value={patientId} onChange={(id) => setPatientId(id)} />
            <div className="field">
              <label htmlFor="bi-disc">{t("discount", lang)}</label>
              <input
                id="bi-disc"
                inputMode="decimal"
                value={discount}
                onChange={(e) => setDiscount(e.target.value)}
              />
            </div>
          </div>

          <table style={{ marginTop: "0.75rem" }}>
            <thead>
              <tr>
                <th>{t("itemType", lang)}</th>
                <th>{t("itemDescription", lang)}</th>
                <th>{t("qty", lang)}</th>
                <th>{t("unitPrice", lang)}</th>
                <th>{t("taxRate", lang)}</th>
                <th>{t("total", lang)}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {lines.map((l, idx) => (
                <tr key={idx}>
                  <td>
                    <select
                      value={l.item_type}
                      onChange={(e) =>
                        setLines((xs) =>
                          xs.map((x, i) =>
                            i === idx ? { ...x, item_type: e.target.value } : x
                          )
                        )
                      }
                    >
                      {["consultation", "procedure", "pharmacy", "lab", "other"].map(
                        (ty) => (
                          <option key={ty} value={ty}>
                            {t(`itemType_${ty}`, lang)}
                          </option>
                        )
                      )}
                    </select>
                  </td>
                  <td>
                    <input
                      value={l.description}
                      onChange={(e) =>
                        setLines((xs) =>
                          xs.map((x, i) =>
                            i === idx ? { ...x, description: e.target.value } : x
                          )
                        )
                      }
                    />
                  </td>
                  <td style={{ width: "4rem" }}>
                    <input
                      inputMode="numeric"
                      value={l.quantity}
                      onChange={(e) =>
                        setLines((xs) =>
                          xs.map((x, i) =>
                            i === idx
                              ? { ...x, quantity: Number(e.target.value) }
                              : x
                          )
                        )
                      }
                    />
                  </td>
                  <td style={{ width: "6rem" }}>
                    <input
                      inputMode="decimal"
                      value={l.unit_price}
                      onChange={(e) =>
                        setLines((xs) =>
                          xs.map((x, i) =>
                            i === idx
                              ? { ...x, unit_price: Number(e.target.value) }
                              : x
                          )
                        )
                      }
                    />
                  </td>
                  <td style={{ width: "4rem" }}>
                    <input
                      inputMode="decimal"
                      value={l.tax_rate}
                      onChange={(e) =>
                        setLines((xs) =>
                          xs.map((x, i) =>
                            i === idx ? { ...x, tax_rate: Number(e.target.value) } : x
                          )
                        )
                      }
                    />
                  </td>
                  <td>{lineTotal(l).toFixed(2)}</td>
                  <td>
                    <button
                      type="button"
                      className="icon"
                      aria-label={t("remove", lang)}
                      onClick={() => setLines((xs) => xs.filter((_, i) => i !== idx))}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
            <button
              type="button"
              className="secondary"
              onClick={() => setLines((xs) => [...xs, { ...EMPTY_LINE }])}
            >
              + {t("addItemLine", lang)}
            </button>
            <button
              className="primary"
              type="button"
              disabled={busy || !can("billing.invoice")}
              onClick={() => void createInvoice()}
            >
              {t("newInvoice", lang)}
            </button>
          </div>
        </section>

        <section className="card" style={{ marginTop: "1.25rem" }}>
          <h3 style={{ marginTop: 0 }}>{t("invoice", lang)}</h3>
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>{t("patients", lang)}</th>
                <th>{t("total", lang)}</th>
                <th>{t("amountPaid", lang)}</th>
                <th>{t("status", lang)}</th>
                <th>{t("actions", lang)}</th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((inv) => (
                <tr key={inv.id}>
                  <td>
                    <strong>{inv.invoice_number}</strong>
                  </td>
                  <td>{patientName(inv.patient_id)}</td>
                  <td>{Number(inv.total).toFixed(2)}</td>
                  <td>{Number(inv.amount_paid).toFixed(2)}</td>
                  <td>
                    <span className="tag">{inv.status}</span>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => void openInvoice(inv.id)}
                    >
                      {t("open", lang)}
                    </button>
                    {inv.status === "draft" && can("billing.invoice") && (
                      <button
                        type="button"
                        className="primary"
                        disabled={busy}
                        onClick={() =>
                          void act(`/invoices/${inv.id}/issue`).then(() =>
                            openInvoice(inv.id)
                          )
                        }
                      >
                        {t("issue", lang)}
                      </button>
                    )}
                    {inv.status === "issued" && can("billing.invoice") && (
                      <button
                        type="button"
                        className="danger"
                        disabled={busy}
                        onClick={() =>
                          void act(`/invoices/${inv.id}/void`).then(() =>
                            openInvoice(inv.id)
                          )
                        }
                      >
                        {t("void", lang)}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {invoices.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted">
                    {t("noInvoices", lang)}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </section>

        {selected && (
          <section className="card" style={{ marginTop: "1.25rem" }}>
            <h3 style={{ marginTop: 0 }}>
              {selected.invoice_number}{" "}
              <span className="tag">{selected.status}</span>
            </h3>
            <table>
              <thead>
                <tr>
                  <th>{t("itemDescription", lang)}</th>
                  <th>{t("qty", lang)}</th>
                  <th>{t("unitPrice", lang)}</th>
                  <th>{t("total", lang)}</th>
                </tr>
              </thead>
              <tbody>
                {selected.items.map((it) => (
                  <tr key={it.id}>
                    <td>
                      {it.description} <span className="muted">({it.item_type})</span>
                    </td>
                    <td>{it.quantity}</td>
                    <td>{Number(it.unit_price).toFixed(2)}</td>
                    <td>{Number(it.line_total).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p>
              <strong>{t("total", lang)}:</strong> {Number(selected.total).toFixed(2)}{" "}
              <strong>{t("amountPaid", lang)}:</strong>{" "}
              {Number(selected.amount_paid).toFixed(2)}{" "}
              <strong>{t("balanceDue", lang)}:</strong>{" "}
              {(Number(selected.total) - Number(selected.amount_paid)).toFixed(2)}
            </p>

            <NeedsConnection />
            {selected.status === "issued" &&
              can("billing.payment") && (
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <div className="field">
                  <label htmlFor="pay-amt">{t("amount", lang)}</label>
                  <input
                    id="pay-amt"
                    inputMode="decimal"
                    value={payAmount}
                    onChange={(e) => setPayAmount(e.target.value)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="pay-m">{t("method", lang)}</label>
                  <select
                    id="pay-m"
                    value={payMethod}
                    onChange={(e) => setPayMethod(e.target.value)}
                  >
                    <option value="cash">{t("cash", lang)}</option>
                    <option value="upi">{t("upi", lang)}</option>
                    <option value="card">{t("card", lang)}</option>
                  </select>
                </div>
                <button
                  type="button"
                  className="primary"
                  style={{ alignSelf: "end" }}
                  disabled={busy || !online}
                  data-testid="take-payment"
                  onClick={() => void takePayment("manual")}
                >
                  {t("takePayment", lang)} ({t(payMethod, lang)})
                </button>
                <button
                  type="button"
                  className="secondary"
                  style={{ alignSelf: "end" }}
                  disabled={busy || !online}
                  onClick={() => void takePayment("sandbox")}
                >
                  {t("upi", lang)} (sandbox)
                </button>
              </div>
            )}

            {selected.payments.length > 0 && (
              <table style={{ marginTop: "0.75rem" }}>
                <thead>
                  <tr>
                    <th>{t("amount", lang)}</th>
                    <th>{t("method", lang)}</th>
                    <th>{t("status", lang)}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {selected.payments.map((pay: Payment) => (
                    <tr key={pay.id}>
                      <td>{Number(pay.amount).toFixed(2)}</td>
                      <td>
                        {pay.method} <span className="muted">({pay.gateway})</span>
                      </td>
                      <td>
                        <span className="tag">{pay.status}</span>
                      </td>
                      <td>
                        {pay.status === "pending" && can("billing.payment") && (
                          <button
                            type="button"
                            className="primary"
                            disabled={busy || !online}
                            onClick={() => void confirmSandbox(pay.id)}
                          >
                            {t("payment", lang)} ✓
                          </button>
                        )}
                        {(pay.status === "succeeded" || pay.status === "partially_refunded") &&
                          can("billing.refund") && (
                            <button
                              type="button"
                              className="secondary"
                              disabled={busy}
                              onClick={() => {
                                setRefundFor(pay);
                                setRefundAmount("");
                                setRefundReason("");
                              }}
                            >
                              {t("refund", lang)}
                            </button>
                          )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {refundFor && (
              <div className="card inset" style={{ marginTop: "0.75rem" }}>
                <h4 style={{ marginTop: 0 }}>
                  {t("refund", lang)} — {Number(refundFor.amount).toFixed(2)} ({refundFor.method})
                </h4>
                <div className="row">
                  <div className="field">
                    <label htmlFor="rf-amt">{t("amount", lang)}</label>
                    <input
                      id="rf-amt"
                      inputMode="decimal"
                      value={refundAmount}
                      onChange={(e) => setRefundAmount(e.target.value)}
                    />
                  </div>
                  <div className="field grow">
                    <label htmlFor="rf-reason">{t("reason", lang)}</label>
                    <input
                      id="rf-reason"
                      value={refundReason}
                      maxLength={300}
                      onChange={(e) => setRefundReason(e.target.value)}
                    />
                  </div>
                  <button
                    type="button"
                    className="primary"
                    style={{ alignSelf: "end" }}
                    disabled={busy || !online}
                    onClick={() => void submitRefund()}
                  >
                    {t("refund", lang)}
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    style={{ alignSelf: "end" }}
                    onClick={() => setRefundFor(null)}
                  >
                    {t("cancel", lang)}
                  </button>
                </div>
              </div>
            )}

            <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
              <button type="button" className="secondary" onClick={() => void loadReceipt()}>
                {t("receipt", lang)}
              </button>
              {receipt && (
                <a
                  className="primary"
                  href={`/print/rx/${selected.id}?type=receipt`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ padding: "0.5rem 1rem" }}
                >
                  {t("printReceipt", lang)}
                </a>
              )}
            </div>

            {receipt && (
              <div className="notice" style={{ marginTop: "0.75rem" }}>
                <strong>{receipt.org_name}</strong> / {receipt.branch_name} —{" "}
                {receipt.patient_name} ({receipt.patient_uhid})
                <br />
                {t("total", lang)}: {Number(receipt.invoice.total).toFixed(2)} ·{" "}
                {t("amountPaid", lang)}: {Number(receipt.invoice.amount_paid).toFixed(2)} ·{" "}
                {t("balanceDue", lang)}: {receipt.balance_due.toFixed(2)}
                <br />
                <span className="muted">
                  {t("ledger", lang)}:{" "}
                  {receipt.ledger
                    .map(
                      (e) =>
                        `${t(e.entry_type === "charge" ? "charge" : "payment", lang)} ${
                          e.direction === "debit" ? "+" : "−"
                        }${Number(e.amount).toFixed(2)}`
                    )
                    .join(" · ")}
                </span>
              </div>
            )}
          </section>
        )}
      </main>
  );
}
