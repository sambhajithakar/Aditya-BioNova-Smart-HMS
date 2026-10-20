"use client";

/**
 * Accept a clinic invitation (/accept-invite?token=…). New e-mail addresses
 * create an account (full name + password); existing accounts confirm with
 * their current password. Success signs the user in via /api/session.
 */
import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { acceptInvite } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { PASSWORD_MAX } from "@/lib/password";
import { PublicShell, authErrorMessage } from "@/components/PublicShell";

function AcceptForm() {
  const { t } = useLang();
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [existing, setExisting] = useState(false);
  const [fullName, setFullName] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    if (!existing && pw.length < 10) return setError(t("passwordPolicy"));
    setBusy(true);
    setError(null);
    try {
      await acceptInvite({
        token,
        password: pw,
        ...(existing ? {} : { full_name: fullName.trim() }),
      });
      router.replace("/dashboard");
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
  return (
    <form className="stack" onSubmit={onSubmit}>
      <fieldset style={{ border: 0, padding: 0, display: "grid", gap: "0.4rem" }}>
        <label>
          <input type="radio" checked={!existing} onChange={() => setExisting(false)} />{" "}
          {t("inviteNewAccount")}
        </label>
        <label>
          <input type="radio" checked={existing} onChange={() => setExisting(true)} />{" "}
          {t("inviteExistingAccount")}
        </label>
      </fieldset>
      {!existing && (
        <label className="field">
          {t("fullName")}
          <input
            type="text"
            autoComplete="name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
          />
        </label>
      )}
      <label className="field">
        {existing ? t("password") : t("newPassword")}
        <input
          type="password"
          autoComplete={existing ? "current-password" : "new-password"}
          maxLength={PASSWORD_MAX}
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          required
        />
      </label>
      {!existing && <p className="muted">{t("passwordPolicy")}</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button type="submit" className="primary" disabled={busy}>
        {t("acceptInvitation")}
      </button>
    </form>
  );
}

export default function AcceptInvitePage() {
  const { t } = useLang();
  return (
    <PublicShell>
      <h1 style={{ marginTop: 0 }}>{t("acceptInvitation")}</h1>
      <Suspense fallback={null}>
        <AcceptForm />
      </Suspense>
    </PublicShell>
  );
}
