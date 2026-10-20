"use client";

/**
 * Device-adaptive chrome of the authenticated shell, loaded lazily (it is not
 * needed for the first paint and only renders once /auth/me has resolved):
 * phone bottom bar + "More" sheet, keyboard shortcuts, "?" help dialog,
 * idle prefetch of the role's primary modules, and the service-worker update
 * toast. Everything is driven by the already-gated nav list (permission +
 * edition feature), so no gating is bypassed.
 */
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { LANGS } from "@/lib/i18n";
import { useLang } from "@/lib/lang";
import { ShellNavItem, navLabel } from "@/lib/nav";
import { pickBottomNav } from "@/lib/device-nav";
import {
  ChordState,
  initialChord,
  isEditableTarget,
  newTargetSelectors,
  resolveShortcut,
} from "@/lib/shortcuts";
import { requestPatientSearch } from "@/lib/quick-search";
import { applyUpdate, registerServiceWorker } from "@/lib/pwa";
import { NavIcon } from "./icons";
import { QUICK_SEARCH_ID } from "./ShellBits";

const ShortcutsDialog = dynamic(() => import("./ShortcutsDialog"), { ssr: false });

/** Next keeps a full prefetch for 5 minutes; refresh a little before that. */
const PREFETCH_TTL_MS = 4 * 60_000;
const prefetchedAt = new Map<string, number>();

// ------------------------------------------------------- chrome / phones ---
export default function DeviceChrome({
  nav,
  active,
  role,
  onSignOut,
  signingOut,
}: {
  nav: ShellNavItem[];
  active: string;
  role: string | undefined;
  onSignOut: () => void;
  signingOut: boolean;
}) {
  const { t, lang, setLang } = useLang();
  const router = useRouter();
  const pathname = usePathname();
  const [helpOpen, setHelpOpen] = useState(false);
  const [update, setUpdate] = useState<ServiceWorkerRegistration | null>(null);
  const sheetRef = useRef<HTMLDialogElement>(null);
  const chord = useRef<ChordState>(initialChord);
  const { primary, rest } = pickBottomNav(nav, role);
  const hasDashboard = nav.some((n) => n.key === "dashboard");
  const canSearch = nav.some((n) => n.key === "patients");

  // Close the sheet on navigation.
  useEffect(() => {
    if (sheetRef.current?.open) sheetRef.current.close();
  }, [pathname]);

  useEffect(() => {
    void registerServiceWorker((reg) => setUpdate(reg));
  }, []);

  // Perf: when idle, prefetch Home + the role's primary modules (route
  // payload + page chunk) so the most-used navigations skip two round trips.
  // Skipped when the browser asks to save data.
  const prefetchKey = [hasDashboard ? "/dashboard" : "", ...primary.map((p) => p.href)].join(" ");
  useEffect(() => {
    const conn = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
    if (conn?.saveData) return;
    const now = Date.now();
    // Once per route per PREFETCH_TTL_MS: every page mounts its own shell, and
    // re-prefetching on each navigation competed with the page's own requests.
    const hrefs = prefetchKey
      .split(" ")
      .filter((h) => h && h !== pathname && now - (prefetchedAt.get(h) ?? 0) > PREFETCH_TTL_MS);
    if (hrefs.length === 0) return;
    const run = () =>
      hrefs.forEach((h) => {
        prefetchedAt.set(h, Date.now());
        router.prefetch(h);
      });
    const w = window as Window & {
      requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number;
      cancelIdleCallback?: (id: number) => void;
    };
    if (w.requestIdleCallback) {
      const id = w.requestIdleCallback(run, { timeout: 3000 });
      return () => w.cancelIdleCallback?.(id);
    }
    const id = setTimeout(run, 1500);
    return () => clearTimeout(id);
  }, [prefetchKey, pathname, router]);

  const focusSearch = useCallback(() => {
    const el = document.getElementById(QUICK_SEARCH_ID) as HTMLInputElement | null;
    if (el && el.offsetParent !== null) {
      el.focus();
      el.select();
    } else if (canSearch) {
      requestPatientSearch("");
      if (pathname !== "/patients") router.push("/patients");
    }
  }, [canSearch, pathname, router]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.defaultPrevented) return;
      if (document.querySelector("dialog[open]")) return; // a modal owns the keyboard
      const r = resolveShortcut(
        {
          key: e.key,
          ctrlKey: e.ctrlKey,
          metaKey: e.metaKey,
          altKey: e.altKey,
          shiftKey: e.shiftKey,
          editable: isEditableTarget(e.target),
          isComposing: e.isComposing,
          repeat: e.repeat,
        },
        chord.current,
        Date.now(),
      );
      chord.current = r.state;
      const a = r.action;
      if (!a) return;
      if (a.type === "focusSearch") {
        if (!canSearch) return;
        e.preventDefault();
        focusSearch();
      } else if (a.type === "help") {
        e.preventDefault();
        setHelpOpen(true);
      } else if (a.type === "new") {
        const target = newTargetSelectors(pathname)
          .map((sel) => document.querySelector<HTMLElement>(sel))
          .find((el) => !!el && el.offsetParent !== null);
        if (!target) return;
        e.preventDefault();
        target.scrollIntoView({ block: "center" });
        target.focus();
      } else if (a.type === "goto") {
        const item = nav.find((n) => n.key === a.nav);
        if (!item) return; // not permitted / not in plan: do nothing
        e.preventDefault();
        router.push(item.href);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [nav, router, focusSearch, canSearch, pathname]);

  const restActive = rest.some((i) => i.key === active);

  return (
    <>
      <nav className="bottom-nav" aria-label={t("devPrimaryNav")} data-testid="bottom-nav">
        {hasDashboard && (
          <Link
            href="/dashboard"
            prefetch={false}
            className={active === "dashboard" ? "active" : undefined}
            aria-current={active === "dashboard" ? "page" : undefined}
          >
            <NavIcon name="dashboard" />
            <span>{t("devHome")}</span>
          </Link>
        )}
        {primary.map((item) => (
          <Link
            key={item.key}
            href={item.href}
            prefetch={false}
            className={item.key === active ? "active" : undefined}
            aria-current={item.key === active ? "page" : undefined}
          >
            <NavIcon name={item.key} />
            <span>{t(navLabel(item))}</span>
          </Link>
        ))}
        <button
          type="button"
          className={restActive ? "active" : undefined}
          onClick={() => sheetRef.current?.showModal()}
          aria-haspopup="dialog"
          data-testid="nav-more"
        >
          <NavIcon name="more" />
          <span>{t("devMore")}</span>
        </button>
      </nav>

      <dialog
        ref={sheetRef}
        className="sheet-dialog more-sheet"
        aria-labelledby="more-title"
        data-testid="more-sheet"
      >
        <div className="sheet-head">
          <h2 id="more-title">{t("devMoreTitle")}</h2>
          <button type="button" className="secondary" onClick={() => sheetRef.current?.close()}>
            {t("devClose")}
          </button>
        </div>
        <ul className="sheet-links">
          {rest.map((item) => (
            <li key={item.key}>
              <Link
                href={item.href}
                prefetch={false}
                className={item.key === active ? "active" : undefined}
                aria-current={item.key === active ? "page" : undefined}
                onClick={() => sheetRef.current?.close()}
              >
                <NavIcon name={item.key} />
                <span>{t(navLabel(item))}</span>
              </Link>
            </li>
          ))}
        </ul>
        <div className="sheet-foot">
          <Link href="/print/test">{t("devPrinterTestLink")}</Link>
          <span className="lang-switch on-light" role="group" aria-label="Language">
            {LANGS.map((l) => (
              <button key={l.code} type="button" aria-pressed={lang === l.code} onClick={() => setLang(l.code)}>
                {l.native}
              </button>
            ))}
          </span>
          <button
            type="button"
            className="secondary"
            onClick={onSignOut}
            disabled={signingOut}
            data-testid="logout-sheet"
          >
            {t("logout")}
          </button>
        </div>
      </dialog>

      {helpOpen && (
        <ShortcutsDialog onClose={() => setHelpOpen(false)} visibleNavKeys={nav.map((n) => n.key)} />
      )}

      {update && (
        <div className="update-toast" role="status" aria-live="polite" data-testid="sw-update">
          <span>{t("devUpdateAvailable")}</span>
          <button type="button" className="primary" onClick={() => applyUpdate(update)}>
            {t("devReload")}
          </button>
        </div>
      )}
    </>
  );
}
