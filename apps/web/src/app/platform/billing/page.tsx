"use client";

/**
 * Vendor billing console (M7.2): recent SaaS orders, the refund approval
 * queue (four-eyes — the requester can never decide), AI credit pack prices,
 * the subscription lifecycle run (past-due → read-only) and reconciliation.
 * Plan prices are edited on the Plans page.
 */
import { useCallback, useEffect, useState } from "react";
import { PlatformShell } from "@/components/PlatformShell";
import { Messages, fmtDateTime, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { formatPaise, parseRupeesToPaise, serverMessage } from "@/lib/saas";
import { CatalogPack, ReconciliationIssue, SaasOrder, SaasRefund } from "@/lib/saasBilling";

const money = (p: number | null | undefined) => formatPaise(p ?? null) ?? "—";

function PlatformBillingBody() {
  const { t } = useLang();
  const { busy, error, notice, setError, setNotice, act } = useAction();
  const [orders, setOrders] = useState<SaasOrder[]>([]);
  const [refunds, setRefunds] = useState<SaasRefund[]>([]);
  const [packs, setPacks] = useState<CatalogPack[]>([]);
  const [prices, setPrices] = useState<Record<string, string>>({});
  const [issues, setIssues] = useState<ReconciliationIssue[] | null>(null);

  const load = useCallback(async () => {
    try {
      const [o, r, p] = await Promise.all([
        api.get<SaasOrder[]>("/platform/billing/orders?limit=50"),
        api.get<SaasRefund[]>("/platform/billing/refunds"),
        api.get<CatalogPack[]>("/platform/billing/credit-packs"),
      ]);
      setOrders(o);
      setRefunds(r);
      setPacks(p);
      setPrices(Object.fromEntries(p.map((k) => [k.code, k.price_paise ? (k.price_paise / 100).toFixed(2) : ""])));
    } catch (err) {
      setError(serverMessage(err, t("loadFailed")));
    }
  }, [setError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const decide = (r: SaasRefund, approve: boolean) =>
    act(async () => {
      const out = await api.post<SaasRefund>(`/platform/billing/refunds/${r.id}/decide`, { approve, note: "" });
      setNotice(`${t("billRefund")}: ${t(`billRefund_${out.status}`)}`);
      await load();
    });

  const savePack = (k: CatalogPack) =>
    act(async () => {
      const parsed = parseRupeesToPaise(prices[k.code] ?? "");
      if (!parsed.ok) throw new Error(t("billInvalidPrice"));
      await api.put(`/platform/billing/credit-packs/${k.code}`, {
        name: k.name,
        credits: k.credits,
        price_paise: parsed.paise || null,
        is_active: true,
      });
      setNotice(t("saved"));
      await load();
    });

  const lifecycle = () =>
    act(async () => {
      const c = await api.post<{ past_due: number; read_only: number; orders_expired: number }>(
        "/platform/billing/lifecycle",
        {},
      );
      setNotice(
        t("billLifecycleResult")
          .replace("{past_due}", String(c.past_due))
          .replace("{read_only}", String(c.read_only))
          .replace("{expired}", String(c.orders_expired)),
      );
    });

  const reconcile = () =>
    act(async () => {
      const r = await api.get<{ issues: ReconciliationIssue[] }>("/platform/billing/reconciliation");
      setIssues(r.issues);
    });

  return (
    <main className="page">
      <h1 style={{ marginTop: 0 }}>{t("billPlatformTitle")}</h1>
      <p className="muted">{t("billPlatformIntro")}</p>
      <Messages error={error} notice={notice} />

      <section className="card">
        <h2 style={{ marginTop: 0 }}>{t("billRefundQueue")}</h2>
        {refunds.length === 0 ? (
          <p className="muted">{t("billNone")}</p>
        ) : (
          <ul data-testid="refund-queue">
            {refunds.map((r) => (
              <li key={r.id}>
                {fmtDateTime(r.created_at)} · {money(r.amount_paise)} · {r.reason}{" "}
                <button type="button" className="primary" disabled={busy} onClick={() => void decide(r, true)}>
                  {t("billApprove")}
                </button>{" "}
                <button type="button" className="ghost" disabled={busy} onClick={() => void decide(r, false)}>
                  {t("billReject")}
                </button>
              </li>
            ))}
          </ul>
        )}
        <p className="muted">{t("billFourEyes")}</p>
      </section>

      <section className="card" style={{ marginTop: "1rem" }}>
        <h2 style={{ marginTop: 0 }}>{t("billCreditPacks")}</h2>
        {packs.map((k) => (
          <div key={k.code} className="row" style={{ gap: "0.5rem", alignItems: "end", marginBottom: "0.5rem" }}>
            <label className="field">
              {k.name} — {t("billPriceRupees")}
              <input
                aria-label={`${k.name} ${t("billPriceRupees")}`}
                inputMode="decimal"
                value={prices[k.code] ?? ""}
                placeholder={t("billNotPriced")}
                onChange={(e) => setPrices({ ...prices, [k.code]: e.target.value })}
              />
            </label>
            <button type="button" disabled={busy} onClick={() => void savePack(k)}>
              {t("save")}
            </button>
          </div>
        ))}
      </section>

      <section className="card" style={{ marginTop: "1rem" }}>
        <h2 style={{ marginTop: 0 }}>{t("billOperations")}</h2>
        <button type="button" disabled={busy} onClick={() => void lifecycle()}>
          {t("billRunLifecycle")}
        </button>{" "}
        <button type="button" disabled={busy} onClick={() => void reconcile()}>
          {t("billReconcile")}
        </button>
        {issues && (
          <div data-testid="reconciliation">
            {issues.length === 0 ? (
              <p>{t("billNoIssues")}</p>
            ) : (
              <ul>
                {issues.map((i, n) => (
                  <li key={n}>
                    <code>{i.kind}</code>{" "}
                    {Object.entries(i)
                      .filter(([k]) => k !== "kind")
                      .map(([k, v]) => `${k}=${v}`)
                      .join(" · ")}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      <section className="card" style={{ marginTop: "1rem" }}>
        <h2 style={{ marginTop: 0 }}>{t("billRecentOrders")}</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t("billDate")}</th>
                <th>{t("billItem")}</th>
                <th>{t("billTotal")}</th>
                <th>{t("billStatus")}</th>
                <th>{t("billProvider")}</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id}>
                  <td>{fmtDateTime(o.created_at)}</td>
                  <td>{o.description}</td>
                  <td>{money(o.total_paise)}</td>
                  <td>{t(`billStatus_${o.status}`)}</td>
                  <td>{o.provider}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

export default function PlatformBillingPage() {
  return (
    <PlatformShell active="billing">
      <PlatformBillingBody />
    </PlatformShell>
  );
}
