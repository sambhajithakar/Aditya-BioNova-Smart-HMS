"use client";

/** Set a new password from an e-mailed reset link (/reset-password?token=…). */
import Link from "next/link";
import { FormEvent, Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { PASSWORD_MAX, PASSWORD_MIN, passwordProblem } from "@/lib/password";
import { PublicShell, authErrorMessage } from "@/components/PublicShell";

function ResetForm() {
  const { t } = useLang();
  const token = useSearchParams().get("token") ?? "";
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    const problem = passwordProblem(pw, confirm);
    if (problem) return setError(t(problem));
    setBusy(true);
    setError(null);
    try {
      await api.publicPost("/auth/password/reset", { token, new_password: pw });
      setDone(true);
      setPw("");
      setConfirm("");
    } catch (err) {
      setError(authErrorMessage(err, t));
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <p className="error" role="alert">
        {t("linkInvalid")}
      </p>
    );
  }
  if (done) {
    return (
      <>
        <p className="notice" role="status">
          {t("passwordResetDone")}
        </p>
        <Link href="/login">{t("backToSignIn")}</Link>
      </>
    );
  }
  return (
    <form className="stack" onSubmit={onSubmit}>
      <label className="field">
        {t("newPassword")}
        <input
          type="password"
          autoComplete="new-password"
          minLength={PASSWORD_MIN}
          maxLength={PASSWORD_MAX}
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          required
        />
      </label>
      <label className="field">
        {t("confirmPassword")}
        <input
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          required
        />
      </label>
      <p className="muted">{t("passwordPolicy")}</p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button type="submit" className="primary" disabled={busy}>
        {t("resetPassword")}
      </button>
    </form>
  );
}

export default function ResetPasswordPage() {
  const { t } = useLang();
  return (
    <PublicShell>
      <h1 style={{ marginTop: 0 }}>{t("resetPassword")}</h1>
      <Suspense fallback={null}>
        <ResetForm />
      </Suspense>
    </PublicShell>
  );
}
