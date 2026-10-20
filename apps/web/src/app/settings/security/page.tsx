"use client";

/**
 * Account security: TOTP MFA (enroll → enable → one-time recovery codes →
 * disable), password change, and the active-session list with revoke /
 * revoke-others. Endpoints per the M7 contract.
 */
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ApiError, MfaStatus, SessionInfo, TotpSetup, api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { useInFlight } from "@/lib/idempotency";
import { PASSWORD_MAX, PASSWORD_MIN, passwordProblem } from "@/lib/password";


function msg(err: unknown, fallback: string): string {
  return err instanceof ApiError && typeof err.detail === "string" ? err.detail : fallback;
}

function SecurityBody() {
  const { t } = useLang();
  const { busy, run } = useInFlight();
  const [status, setStatus] = useState<MfaStatus | null>(null);
  const [setup, setSetup] = useState<TotpSetup | null>(null);
  const [enableCode, setEnableCode] = useState("");
  const [recovery, setRecovery] = useState<string[] | null>(null);
  const [disablePw, setDisablePw] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [pw, setPw] = useState({ current: "", next: "", confirm: "" });
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, list] = await Promise.all([
        api.get<MfaStatus>("/auth/mfa/status"),
        api.get<SessionInfo[]>("/auth/sessions"),
      ]);
      setStatus(s);
      setSessions(list);
    } catch (err) {
      setError(msg(err, t("loadFailed")));
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const act = (fn: () => Promise<void>) =>
    run(async () => {
      setError(null);
      setNotice(null);
      try {
        await fn();
      } catch (err) {
        setError(msg(err, t("actionFailed")));
      }
    });

  const startSetup = () =>
    act(async () => {
      setSetup(await api.post<TotpSetup>("/auth/mfa/totp/setup", {}));
      setEnableCode("");
    });

  const enable = (e: FormEvent) => {
    e.preventDefault();
    return act(async () => {
      const r = await api.post<{ recovery_codes: string[] }>("/auth/mfa/totp/enable", {
        code: enableCode.trim(),
      });
      setRecovery(r.recovery_codes);
      setSetup(null);
      setEnableCode("");
      setNotice(t("mfaEnabled"));
      await load();
    });
  };

  const disable = (e: FormEvent) => {
    e.preventDefault();
    return act(async () => {
      await api.post("/auth/mfa/disable", { password: disablePw, code: disableCode.trim() });
      setDisablePw("");
      setDisableCode("");
      setNotice(t("mfaDisabled"));
      await load();
    });
  };

  const changePassword = (e: FormEvent) => {
    e.preventDefault();
    const problem = passwordProblem(pw.next, pw.confirm);
    if (problem) {
      setError(t(problem));
      return;
    }
    return act(async () => {
      await api.post("/auth/password/change", {
        current_password: pw.current,
        new_password: pw.next,
      });
      setPw({ current: "", next: "", confirm: "" });
      setNotice(t("passwordChanged"));
      await load();
    });
  };

  const revoke = (id: string) =>
    act(async () => {
      await api.post(`/auth/sessions/${id}/revoke`, {});
      await load();
    });

  const revokeOthers = () =>
    act(async () => {
      const r = await api.post<{ revoked: number }>("/auth/sessions/revoke-others", {});
      setNotice(`${t("sessionsRevoked")}: ${r.revoked}`);
      await load();
    });

  return (
    <main className="page">
      <h1 style={{ marginTop: 0 }}>{t("security")}</h1>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="notice" aria-live="polite">
          {notice}
        </p>
      )}

      <section className="card">
        <h2 style={{ marginTop: 0 }}>{t("mfaTitle")}</h2>
        {status && (
          <p>
            {t("status")}:{" "}
            <strong>{status.totp_enabled ? t("enabled") : t("disabled")}</strong>
            {status.totp_enabled && (
              <>
                {" "}
                · {t("recoveryRemaining")}: {status.recovery_codes_remaining}
              </>
            )}
          </p>
        )}

        {recovery && (
          <div className="notice" role="status">
            <p>
              <strong>{t("recoveryCodesTitle")}</strong>
            </p>
            <p>{t("recoveryCodesOnce")}</p>
            <ul className="codes" data-testid="recovery-codes">
              {recovery.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
            <button type="button" className="secondary" onClick={() => setRecovery(null)}>
              {t("savedCodes")}
            </button>
          </div>
        )}

        {status && !status.totp_enabled && !setup && (
          <button type="button" className="primary" disabled={busy} onClick={() => void startSetup()}>
            {t("mfaSetup")}
          </button>
        )}

        {setup && (
          <form className="stack" onSubmit={enable}>
            <p>{t("mfaScanHint")}</p>
            <div className="field">
              <span>{t("otpauthUri")}</span>
              <code className="secret" data-testid="otpauth-uri">
                {setup.otpauth_uri}
              </code>
            </div>
            <div className="field">
              <span>{t("mfaSecret")}</span>
              <code className="secret" data-testid="totp-secret">
                {setup.secret}
              </code>
            </div>
            <label className="field">
              {t("mfaCode")}
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="^\d{6}$"
                value={enableCode}
                onChange={(e) => setEnableCode(e.target.value)}
                required
              />
            </label>
            <div className="row">
              <button type="submit" className="primary" disabled={busy}>
                {t("mfaEnable")}
              </button>
              <button type="button" className="secondary" onClick={() => setSetup(null)}>
                {t("cancel")}
              </button>
            </div>
          </form>
        )}

        {status?.totp_enabled && (
          <form className="stack" onSubmit={disable}>
            <h3 style={{ marginBottom: 0 }}>{t("mfaDisable")}</h3>
            <label className="field">
              {t("password")}
              <input
                type="password"
                autoComplete="current-password"
                value={disablePw}
                onChange={(e) => setDisablePw(e.target.value)}
                required
              />
            </label>
            <label className="field">
              {t("mfaCode")}
              <input
                type="text"
                autoComplete="one-time-code"
                value={disableCode}
                onChange={(e) => setDisableCode(e.target.value)}
                required
              />
            </label>
            <button type="submit" className="danger" disabled={busy}>
              {t("mfaDisable")}
            </button>
          </form>
        )}
      </section>

      <section className="card" style={{ marginTop: "1.25rem" }}>
        <h2 style={{ marginTop: 0 }}>{t("changePassword")}</h2>
        <form className="stack" onSubmit={changePassword}>
          <label className="field">
            {t("currentPassword")}
            <input
              type="password"
              autoComplete="current-password"
              value={pw.current}
              onChange={(e) => setPw({ ...pw, current: e.target.value })}
              required
            />
          </label>
          <label className="field">
            {t("newPassword")}
            <input
              type="password"
              autoComplete="new-password"
              minLength={PASSWORD_MIN}
              maxLength={PASSWORD_MAX}
              value={pw.next}
              onChange={(e) => setPw({ ...pw, next: e.target.value })}
              required
            />
          </label>
          <label className="field">
            {t("confirmPassword")}
            <input
              type="password"
              autoComplete="new-password"
              value={pw.confirm}
              onChange={(e) => setPw({ ...pw, confirm: e.target.value })}
              required
            />
          </label>
          <p className="muted">{t("passwordPolicy")}</p>
          <button type="submit" className="primary" disabled={busy}>
            {t("changePassword")}
          </button>
        </form>
      </section>

      <section className="card" style={{ marginTop: "1.25rem" }}>
        <h2 style={{ marginTop: 0 }}>{t("activeSessions")}</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t("device")}</th>
                <th scope="col">{t("ipAddress")}</th>
                <th scope="col">{t("signedInAt")}</th>
                <th scope="col">{t("expiresAt")}</th>
                <th scope="col">{t("actions")}</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.id}>
                  <td>
                    {s.user_agent || "—"}{" "}
                    {s.current && <span className="tag">{t("thisDevice")}</span>}
                  </td>
                  <td>{s.ip_address || "—"}</td>
                  <td>{new Date(s.created_at).toLocaleString()}</td>
                  <td>{new Date(s.expires_at).toLocaleString()}</td>
                  <td>
                    {!s.current && (
                      <button
                        type="button"
                        className="danger"
                        disabled={busy}
                        onClick={() => void revoke(s.id)}
                      >
                        {t("revoke")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {sessions.length === 0 && (
                <tr>
                  <td colSpan={5} className="muted">
                    —
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <button
          type="button"
          className="secondary"
          style={{ marginTop: "0.75rem" }}
          disabled={busy || sessions.filter((s) => !s.current).length === 0}
          onClick={() => void revokeOthers()}
        >
          {t("revokeOthers")}
        </button>
      </section>
    </main>
  );
}

export default function SecurityPage() {
  return (
    <AppShell active="security">
      <SecurityBody />
    </AppShell>
  );
}
