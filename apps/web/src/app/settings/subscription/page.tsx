"use client";

/**
 * Subscription (M7.1, tenant view): current edition, effective status, trial
 * countdown, period end, included features, usage against plan limits, the
 * plan comparison (GET /plans) and a "request plan change" form that opens a
 * billing support ticket. There is NO online payment in M7.1 — the vendor
 * processes the request and invoices offline; the page says so.
 */
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Messages, UsageMeter, fmtDate, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { useCan } from "@/lib/me";
import {
  FEATURE_KEYS,
  LIMIT_KEYS,
  PlanOut,
  SubscriptionOut,
  SupportTicket,
  daysUntil,
  formatPaise,
  serverMessage,
} from "@/lib/saas";

function SubscriptionBody() {
  const { t } = useLang();
  const can = useCan();
  const manage = can("subscription.manage");
  const { busy, error, notice, setError, setNotice, act } = useAction();
  const [sub, setSub] = useState<SubscriptionOut | null>(null);
  const [plans, setPlans] = useState<PlanOut[]>([]);
  const [req, setReq] = useState({ plan_code: "", billing_cycle: "monthly", note: "" });
  const [ticket, setTicket] = useState<SupportTicket | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, p] = await Promise.all([
        api.get<SubscriptionOut>("/subscription"),
        api.get<PlanOut[]>("/plans").catch(() => [] as PlanOut[]),
      ]);
      setSub(s);
      setPlans([...p].sort((a, b) => a.tier - b.tier));
      setReq((r) => ({ ...r, billing_cycle: s.billing_cycle ?? "monthly" }));
    } catch (err) {
      setError(serverMessage(err, t("loadFailed")));
    }
  }, [setError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const onRequest = (e: FormEvent) => {
    e.preventDefault();
    void act(async () => {
      const tk = await api.post<SupportTicket>("/subscription/change-request", {
        plan_code: req.plan_code,
        billing_cycle: req.billing_cycle,
        ...(req.note.trim() ? { note: req.note.trim() } : {}),
      });
      setTicket(tk);
      setReq({ ...req, note: "" });
      setNotice(`${t("changeRequested")} #${tk.number}`);
    });
  };

  const price = (p: number | null, per: string) => {
    const s = formatPaise(p);
    return s ? `${s} ${t(per)}` : t("priceOnRequest");
  };
  const limitText = (v: number | null | undefined) =>
    v === null || v === undefined ? t("unlimited") : String(v);

  if (!sub) {
    return (
      <main className="page">
        <h1 style={{ marginTop: 0 }}>{t("navSubscription")}</h1>
        <Messages error={error} notice={notice} />
        {!error && <p className="muted">{t("loading")}</p>}
      </main>
    );
  }

  const trialDays = sub.effective_status === "trialing" ? daysUntil(sub.trial_ends_at) : null;
  const included = new Set(sub.features);
  const knownFeatures = [
    ...FEATURE_KEYS.filter((k) => included.has(k)),
    ...sub.features.filter((k) => !(FEATURE_KEYS as readonly string[]).includes(k)),
  ];
  const limitKeys = [
    ...LIMIT_KEYS.filter((k) => k in sub.usage),
    ...Object.keys(sub.usage).filter((k) => !(LIMIT_KEYS as readonly string[]).includes(k)),
  ];
  const label = (prefix: string, k: string) => {
    const s = t(`${prefix}_${k}`);
    return s === `${prefix}_${k}` ? k : s;
  };

  return (
    <main className="page">
      <h1 style={{ marginTop: 0 }}>{t("navSubscription")}</h1>
      <Messages error={error} notice={notice} />
      {ticket && (
        <p>
          <Link href="/support">{t("navSupport")} →</Link>
        </p>
      )}

      <section className="card" data-testid="current-plan">
        <div className="grid kpis">
          <div className="kpi">
            <div className="label">{t("currentEdition")}</div>
            <div className="value" style={{ fontSize: "1.5rem" }} data-testid="plan-name">
              {sub.plan.name}
            </div>
          </div>
          <div className="kpi">
            <div className="label">{t("status")}</div>
            <div className="value" style={{ fontSize: "1.5rem" }} data-testid="effective-status">
              {t(`subStatus_${sub.effective_status}`)}
            </div>
            {sub.status !== sub.effective_status && (
              <div className="muted">
                {t("storedStatus")}: {t(`subStatus_${sub.status}`)}
              </div>
            )}
          </div>
          <div className="kpi">
            <div className="label">{t("billingCycle")}</div>
            <div className="value" style={{ fontSize: "1.5rem" }}>
              {t(`cycle_${sub.billing_cycle}`)}
            </div>
          </div>
          {sub.trial_ends_at && (
            <div className="kpi">
              <div className="label">{t("trialEnds")}</div>
              <div className="value" style={{ fontSize: "1.5rem" }}>
                {fmtDate(sub.trial_ends_at)}
              </div>
              {trialDays !== null && (
                <div className="muted" data-testid="trial-countdown">
                  {trialDays > 0 ? `${trialDays} ${t("trialDaysLeft")}` : t("trialExpired")}
                </div>
              )}
            </div>
          )}
          {sub.current_period_end && (
            <div className="kpi">
              <div className="label">{t("periodEnd")}</div>
              <div className="value" style={{ fontSize: "1.5rem" }}>
                {fmtDate(sub.current_period_end)}
              </div>
            </div>
          )}
        </div>
        {sub.read_only_reason && (
          <p className="warn-box" style={{ marginBottom: 0 }}>
            {t("readOnlyReason")}: {sub.read_only_reason}
          </p>
        )}
      </section>

      <div className="grid two" style={{ marginTop: "1.25rem" }}>
        <section className="card" aria-labelledby="usage-h">
          <h2 id="usage-h" style={{ marginTop: 0 }}>
            {t("usage")}
          </h2>
          <div className="grid" data-testid="usage">
            {limitKeys.map((k) => (
              <UsageMeter key={k} label={label("limit", k)} entry={sub.usage[k]} />
            ))}
          </div>
        </section>
        <section className="card" aria-labelledby="features-h">
          <h2 id="features-h" style={{ marginTop: 0 }}>
            {t("featuresIncluded")}
          </h2>
          <ul style={{ margin: 0, paddingLeft: "1.2rem", columns: 2 }} data-testid="features">
            {knownFeatures.map((k) => (
              <li key={k}>{label("feature", k)}</li>
            ))}
          </ul>
        </section>
      </div>

      {plans.length > 0 && (
        <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="compare-h">
          <h2 id="compare-h" style={{ marginTop: 0 }}>
            {t("comparePlans")}
          </h2>
          <div className="table-wrap">
            <table data-testid="plan-comparison">
              <thead>
                <tr>
                  <th scope="col">{t("plan")}</th>
                  {plans.map((p) => (
                    <th scope="col" key={p.code}>
                      {p.name}
                      {p.code === sub.plan.code && (
                        <>
                          {" "}
                          <span className="tag">{t("currentPlanTag")}</span>
                        </>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">{t("cycle_monthly")}</th>
                  {plans.map((p) => (
                    <td key={p.code}>{price(p.price_monthly_paise, "perMonth")}</td>
                  ))}
                </tr>
                <tr>
                  <th scope="row">{t("cycle_annual")}</th>
                  {plans.map((p) => (
                    <td key={p.code}>{price(p.price_annual_paise, "perYear")}</td>
                  ))}
                </tr>
                <tr>
                  <th scope="row">{t("trialDays")}</th>
                  {plans.map((p) => (
                    <td key={p.code}>{p.trial_days}</td>
                  ))}
                </tr>
                {LIMIT_KEYS.map((k) => (
                  <tr key={k}>
                    <th scope="row">{t(`limit_${k}`)}</th>
                    {plans.map((p) => (
                      <td key={p.code}>{limitText(p.limits?.[k])}</td>
                    ))}
                  </tr>
                ))}
                {FEATURE_KEYS.map((k) => (
                  <tr key={k}>
                    <th scope="row">{t(`feature_${k}`)}</th>
                    {plans.map((p) => {
                      const has = p.features.includes(k);
                      return (
                        <td key={p.code} className={has ? "yes" : "no"}>
                          <span aria-hidden="true">{has ? "✓" : "—"}</span>
                          <span className="sr-only">{has ? t("enabled") : t("disabled")}</span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="change-h">
        <h2 id="change-h" style={{ marginTop: 0 }}>
          {t("requestPlanChange")}
        </h2>
        <p className="notice" data-testid="payment-not-enabled">
          {t("paymentNotEnabled")}
        </p>
        {manage ? (
          <form className="stack" onSubmit={onRequest}>
            <label className="field">
              {t("plan")}
              <select
                value={req.plan_code}
                onChange={(e) => setReq({ ...req, plan_code: e.target.value })}
                required
              >
                <option value="">—</option>
                {plans.map((p) => (
                  <option key={p.code} value={p.code}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              {t("billingCycle")}
              <select
                value={req.billing_cycle}
                onChange={(e) => setReq({ ...req, billing_cycle: e.target.value })}
              >
                <option value="monthly">{t("cycle_monthly")}</option>
                <option value="annual">{t("cycle_annual")}</option>
              </select>
            </label>
            <label className="field">
              {t("noteOptional")}
              <textarea
                className="wide"
                rows={3}
                maxLength={2000}
                value={req.note}
                onChange={(e) => setReq({ ...req, note: e.target.value })}
              />
            </label>
            <button type="submit" className="primary" disabled={busy}>
              {t("sendRequest")}
            </button>
          </form>
        ) : (
          <p className="muted">{t("readOnlyView")}</p>
        )}
      </section>
    </main>
  );
}

export default function SubscriptionPage() {
  return (
    <AppShell active="subscription">
      <SubscriptionBody />
    </AppShell>
  );
}
