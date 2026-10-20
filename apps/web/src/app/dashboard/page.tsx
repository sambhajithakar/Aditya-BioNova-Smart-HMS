"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { SetupWizardCard } from "@/components/SetupWizardCard";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { hasPermission, useMe } from "@/lib/me";
import { NAV, navLabel } from "@/lib/nav";
import { ONBOARDING_STEPS, Onboarding, visibleNav } from "@/lib/saas";

/**
 * M7.1 onboarding checklist for owners / admins (org.manage): each step of
 * GET /organization/onboarding links to the page that completes it. Hidden
 * once every step is done or if the endpoint is unavailable.
 */
function OnboardingCard() {
  const { t } = useLang();
  const [data, setData] = useState<Onboarding | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<Onboarding>("/organization/onboarding")
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  if (!data || data.completed) return null;
  const doneCount = data.steps.filter((s) => s.done).length;
  return (
    <section className="card" style={{ marginTop: "1.25rem" }} data-testid="onboarding">
      <h2 style={{ marginTop: 0 }}>
        {t("onboardingTitle")}{" "}
        <span className="muted" style={{ fontSize: "1rem" }}>
          ({doneCount}/{data.steps.length})
        </span>
      </h2>
      <ol className="steps">
        {data.steps.map((s) => {
          const href = ONBOARDING_STEPS.find((x) => x.key === s.key)?.href ?? "/dashboard";
          return (
            <li key={s.key} className={s.done ? "done" : undefined}>
              <span className="mark" aria-hidden="true">
                {s.done ? "✓" : ""}
              </span>
              <Link href={href}>{t(`step_${s.key}`)}</Link>
              <span className="sr-only">
                {s.done ? t("stepDone") : t("stepTodo")}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function DashboardBody() {
  const { t } = useLang();
  const me = useMe();
  if (!me) return null;
  const modules = visibleNav(NAV, me).filter((n) => n.key !== "dashboard");
  return (
    <main className="page">
      <div className="card">
        <h1 style={{ marginTop: 0 }}>
          {t("welcome")}, {me.user.full_name}
        </h1>
        <p className="muted" style={{ marginBottom: "0.4rem" }}>
          {t("org")}: <strong>{me.organization.name}</strong> ({me.organization.slug}) —{" "}
          {t("role")}: <strong>{me.role}</strong>
          {me.edition && (
            <>
              {" "}
              — {t("currentEdition")}: <strong>{me.edition.name}</strong>
            </>
          )}
        </p>
      </div>
      {hasPermission(me, "setup.manage") && <SetupWizardCard />}
      {hasPermission(me, "org.manage") && <OnboardingCard />}
      <div className="grid kpis" style={{ marginTop: "1.25rem" }}>
        {modules.map((m) => (
          <Link className="card kpi tile" href={m.href} key={m.key}>
            <span className="label">{t(navLabel(m))}</span>
          </Link>
        ))}
      </div>
    </main>
  );
}

export default function DashboardPage() {
  return (
    <AppShell active="dashboard">
      <DashboardBody />
    </AppShell>
  );
}
