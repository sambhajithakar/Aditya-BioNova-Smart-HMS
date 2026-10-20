"use client";

/**
 * Sign-in with an optional second step: when the backend answers
 * `mfa_required`, the user enters a 6-digit TOTP code or a recovery code.
 * Tokens never touch localStorage — /api/session/login sets the httpOnly
 * refresh cookie and returns only the access token (kept in memory).
 */
import Link from "next/link";
import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { MfaChallenge, login, verifyMfa } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { PublicShell, authErrorMessage } from "@/components/PublicShell";
import { safeNext } from "@/lib/safe-next";

function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const { t } = useLang();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [slug, setSlug] = useState("");
  const [challenge, setChallenge] = useState<MfaChallenge | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const done = () => router.replace(safeNext(search.get("next")));
  // Perf: fetch the post-login page's payload + code while the user types.
  const nextPath = safeNext(search.get("next"));
  useEffect(() => {
    router.prefetch(nextPath);
  }, [router, nextPath]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      const r = await login({ email, password, organization_slug: slug || undefined });
      if (r.kind === "mfa") {
        setChallenge(r.challenge);
        setPassword("");
      } else {
        done();
      }
    } catch (err) {
      setError(authErrorMessage(err, t));
    } finally {
      setBusy(false);
    }
  }

  async function onVerify(e: FormEvent) {
    e.preventDefault();
    if (busy || !challenge) return;
    setError(null);
    setBusy(true);
    try {
      await verifyMfa(challenge.mfa_token, code.trim());
      done();
    } catch (err) {
      setError(authErrorMessage(err, t));
    } finally {
      setBusy(false);
    }
  }

  if (challenge) {
    return (
      <>
        <h1 style={{ marginTop: 0 }}>{t("mfaTitle")}</h1>
        <p className="muted">{t("mfaPrompt")}</p>
        <form className="stack" onSubmit={onVerify}>
          <label className="field">
            {t("mfaCode")}
            <input
              type="text"
              inputMode="text"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              pattern="^(\d{6}|[A-Za-z0-9]{4}-[A-Za-z0-9]{4})$"
              title={t("mfaCodeHint")}
              required
              autoFocus
            />
          </label>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button className="primary" type="submit" disabled={busy}>
            {busy ? "…" : t("verify")}
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setChallenge(null);
              setCode("");
              setError(null);
            }}
          >
            {t("back")}
          </button>
        </form>
      </>
    );
  }

  return (
    <>
      <h1 style={{ marginTop: 0 }}>{t("signIn")}</h1>
      <form className="stack" onSubmit={onSubmit}>
        <label className="field">
          {t("email")}
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
            required
          />
        </label>
        <label className="field">
          {t("password")}
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        <label className="field">
          {t("clinicSlug")}
          <input
            type="text"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="sunrise-clinic"
          />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "…" : t("signIn")}
        </button>
      </form>
      <p style={{ marginTop: "1.25rem" }}>
        <Link href="/forgot-password">{t("forgotPassword")}</Link>
      </p>
    </>
  );
}

export default function LoginPage() {
  return (
    <PublicShell>
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </PublicShell>
  );
}
