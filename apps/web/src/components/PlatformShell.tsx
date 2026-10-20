"use client";

/**
 * Platform (vendor) console shell — M7.1. Deliberately looks different from
 * a clinic (darker header, teal rule, "Platform console" badge, its own nav)
 * so an operator never confuses it with a tenant workspace. Rendered only
 * for /auth/me.is_platform_admin; the API enforces the same (plus MFA).
 */
import Link from "next/link";
import { ReactNode, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Me, api, logout } from "@/lib/api";
import { LANGS } from "@/lib/i18n";
import { useLang } from "@/lib/lang";
import { MeContext } from "@/lib/me";
import { onAuthFailure, onMfaEnrollmentRequired } from "@/lib/session";
import { MFA_SETUP_PATH, mfaRedirectTarget } from "@/lib/saas";

const PLATFORM_NAV = [
  { key: "overview", label: "platformOverview", href: "/platform" },
  { key: "plans", label: "platformPlans", href: "/platform/plans" },
  { key: "billing", label: "platformBilling", href: "/platform/billing" },
  { key: "support", label: "platformSupport", href: "/platform/support" },
];

export function PlatformShell({ children, active }: { children: ReactNode; active: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const { lang, setLang, t } = useLang();
  const [me, setMe] = useState<Me | null>(null);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    const goLogin = () =>
      router.replace(`/login?next=${encodeURIComponent(pathname || "/platform")}`);
    const off = onAuthFailure(goLogin);
    const offMfa = onMfaEnrollmentRequired(() =>
      router.replace(`${MFA_SETUP_PATH}?mfa=required`),
    );
    let cancelled = false;
    api
      .get<Me>("/auth/me")
      .then((m) => {
        if (cancelled) return;
        const target = mfaRedirectTarget(m, pathname);
        if (target) router.replace(target);
        else setMe(m);
      })
      .catch(() => {
        if (!cancelled) goLogin();
      });
    return () => {
      cancelled = true;
      off();
      offMfa();
    };
  }, [router, pathname]);

  async function signOut() {
    setSigningOut(true);
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  }

  return (
    <MeContext.Provider value={me}>
      <header className="app-header platform">
        <span className="brand">{t("platformConsole")}</span>
        <span className="platform-badge" data-testid="platform-badge">
          {t("platformBadge")}
        </span>
        {me && <span className="context">{me.user.email}</span>}
        <span className="spacer" />
        <Link className="header-link" href="/dashboard">
          {t("backToClinic")}
        </Link>
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
        <button
          className="on-dark"
          type="button"
          onClick={() => void signOut()}
          disabled={signingOut}
          data-testid="logout"
        >
          {t("logout")}
        </button>
      </header>
      <nav className="layout-nav platform" aria-label={t("platformConsole")}>
        {me?.is_platform_admin &&
          PLATFORM_NAV.map((n) => (
            <Link
              key={n.key}
              href={n.href}
              className={n.key === active ? "active" : undefined}
              aria-current={n.key === active ? "page" : undefined}
            >
              {t(n.label)}
            </Link>
          ))}
      </nav>
      {!me ? (
        <main className="page">
          <p className="muted" aria-live="polite">
            {t("loading")}
          </p>
        </main>
      ) : !me.is_platform_admin ? (
        <main className="page">
          <p className="error" role="alert">
            {t("platformNotAdmin")}
          </p>
        </main>
      ) : (
        children
      )}
    </MeContext.Provider>
  );
}
