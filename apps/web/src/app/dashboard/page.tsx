"use client";

import Link from "next/link";
import { AppShell, NAV } from "@/components/AppShell";
import { useLang } from "@/lib/lang";
import { hasPermission, useMe } from "@/lib/me";

function DashboardBody() {
  const { t } = useLang();
  const me = useMe();
  if (!me) return null;
  const modules = NAV.filter((n) => n.key !== "dashboard" && hasPermission(me, n.perm));
  return (
    <main className="page">
      <div className="card">
        <h1 style={{ marginTop: 0 }}>
          {t("welcome")}, {me.user.full_name}
        </h1>
        <p className="muted" style={{ marginBottom: "0.4rem" }}>
          {t("org")}: <strong>{me.organization.name}</strong> ({me.organization.slug}) —{" "}
          {t("role")}: <strong>{me.role}</strong>
        </p>
      </div>
      <div className="grid kpis" style={{ marginTop: "1.25rem" }}>
        {modules.map((m) => (
          <Link className="card kpi tile" href={m.href} key={m.key}>
            <span className="label">{t(m.key)}</span>
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
