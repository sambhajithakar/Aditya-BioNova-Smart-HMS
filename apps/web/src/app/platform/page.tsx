"use client";

/**
 * Platform console — overview KPIs (GET /platform/overview) and the tenant
 * directory (GET /platform/tenants?q=&status=) linking to tenant detail.
 * MRR is integer paise; subscriptions without a configured price are not in
 * MRR and are called out explicitly.
 */
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { PlatformShell } from "@/components/PlatformShell";
import { Messages, fmtDate, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import {
  PlatformOverview,
  PlatformTenant,
  SUBSCRIPTION_STATUSES,
  formatPaise,
  serverMessage,
} from "@/lib/saas";

function Breakdown({ title, data, labelOf }: {
  title: string;
  data: Record<string, number>;
  labelOf: (k: string) => string;
}) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return (
    <section className="card">
      <h2 style={{ marginTop: 0, fontSize: "1.1rem" }}>{title}</h2>
      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: "0.4rem" }}>
        {entries.map(([k, v]) => (
          <li key={k} className="meter">
            <span style={{ display: "flex", justifyContent: "space-between" }}>
              <span>{labelOf(k)}</span>
              <strong>{v}</strong>
            </span>
            <div className="bar" aria-hidden="true">
              <div className="fill" style={{ width: `${Math.round((v / max) * 100)}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function OverviewBody() {
  const { t } = useLang();
  const { error, setError } = useAction();
  const [ov, setOv] = useState<PlatformOverview | null>(null);
  const [tenants, setTenants] = useState<PlatformTenant[]>([]);
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    api
      .get<PlatformOverview>("/platform/overview")
      .then(setOv)
      .catch((err) => setError(serverMessage(err, t("loadFailed"))));
  }, [setError, t]);

  const loadTenants = useCallback(async () => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (status) params.set("status", status);
    try {
      const qs = params.toString();
      setTenants(await api.get<PlatformTenant[]>(`/platform/tenants${qs ? `?${qs}` : ""}`));
    } catch (err) {
      setError(serverMessage(err, t("loadFailed")));
    }
  }, [q, status, setError, t]);

  useEffect(() => {
    void loadTenants();
  }, [loadTenants]);

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    setQ(qInput.trim().slice(0, 100));
  };

  const statusLabel = (s: string | null) => {
    if (!s) return "—";
    const k = `subStatus_${s}`;
    const v = t(k);
    return v === k ? t(s) : v;
  };
  const totalTenants = ov ? Object.values(ov.tenants_by_status).reduce((a, b) => a + b, 0) : 0;

  return (
    <main className="page" style={{ maxWidth: 1280 }}>
      <h1 style={{ marginTop: 0 }}>{t("platformOverview")}</h1>
      <Messages error={error} notice={null} />

      {ov && (
        <>
          <div className="grid kpis" data-testid="platform-kpis">
            <div className="card kpi">
              <div className="label">{t("kpiTenants")}</div>
              <div className="value">{totalTenants}</div>
            </div>
            <div className="card kpi">
              <div className="label">{t("kpiMrr")}</div>
              <div className="value" data-testid="mrr">
                {formatPaise(ov.mrr_paise) ?? "₹0"}
              </div>
              {ov.unpriced_active_subscriptions > 0 && (
                <div className="muted" data-testid="unpriced">
                  {ov.unpriced_active_subscriptions} {t("unpricedNote")}
                </div>
              )}
            </div>
            <div className="card kpi">
              <div className="label">{t("kpiTrials7d")}</div>
              <div className="value">{ov.trials_expiring_7d}</div>
            </div>
            <div className="card kpi">
              <div className="label">{t("kpiOpenTickets")}</div>
              <div className="value">
                <Link href="/platform/support">{ov.open_tickets}</Link>
              </div>
            </div>
          </div>
          <div className="grid two" style={{ marginTop: "1rem" }}>
            <Breakdown title={t("tenantsByStatus")} data={ov.tenants_by_status} labelOf={statusLabel} />
            <Breakdown title={t("tenantsByPlan")} data={ov.tenants_by_plan} labelOf={(k) => k} />
          </div>
        </>
      )}

      <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="tenants-h">
        <h2 id="tenants-h" style={{ marginTop: 0 }}>
          {t("kpiTenants")}
        </h2>
        <form className="row" onSubmit={onSearch} style={{ alignItems: "flex-end", marginBottom: "0.75rem" }}>
          <label className="field grow">
            {t("search")}
            <input
              type="search"
              value={qInput}
              maxLength={100}
              onChange={(e) => setQInput(e.target.value)}
            />
          </label>
          <label className="field">
            {t("status")}
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">{t("allStatuses")}</option>
              {SUBSCRIPTION_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {t(`subStatus_${s}`)}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="primary">
            {t("search")}
          </button>
        </form>
        <div className="table-wrap">
          <table data-testid="tenants-table">
            <thead>
              <tr>
                <th scope="col">{t("tenant")}</th>
                <th scope="col">{t("plan")}</th>
                <th scope="col">{t("subscriptionStatus")}</th>
                <th scope="col">{t("trialEnds")}</th>
                <th scope="col">{t("users")}</th>
                <th scope="col">{t("navBranches")}</th>
                <th scope="col">{t("beds")}</th>
                <th scope="col">{t("patients")}</th>
                <th scope="col">{t("createdAt")}</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map((tn) => (
                <tr key={tn.id}>
                  <td>
                    <Link href={`/platform/tenants/${encodeURIComponent(tn.id)}`}>{tn.name}</Link>
                    <div className="muted" style={{ fontSize: "0.85rem" }}>
                      {tn.slug}
                      {tn.status !== "active" && <> · {t(tn.status)}</>}
                      {tn.offboarding_requested_at && (
                        <>
                          {" "}
                          <span className="tag">{t("offboardingFlag")}</span>
                        </>
                      )}
                    </div>
                  </td>
                  <td>{tn.plan_code ?? "—"}</td>
                  <td>{statusLabel(tn.effective_status)}</td>
                  <td>{fmtDate(tn.trial_ends_at)}</td>
                  <td>{tn.users}</td>
                  <td>{tn.branches}</td>
                  <td>{tn.beds}</td>
                  <td>{tn.patients}</td>
                  <td>{fmtDate(tn.created_at)}</td>
                </tr>
              ))}
              {tenants.length === 0 && (
                <tr>
                  <td colSpan={9} className="muted">
                    {t("noResults")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

export default function PlatformPage() {
  return (
    <PlatformShell active="overview">
      <OverviewBody />
    </PlatformShell>
  );
}
