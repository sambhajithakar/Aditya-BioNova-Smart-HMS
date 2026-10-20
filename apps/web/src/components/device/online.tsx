"use client";

/**
 * useOnline(): false only when the shell has decided the app is OFFLINE
 * (navigator offline, or repeated failed requests/health probes). Pages use
 * it to disable server-finalised actions — payments, refunds, signing a
 * prescription — because the web app never queues those offline.
 */
import { useEffect, useState } from "react";
import { Connectivity, getConn, subscribeConn } from "@/lib/connectivity";
import { useLang } from "@/lib/lang";

export function useConnectivity(): Connectivity {
  const [status, setStatus] = useState<Connectivity>("online");
  useEffect(() => {
    setStatus(getConn().status);
    return subscribeConn((s) => setStatus(s.status));
  }, []);
  return status;
}

export function useOnline(): boolean {
  return useConnectivity() !== "offline";
}

/** Inline explanation shown next to disabled server-finalised actions. */
export function NeedsConnection() {
  const online = useOnline();
  const { t } = useLang();
  if (online) return null;
  return (
    <p className="warn-box needs-connection" role="status" data-testid="needs-connection">
      {t("devNeedsConnection")}
    </p>
  );
}
