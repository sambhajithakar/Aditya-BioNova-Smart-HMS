"use client";

/**
 * Platform console — one tenant: profile + counters, subscription editor
 * (PUT /platform/tenants/{id}/subscription: plan, status, billing cycle,
 * trial / period end, per-limit overrides, mandatory reason), suspend /
 * reactivate with reason (PATCH /platform/tenants/{id}) and the
 * subscription events timeline.
 *
 * Limit overrides: each limit is "plan default" (not sent), a custom whole
 * number, or unlimited (null). The field is omitted entirely when nothing is
 * overridden so existing overrides are not clobbered.
 */
import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { PlatformShell } from "@/components/PlatformShell";
import { Messages, UsageMeter, fmtDate, fmtDateTime, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import {
  LIMIT_KEYS,
  PlatformPlanOut,
  PlatformTenant,
  PlatformTenantDetail,
  SUBSCRIPTION_STATUSES,
  dateInputToIso,
  isoToDateInput,
  parseLimit,
  serverMessage,
} from "@/lib/saas";

type OverrideMode = "inherit" | "custom" | "unlimited";
type Editor = {
  plan_code: string;
  status: string;
  billing_cycle: string;
  trial_ends_at: string;
  current_period_end: string;
  overrides: Record<string, { mode: OverrideMode; value: string }>;
  reason: string;
};

function editorFrom(d: PlatformTenantDetail): Editor {
  const s = d.subscription;
  const overrides: Editor["overrides"] = {};
  for (const k of LIMIT_KEYS) overrides[k] = { mode: "inherit", value: "" };
  return {
    plan_code: s?.plan.code ?? d.plan_code ?? "",
    status: s?.status ?? d.subscription_status ?? "active",
    billing_cycle: s?.billing_cycle ?? "monthly",
    trial_ends_at: isoToDateInput(s?.trial_ends_at ?? d.trial_ends_at),
    current_period_end: isoToDateInput(s?.current_period_end),
    overrides,
    reason: "",
  };
}

function TenantBody() {
  const { t } = useLang();
  const params = useParams<{ id: string }>();
  const id = String(params?.id ?? "");
  const { busy, error, notice, setError, setNotice, act } = useAction();
  const [tenant, setTenant] = useState<PlatformTenantDetail | null>(null);
  const [plans, setPlans] = useState<PlatformPlanOut[]>([]);
  const [ed, setEd] = useState<Editor | null>(null);
  const [suspendReason, setSuspendReason] = useState("");

  const load = useCallback(async () => {
    try {
      const [d, p] = await Promise.all([
        api.get<PlatformTenantDetail>(`/platform/tenants/${encodeURIComponent(id)}`),
        api.get<PlatformPlanOut[]>("/platform/plans").catch(() => [] as PlatformPlanOut[]),
      ]);
      setTenant(d);
      setPlans([...p].sort((a, b) => a.sort_order - b.sort_order || a.tier - b.tier));
      setEd(editorFrom(d));
    } catch (err) {
      setError(serverMessage(err, t("loadFailed")));
    }
  }, [id, setError, t]);

  useEffect(() => {
    if (id) void load();
  }, [id, load]);

  if (!tenant || !ed) {
    return (
      <main className="page">
        <Messages error={error} notice={notice} />
        {!error && <p className="muted">{t("loading")}</p>}
      </main>
    );
  }

  const setOv = (k: string, patch: Partial<{ mode: OverrideMode; value: string }>) =>
    setEd({ ...ed, overrides: { ...ed.overrides, [k]: { ...ed.overrides[k], ...patch } } });

  const onSave = (e: FormEvent) => {
    e.preventDefault();
    if (!ed.reason.trim()) {
      setError(t("reasonRequired"));
      return;
    }
    const limit_overrides: Record<string, number | null> = {};
    for (const [k, o] of Object.entries(ed.overrides)) {
      if (o.mode === "unlimited") limit_overrides[k] = null;
      else if (o.mode === "custom") {
        const n = parseLimit(o.value);
        if (n === undefined) {
          setError(t("invalidLimit"));
          return;
        }
        limit_overrides[k] = n;
      }
    }
    const body: Record<string, unknown> = {
      plan_code: ed.plan_code,
      status: ed.status,
      billing_cycle: ed.billing_cycle,
      trial_ends_at: dateInputToIso(ed.trial_ends_at),
      current_period_end: dateInputToIso(ed.current_period_end),
      reason: ed.reason.trim(),
    };
    if (Object.keys(limit_overrides).length > 0) body.limit_overrides = limit_overrides;
    void act(async () => {
      const d = await api.put<PlatformTenantDetail>(
        `/platform/tenants/${encodeURIComponent(id)}/subscription`,
        body,
      );
      setTenant(d);
      setEd(editorFrom(d));
      setNotice(t("saved"));
    });
  };

  const setTenantStatus = (status: "active" | "suspended") => {
    if (!suspendReason.trim()) {
      setError(t("reasonRequired"));
      return;
    }
    void act(async () => {
      await api.patch<PlatformTenant>(`/platform/tenants/${encodeURIComponent(id)}`, {
        status,
        reason: suspendReason.trim(),
      });
      setSuspendReason("");
      setNotice(t("saved"));
      await load();
    });
  };

  const sub = tenant.subscription;
  const subLabel = (s: string | null | undefined) => (s ? t(`subStatus_${s}`) : "—");

  return (
    <main className="page" style={{ maxWidth: 1280 }}>
      <p style={{ marginTop: 0 }}>
        <Link href="/platform">← {t("kpiTenants")}</Link>
      </p>
      <h1 style={{ marginTop: 0 }} data-testid="tenant-name">
        {tenant.name}
      </h1>
      <p className="muted">
        {tenant.slug} · {t("tenantStatus")}: <strong>{t(tenant.status)}</strong> ·{" "}
        {t("subscriptionStatus")}: <strong data-testid="tenant-sub-status">{subLabel(tenant.effective_status)}</strong>{" "}
        · {t("plan")}: <strong data-testid="tenant-plan">{sub?.plan.name ?? tenant.plan_code ?? "—"}</strong>
        {tenant.offboarding_requested_at && (
          <>
            {" "}
            · <span className="tag">{t("offboardingFlag")}: {fmtDate(tenant.offboarding_requested_at)}</span>
          </>
        )}
      </p>
      <Messages error={error} notice={notice} />

      <div className="grid kpis">
        <div className="card kpi">
          <div className="label">{t("users")}</div>
          <div className="value">{tenant.users}</div>
        </div>
        <div className="card kpi">
          <div className="label">{t("navBranches")}</div>
          <div className="value">{tenant.branches}</div>
        </div>
        <div className="card kpi">
          <div className="label">{t("beds")}</div>
          <div className="value">{tenant.beds}</div>
        </div>
        <div className="card kpi">
          <div className="label">{t("patients")}</div>
          <div className="value">{tenant.patients}</div>
        </div>
      </div>

      {sub && Object.keys(sub.usage).length > 0 && (
        <section className="card" style={{ marginTop: "1.25rem" }}>
          <h2 style={{ marginTop: 0 }}>{t("usage")}</h2>
          <div className="grid kpis">
            {Object.entries(sub.usage).map(([k, u]) => (
              <UsageMeter key={k} label={t(`limit_${k}`)} entry={u} />
            ))}
          </div>
        </section>
      )}

      <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="sub-h">
        <h2 id="sub-h" style={{ marginTop: 0 }}>
          {t("navSubscription")}
        </h2>
        <form onSubmit={onSave}>
          <div className="grid two">
            <label className="field">
              {t("plan")}
              <select
                value={ed.plan_code}
                onChange={(e) => setEd({ ...ed, plan_code: e.target.value })}
                required
                data-testid="plan-select"
              >
                {!plans.some((p) => p.code === ed.plan_code) && (
                  <option value={ed.plan_code}>{ed.plan_code || "—"}</option>
                )}
                {plans.map((p) => (
                  <option key={p.code} value={p.code}>
                    {p.name} ({p.code}){p.is_active ? "" : " ✕"}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              {t("subscriptionStatus")}
              <select value={ed.status} onChange={(e) => setEd({ ...ed, status: e.target.value })}>
                {SUBSCRIPTION_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {t(`subStatus_${s}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              {t("billingCycle")}
              <select
                value={ed.billing_cycle}
                onChange={(e) => setEd({ ...ed, billing_cycle: e.target.value })}
              >
                <option value="monthly">{t("cycle_monthly")}</option>
                <option value="annual">{t("cycle_annual")}</option>
              </select>
            </label>
            <label className="field">
              {t("trialEndsAt")}
              <input
                type="date"
                value={ed.trial_ends_at}
                onChange={(e) => setEd({ ...ed, trial_ends_at: e.target.value })}
              />
            </label>
            <label className="field">
              {t("periodEndAt")}
              <input
                type="date"
                value={ed.current_period_end}
                onChange={(e) => setEd({ ...ed, current_period_end: e.target.value })}
              />
            </label>
          </div>

          <fieldset style={{ border: "1px solid var(--border)", borderRadius: "var(--radius)", marginTop: "1rem" }}>
            <legend style={{ fontWeight: 700 }}>{t("limitOverrides")}</legend>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t("limitsTitle")}</th>
                    <th scope="col">{t("plan")}</th>
                    <th scope="col">{t("limitOverrides")}</th>
                  </tr>
                </thead>
                <tbody>
                  {LIMIT_KEYS.map((k) => {
                    const o = ed.overrides[k];
                    const planVal = sub?.plan.limits?.[k];
                    return (
                      <tr key={k}>
                        <th scope="row">{t(`limit_${k}`)}</th>
                        <td>{planVal === null || planVal === undefined ? t("unlimited") : planVal}</td>
                        <td>
                          <div className="row" style={{ alignItems: "center" }}>
                            <select
                              aria-label={`${t("limitOverrides")} — ${t(`limit_${k}`)}`}
                              value={o.mode}
                              onChange={(e) => setOv(k, { mode: e.target.value as OverrideMode })}
                            >
                              <option value="inherit">{t("inheritPlan")}</option>
                              <option value="custom">{t("customValue")}</option>
                              <option value="unlimited">{t("unlimited")}</option>
                            </select>
                            {o.mode === "custom" && (
                              <input
                                type="number"
                                min={0}
                                step={1}
                                aria-label={`${t("customValue")} — ${t(`limit_${k}`)}`}
                                value={o.value}
                                onChange={(e) => setOv(k, { value: e.target.value })}
                                style={{ width: 120 }}
                                required
                              />
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </fieldset>

          <label className="field" style={{ marginTop: "1rem" }}>
            {t("reason")}
            <input
              type="text"
              value={ed.reason}
              maxLength={500}
              onChange={(e) => setEd({ ...ed, reason: e.target.value })}
              required
              data-testid="subscription-reason"
            />
          </label>
          <button type="submit" className="primary" disabled={busy} style={{ marginTop: "1rem" }}>
            {t("saveSubscription")}
          </button>
        </form>
      </section>

      <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="tstatus-h">
        <h2 id="tstatus-h" style={{ marginTop: 0 }}>
          {t("tenantStatus")}
        </h2>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <label className="field grow">
            {t("reason")}
            <input
              type="text"
              value={suspendReason}
              maxLength={500}
              onChange={(e) => setSuspendReason(e.target.value)}
              data-testid="tenant-status-reason"
            />
          </label>
          {tenant.status === "suspended" ? (
            <button type="button" className="primary" disabled={busy} onClick={() => setTenantStatus("active")}>
              {t("reactivateTenant")}
            </button>
          ) : (
            <button type="button" className="danger" disabled={busy} onClick={() => setTenantStatus("suspended")}>
              {t("suspendTenant")}
            </button>
          )}
        </div>
      </section>

      <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="events-h">
        <h2 id="events-h" style={{ marginTop: 0 }}>
          {t("history")}
        </h2>
        <ol className="timeline" data-testid="tenant-events">
          {tenant.events.map((ev) => (
            <li key={ev.id}>
              <div>
                <strong>{fmtDateTime(ev.created_at)}</strong>
                {ev.actor_name && (
                  <span className="muted">
                    {" "}
                    · {t("by")} {ev.actor_name}
                  </span>
                )}
              </div>
              <div>
                {(ev.from_plan || ev.to_plan) && (
                  <span>
                    {t("plan")}: {ev.from_plan ?? "—"} → {ev.to_plan ?? "—"}{" "}
                  </span>
                )}
                {(ev.from_status || ev.to_status) && (
                  <span>
                    · {t("status")}: {subLabel(ev.from_status)} → {subLabel(ev.to_status)}
                  </span>
                )}
              </div>
              {ev.reason && <div className="muted">{ev.reason}</div>}
            </li>
          ))}
          {tenant.events.length === 0 && <li className="muted">{t("noEvents")}</li>}
        </ol>
      </section>
    </main>
  );
}

export default function PlatformTenantPage() {
  return (
    <PlatformShell active="overview">
      <TenantBody />
    </PlatformShell>
  );
}
