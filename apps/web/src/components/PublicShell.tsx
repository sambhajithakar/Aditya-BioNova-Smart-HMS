"use client";

/** Header + language switch for unauthenticated pages (login, reset, invite). */
import { ReactNode } from "react";
import { LANGS } from "@/lib/i18n";
import { useLang } from "@/lib/lang";

export function PublicShell({ children }: { children: ReactNode }) {
  const { lang, setLang, t } = useLang();
  return (
    <>
      <header className="app-header">
        <span className="brand">{t("brand")}</span>
        <span className="spacer" />
        <span className="lang-switch" role="group" aria-label="Language">
          {LANGS.map((l) => (
            <button
              key={l.code}
              type="button"
              aria-pressed={lang === l.code}
              onClick={() => setLang(l.code)}
            >
              {l.native}
            </button>
          ))}
        </span>
      </header>
      <main className="page">
        <div className="card narrow">{children}</div>
      </main>
    </>
  );
}

/** Map an ApiError-ish failure to a translated, user-facing message. */
export function authErrorMessage(
  err: unknown,
  t: (k: string) => string,
): string {
  const e = err as { status?: number; retryAfter?: number | null; detail?: unknown };
  if (e?.status === 429) {
    return e.retryAfter
      ? `${t("tooManyAttempts")} (${e.retryAfter}s)`
      : t("tooManyAttempts");
  }
  if (e?.status === 401) return t("invalidCredentials");
  if (e?.status === 409) return typeof e.detail === "string" ? e.detail : t("multipleClinics");
  if (e?.status === 422) return t("checkInput");
  if (typeof e?.detail === "string" && e.status && e.status < 500) return e.detail;
  return t("serverUnavailable");
}
