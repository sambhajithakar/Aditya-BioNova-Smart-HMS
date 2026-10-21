"use client";

/**
 * Small, always-loaded parts of the authenticated shell:
 *  - <QuickSearch>        header patient search (desktop input, phone icon)
 *  - <ConnectivityBanner> Online / Reconnecting / Offline (+ health probes)
 * The heavier phone/desktop chrome (bottom bar, More sheet, shortcuts, SW
 * update toast) is ./DeviceChrome.tsx, loaded lazily by the shell.
 */
import { FormEvent, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useLang } from "@/lib/lang";
import { requestPatientSearch } from "@/lib/quick-search";
import { dispatchConn, getConn, probeHealth, probeInterval, subscribeConn } from "@/lib/connectivity";
import { NavIcon } from "./icons";
import { useConnectivity } from "./online";

export const QUICK_SEARCH_ID = "quick-search";

// ---------------------------------------------------------------- search ---
export function QuickSearch() {
  const { t } = useLang();
  const router = useRouter();
  const pathname = usePathname();
  const [q, setQ] = useState("");

  function go(term: string) {
    requestPatientSearch(term);
    if (pathname !== "/patients") router.push("/patients");
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    go(q);
    setQ("");
  }

  return (
    <>
      <form role="search" className="quick-search" onSubmit={onSubmit} aria-label={t("devQuickSearch")}>
        <label htmlFor={QUICK_SEARCH_ID} className="sr-only">
          {t("devQuickSearch")}
        </label>
        <input
          id={QUICK_SEARCH_ID}
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("devQuickSearchHint")}
          autoComplete="off"
          enterKeyHint="search"
          data-testid="quick-search"
        />
        <button type="submit" className="on-dark">
          {t("devGo")}
        </button>
      </form>
      <button
        type="button"
        className="on-dark icon-only quick-search-phone"
        onClick={() => go("")}
        aria-label={t("devSearchPatients")}
        data-testid="quick-search-phone"
      >
        <NavIcon name="search" />
      </button>
    </>
  );
}

// ---------------------------------------------------------- connectivity ---
export function ConnectivityBanner() {
  const { t } = useLang();
  const status = useConnectivity();
  const [flash, setFlash] = useState(false);
  const prev = useRef(status);

  // Browser events + an adaptive probe loop (60 s healthy, 5 s in trouble).
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;
    const schedule = () => {
      if (timer) clearTimeout(timer);
      if (stopped) return;
      timer = setTimeout(async () => {
        if (document.visibilityState === "visible") await probeHealth();
        schedule();
      }, probeInterval(getConn()));
    };
    const onOffline = () => dispatchConn("browserOffline");
    const onOnline = () => {
      dispatchConn("browserOnline");
      void probeHealth();
    };
    const onVisible = () => {
      if (document.visibilityState === "visible" && getConn().status !== "online") void probeHealth();
    };
    if (typeof navigator !== "undefined" && navigator.onLine === false) onOffline();
    window.addEventListener("offline", onOffline);
    window.addEventListener("online", onOnline);
    document.addEventListener("visibilitychange", onVisible);
    const off = subscribeConn(() => schedule()); // re-arm with the new cadence
    schedule();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      off();
      window.removeEventListener("offline", onOffline);
      window.removeEventListener("online", onOnline);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  useEffect(() => {
    if (prev.current !== "online" && status === "online") {
      setFlash(true);
      const id = setTimeout(() => setFlash(false), 3000);
      prev.current = status;
      return () => clearTimeout(id);
    }
    prev.current = status;
  }, [status]);

  if (status === "online" && !flash) return <div className="sr-only" role="status" aria-live="polite" />;
  const cls = status === "offline" ? "danger" : status === "reconnecting" ? "warn" : "";
  return (
    <div
      className={`shell-banner conn-banner ${cls}`}
      role="status"
      aria-live="polite"
      data-testid="connectivity"
      data-status={status}
    >
      {status === "offline" && t("devOffline")}
      {status === "reconnecting" && t("devReconnecting")}
      {status === "online" && t("devBackOnline")}
      {status !== "online" && (
        <>
          {" "}
          <button type="button" className="link-button" onClick={() => void probeHealth()}>
            {t("devRetryNow")}
          </button>
        </>
      )}
    </div>
  );
}

