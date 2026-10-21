/**
 * Connectivity state for the shell banner and for disabling server-finalised
 * actions (payments, refunds, prescription signing) while offline.
 *
 * Decision (documented in docs/DEVICE_COMPATIBILITY.md): the WEB app does
 * NOT do offline writes. A payment or a signed prescription is only real
 * once the server has accepted it, so those buttons are disabled while the
 * connection is down instead of queueing work in the browser (which would
 * also mean storing patient data in browser storage). Offline capture with
 * an encrypted outbox is the Android app's job.
 *
 * Inputs: navigator.onLine events, the API client reporting network-level
 * fetch failures / successes, and a periodic probe of GET /api/v1/health
 * (liveness; unauthenticated, no patient data).
 */

export type Connectivity = "online" | "reconnecting" | "offline";

export type ConnEvent =
  | "browserOffline"
  | "browserOnline"
  | "fetchFailed"
  | "fetchOk"
  | "probeFailed"
  | "probeOk";

export type ConnState = { status: Connectivity; failures: number };

/** Consecutive probe/fetch failures after which "reconnecting" becomes "offline". */
export const OFFLINE_AFTER_FAILURES = 3;
export const PROBE_INTERVAL_ONLINE_MS = 60_000;
export const PROBE_INTERVAL_TROUBLE_MS = 5_000;
export const HEALTH_PATH = "/api/v1/health";

export const initialConn: ConnState = { status: "online", failures: 0 };

/** Pure transition function (unit-tested). */
export function nextConn(s: ConnState, e: ConnEvent): ConnState {
  switch (e) {
    case "browserOffline":
      return { status: "offline", failures: Math.max(s.failures, OFFLINE_AFTER_FAILURES) };
    case "browserOnline":
      // The OS says we have a link again; confirm with a probe before "online".
      return { status: "reconnecting", failures: 0 };
    case "fetchFailed":
    case "probeFailed": {
      const failures = s.failures + 1;
      return { status: failures >= OFFLINE_AFTER_FAILURES ? "offline" : "reconnecting", failures };
    }
    case "fetchOk":
    case "probeOk":
      return initialConn;
  }
}

/** Probe cadence for a state: slow when healthy, fast while in trouble. */
export function probeInterval(s: ConnState): number {
  return s.status === "online" ? PROBE_INTERVAL_ONLINE_MS : PROBE_INTERVAL_TROUBLE_MS;
}

// ---- tiny store (module singleton; in memory only) -------------------------
let state: ConnState = initialConn;
const listeners = new Set<(s: ConnState) => void>();

export function getConn(): ConnState {
  return state;
}

export function dispatchConn(e: ConnEvent): void {
  const next = nextConn(state, e);
  if (next.status === state.status && next.failures === state.failures) return;
  state = next;
  for (const l of listeners) l(state);
}

export function subscribeConn(l: (s: ConnState) => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** Test hook. */
export function __resetConnForTests(): void {
  state = initialConn;
  listeners.clear();
}

/** Called by the API client: a fetch threw at the network level. */
export function reportNetworkFailure(): void {
  dispatchConn("fetchFailed");
}

/** Called by the API client: any HTTP response arrived (the server is reachable). */
export function reportNetworkOk(): void {
  if (state.status !== "online") dispatchConn("fetchOk");
}

/** One liveness probe. Any HTTP 2xx from /api/v1/health counts as reachable. */
export async function probeHealth(fetchImpl: typeof fetch = fetch): Promise<boolean> {
  try {
    const res = await fetchImpl(HEALTH_PATH, { method: "GET", cache: "no-store", credentials: "omit" });
    dispatchConn(res.ok ? "probeOk" : "probeFailed");
    return res.ok;
  } catch {
    dispatchConn("probeFailed");
    return false;
  }
}
