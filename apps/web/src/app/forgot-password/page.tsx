"use client";

/**
 * Request a password-reset link. The API always answers 202 so the page
 * never reveals whether an account exists.
 */
import Link from "next/link";
import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { PublicShell, authErrorMessage } from "@/components/PublicShell";

export default function ForgotPasswordPage() {
  const { t } = useLang();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.publicPost("/auth/password/forgot", { email });
      setSent(true);
    } catch (err) {
      setError(authErrorMessage(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <PublicShell>
      <h1 style={{ marginTop: 0 }}>{t("forgotPassword")}</h1>
      {sent ? (
        <p className="notice" role="status">
          {t("resetLinkSent")}
        </p>
      ) : (
        <form className="stack" onSubmit={onSubmit}>
          <p className="muted">{t("forgotPasswordHint")}</p>
          <label className="field">
            {t("email")}
            <input
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="primary" disabled={busy}>
            {t("sendResetLink")}
          </button>
        </form>
      )}
      <p style={{ marginTop: "1.25rem" }}>
        <Link href="/login">{t("backToSignIn")}</Link>
      </p>
    </PublicShell>
  );
}
