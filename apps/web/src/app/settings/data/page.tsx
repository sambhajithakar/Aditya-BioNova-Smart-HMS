"use client";

/**
 * Data export and offboarding (M7.1, owner only — org.offboard).
 *
 * Export: POST /organization/export streams a ZIP (one JSON file per table);
 * it is fetched as a Blob with the in-memory bearer token and handed to the
 * browser as a download, never stored by the app. Every export is audited
 * server-side.
 *
 * Offboarding: request (password + reason, explicit acknowledgement) or
 * cancel a pending request. Strong warnings — data is deleted after the
 * retention period.
 */
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Messages, fmtDateTime, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { useMe } from "@/lib/me";
import { OrganizationProfile, filenameFromDisposition, serverMessage } from "@/lib/saas";

function DataBody() {
  const { t } = useLang();
  const me = useMe();
  const { busy, error, notice, setError, setNotice, act } = useAction();
  const [org, setOrg] = useState<OrganizationProfile | null>(null);
  const [password, setPassword] = useState("");
  const [reason, setReason] = useState("");
  const [ack, setAck] = useState(false);

  const load = useCallback(async () => {
    try {
      setOrg(await api.get<OrganizationProfile>("/organization"));
    } catch (err) {
      setError(serverMessage(err, t("loadFailed")));
    }
  }, [setError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const onExport = () =>
    void act(async () => {
      const { blob, disposition } = await api.download("/organization/export", "POST");
      const stamp = new Date().toISOString().slice(0, 10);
      const name = filenameFromDisposition(
        disposition,
        `${me?.organization.slug ?? "organization"}-export-${stamp}.zip`,
      );
      const url = URL.createObjectURL(blob);
      try {
        const a = document.createElement("a");
        a.href = url;
        a.download = name;
        a.rel = "noopener";
        document.body.appendChild(a);
        a.click();
        a.remove();
      } finally {
        // give the browser a moment to start the download before revoking
        setTimeout(() => URL.revokeObjectURL(url), 10_000);
      }
      setNotice(t("exportDone"));
    });

  const onRequest = (e: FormEvent) => {
    e.preventDefault();
    if (!ack) return;
    void act(async () => {
      const o = await api.post<OrganizationProfile>("/organization/offboarding", {
        password,
        reason: reason.trim(),
      });
      setOrg(o);
      setPassword("");
      setReason("");
      setAck(false);
      setNotice(t("offboardingRequested"));
    });
  };

  const onCancel = () =>
    void act(async () => {
      setOrg(await api.del<OrganizationProfile>("/organization/offboarding"));
      setNotice(t("offboardingCancelled"));
    });

  return (
    <main className="page">
      <h1 style={{ marginTop: 0 }}>{t("dataTitle")}</h1>
      <p className="muted">{t("ownerOnly")}</p>
      <Messages error={error} notice={notice} />

      <section className="card" aria-labelledby="export-h">
        <h2 id="export-h" style={{ marginTop: 0 }}>
          {t("exportTitle")}
        </h2>
        <p className="warn-box">{t("exportHint")}</p>
        <button
          type="button"
          className="primary"
          disabled={busy}
          onClick={onExport}
          data-testid="export-button"
        >
          {t("exportButton")}
        </button>
      </section>

      <section
        className="card"
        style={{ marginTop: "1.25rem", borderColor: "var(--danger)" }}
        aria-labelledby="offboard-h"
      >
        <h2 id="offboard-h" style={{ marginTop: 0, color: "var(--danger)" }}>
          {t("offboardTitle")}
        </h2>
        <p className="error" role="note">
          {t("offboardWarn")}
        </p>
        {org?.offboarding_requested_at ? (
          <>
            <p data-testid="offboarding-requested">
              {t("offboardingRequestedAt")}:{" "}
              <strong>{fmtDateTime(org.offboarding_requested_at)}</strong>
            </p>
            <button type="button" className="secondary" disabled={busy} onClick={onCancel}>
              {t("cancelOffboarding")}
            </button>
          </>
        ) : (
          org && (
            <form className="stack" onSubmit={onRequest}>
              <label className="field">
                {t("reason")}
                <textarea
                  className="wide"
                  rows={3}
                  maxLength={1000}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  required
                />
              </label>
              <label className="field">
                {t("currentPassword")}
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </label>
              <label className="inline">
                <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
                {t("confirmIrreversible")}
              </label>
              <button type="submit" className="danger" disabled={busy || !ack}>
                {t("requestOffboarding")}
              </button>
            </form>
          )
        )}
      </section>
    </main>
  );
}

export default function DataPage() {
  return (
    <AppShell active="data">
      <DataBody />
    </AppShell>
  );
}
