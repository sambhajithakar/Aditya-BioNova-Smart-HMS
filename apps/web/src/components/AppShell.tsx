"use client";

/**
 * Shared authenticated shell: header with language switcher + the module
 * navigation.
 *
 * Auth gate (S3): children are NOT rendered until GET /auth/me succeeds, so
 * no page fires protected requests before the session is established. The
 * access token is minted from the httpOnly refresh cookie on first use (see
 * lib/session.ts); if that fails the user is sent to /login.
 *
 * RBAC (S5): nav items the member's permissions don't allow are hidden, and a
 * page whose permission is missing renders a "not permitted" notice instead
 * of firing requests that would 403.
 */
import Link from "next/link";
import { ReactNode, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Me, api, logout } from "@/lib/api";
import { onAuthFailure } from "@/lib/session";
import { LANGS } from "@/lib/i18n";
import { useLang } from "@/lib/lang";
import { MeContext, hasPermission } from "@/lib/me";

export const NAV: { key: string; href: string; perm?: string }[] = [
  { key: "dashboard", href: "/dashboard" },
  { key: "patients", href: "/patients", perm: "patient.read" },
  { key: "appointments", href: "/appointments", perm: "appointment.read" },
  { key: "queue", href: "/queue", perm: "queue.read" },
  { key: "consultation", href: "/consultation", perm: "encounter.read" },
  { key: "billing", href: "/billing", perm: "billing.read" },
  { key: "pharmacy", href: "/pharmacy", perm: "pharmacy.read" },
  { key: "lab", href: "/lab", perm: "lab.read" },
  { key: "ipd", href: "/ipd", perm: "bed.read" },
  { key: "inventory", href: "/inventory", perm: "inventory.read" },
  { key: "expenses", href: "/expenses", perm: "expense.read" },
  { key: "reports", href: "/reports", perm: "report.read" },
  { key: "members", href: "/settings/members", perm: "member.read" },
  { key: "security", href: "/settings/security" },
];

export function AppShell({
  children,
  active,
}: {
  children: ReactNode;
  active: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { lang, setLang, t } = useLang();
  const [me, setMe] = useState<Me | null>(null);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    const goLogin = () =>
      router.replace(`/login?next=${encodeURIComponent(pathname || "/dashboard")}`);
    const off = onAuthFailure(goLogin);
    let cancelled = false;
    api
      .get<Me>("/auth/me")
      .then((m) => {
        if (!cancelled) setMe(m);
      })
      .catch(() => {
        if (!cancelled) goLogin();
      });
    return () => {
      cancelled = true;
      off();
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

  const pagePerm = NAV.find((n) => n.key === active)?.perm;
  const allowed = hasPermission(me, pagePerm);

  return (
    <MeContext.Provider value={me}>
      <header className="app-header">
        <span className="brand">{t("brand")}</span>
        {me && (
          <span className="context">
            {me.organization.name} <span className="muted-on-dark">/</span>{" "}
            {me.user.full_name} <span className="muted-on-dark">({me.role})</span>
          </span>
        )}
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

      <nav className="layout-nav" aria-label="Modules">
        {NAV.filter((item) => hasPermission(me, item.perm)).map((item) => (
          <Link
            key={item.key}
            href={item.href}
            className={item.key === active ? "active" : undefined}
            aria-current={item.key === active ? "page" : undefined}
          >
            {t(item.key)}
          </Link>
        ))}
      </nav>

      {!me ? (
        <main className="page">
          <p className="muted" aria-live="polite">
            {t("loading")}
          </p>
        </main>
      ) : allowed ? (
        children
      ) : (
        <main className="page">
          <p className="error" role="alert">
            {t("notPermitted")}
          </p>
        </main>
      )}
    </MeContext.Provider>
  );
}
