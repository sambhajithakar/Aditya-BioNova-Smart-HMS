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
 *
 * M7.1: nav items whose feature is not in the tenant's edition are hidden
 * too (and such a page renders a "not in your plan" notice); a slim banner
 * shows trial / past-due / read-only / suspended subscriptions; a member who
 * must enrol MFA (me.mfa_enrollment_required, or any API 403
 * "mfa_enrollment_required") is sent to /settings/security.
 */
import Link from "next/link";
import { ReactNode, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Me, api, logout } from "@/lib/api";
import { onAuthFailure, onMeChanged, onMfaEnrollmentRequired } from "@/lib/session";
import { LANGS } from "@/lib/i18n";
import { useLang } from "@/lib/lang";
import { MeContext, hasPermission } from "@/lib/me";
import { NAV, navLabel } from "@/lib/nav";
import {
  MFA_SETUP_PATH,
  hasFeature,
  mfaRedirectTarget,
  subscriptionBanner,
  visibleNav,
} from "@/lib/saas";

export { NAV };

const BANNER_KEY: Record<string, string> = {
  trialing: "bannerTrialing",
  past_due: "bannerPastDue",
  read_only: "bannerReadOnly",
  suspended: "bannerSuspended",
  cancelled: "bannerCancelled",
};

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
  const [mfaForced, setMfaForced] = useState(false);

  useEffect(() => {
    const goLogin = () =>
      router.replace(`/login?next=${encodeURIComponent(pathname || "/dashboard")}`);
    const off = onAuthFailure(goLogin);
    const offMfa = onMfaEnrollmentRequired(() => {
      setMfaForced(true);
      if (pathname !== MFA_SETUP_PATH) router.replace(`${MFA_SETUP_PATH}?mfa=required`);
    });
    if (typeof window !== "undefined" && /[?&]mfa=required\b/.test(window.location.search)) {
      setMfaForced(true);
    }
    let cancelled = false;
    const loadMe = (initial: boolean) =>
      api
        .get<Me>("/auth/me")
        .then((m) => {
          if (cancelled) return;
          const target = mfaRedirectTarget(m, pathname);
          if (target) {
            router.replace(target);
            return;
          }
          if (!m.mfa_enrollment_required) setMfaForced(false);
          setMe(m);
        })
        .catch(() => {
          if (!cancelled && initial) goLogin();
        });
    void loadMe(true);
    const offMe = onMeChanged(() => void loadMe(false));
    return () => {
      cancelled = true;
      off();
      offMfa();
      offMe();
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

  const page = NAV.find((n) => n.key === active);
  const allowed = hasPermission(me, page?.perm);
  const entitled = hasFeature(me, page?.feature);
  const mfaRequired = !!me?.mfa_enrollment_required || mfaForced;
  const nav = mfaRequired
    ? NAV.filter((n) => n.key === "security")
    : visibleNav(NAV, me);
  const banner = subscriptionBanner(me);

  return (
    <MeContext.Provider value={me}>
      <header className="app-header">
        <span className="brand">{t("brand")}</span>
        {me && (
          <span className="context">
            {me.organization.name} <span className="muted-on-dark">/</span>{" "}
            {me.user.full_name} <span className="muted-on-dark">({me.role})</span>
            {me.edition && (
              <>
                {" "}
                <span className="edition-pill" data-testid="edition">
                  {me.edition.name}
                </span>
              </>
            )}
          </span>
        )}
        <span className="spacer" />
        {me?.is_platform_admin && !mfaRequired && (
          <Link className="header-link" href="/platform" data-testid="platform-link">
            {t("platformConsole")}
          </Link>
        )}
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
        {nav.map((item) => (
          <Link
            key={item.key}
            href={item.href}
            className={item.key === active ? "active" : undefined}
            aria-current={item.key === active ? "page" : undefined}
          >
            {t(navLabel(item))}
          </Link>
        ))}
      </nav>

      {mfaRequired && (
        <div className="shell-banner danger" role="alert" data-testid="mfa-required-banner">
          <strong>{t("mfaRequiredTitle")}.</strong> {t("mfaRequiredBody")}
        </div>
      )}
      {!mfaRequired && banner && (
        <div
          className={`shell-banner ${banner === "trialing" ? "" : "warn"}`}
          role="status"
          data-testid="subscription-banner"
        >
          {t(BANNER_KEY[banner])}{" "}
          {hasPermission(me, "subscription.read") && (
            <Link href="/settings/subscription">{t("viewSubscription")}</Link>
          )}
        </div>
      )}

      {!me ? (
        <main className="page">
          <p className="muted" aria-live="polite">
            {t("loading")}
          </p>
        </main>
      ) : !allowed ? (
        <main className="page">
          <p className="error" role="alert">
            {t("notPermitted")}
          </p>
        </main>
      ) : !entitled ? (
        <main className="page">
          <p className="notice" role="alert" data-testid="feature-not-in-plan">
            {t("featureNotInPlan")}{" "}
            {hasPermission(me, "subscription.read") && (
              <Link href="/settings/subscription">{t("upgradeHint")}</Link>
            )}
          </p>
        </main>
      ) : (
        children
      )}
    </MeContext.Provider>
  );
}
