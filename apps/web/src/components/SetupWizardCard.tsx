"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { WizardState } from "@/lib/setup";

/**
 * Dashboard call-to-action for owners / admins while the Smart Setup Wizard
 * is unfinished (server-side state, so it follows them across devices).
 * It deliberately does not force a redirect: staff always land where they
 * expect and can open the wizard when convenient.
 */
export function SetupWizardCard() {
  const { t } = useLang();
  const [state, setState] = useState<WizardState | null>(null);
  useEffect(() => {
    let cancelled = false;
    api
      .get<WizardState>("/setup/wizard")
      .then((s) => {
        if (!cancelled) setState(s);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  if (!state || !state.should_show) return null;
  const started = state.progress_percent > 0;
  return (
    <section className="card" style={{ marginTop: "1.25rem", borderLeft: "4px solid var(--teal-500)" }} data-testid="setup-card">
      <h2 style={{ marginTop: 0 }}>{t("wizCardTitle")}</h2>
      <p style={{ marginTop: 0 }}>{t("wizCardBody")}</p>
      <div className="meter ok" style={{ marginBottom: "0.75rem" }}>
        <div className="bar" aria-hidden="true">
          <div className="fill" style={{ width: `${state.progress_percent}%` }} />
        </div>
        <span className="figure">{state.progress_percent}%</span>
      </div>
      <Link
        href="/setup"
        data-testid="setup-card-link"
        style={{
          display: "inline-block",
          padding: "0.55rem 1rem",
          borderRadius: 6,
          background: "var(--teal-600)",
          color: "#fff",
          fontWeight: 700,
          textDecoration: "none",
        }}
      >
        {started ? t("wizCardContinue") : t("wizCardStart")}
      </Link>
    </section>
  );
}
