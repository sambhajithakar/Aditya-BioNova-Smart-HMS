/**
 * Browser-side session state (H19).
 *
 * - The ACCESS token lives only in module memory (never localStorage), so a
 *   page reload drops it and it is re-minted from the refresh cookie.
 * - The REFRESH token never reaches JavaScript: it sits in an httpOnly,
 *   SameSite=Strict cookie scoped to Path=/api/session and is only used by
 *   the Next route handlers under app/api/session/*.
 * - Refresh is single-flight inside a tab and serialised across tabs with the
 *   Web Locks API when available (the backend rotates refresh tokens and
 *   treats a replayed one as theft, so two tabs must never race).
 * - A proactive refresh is scheduled shortly before `expires_in` elapses.
 */

export type SessionPayload = {
  access_token: string;
  expires_in: number;
};

import { reportNetworkFailure } from "./connectivity";

type FetchLike = typeof fetch;

let accessToken: string | null = null;
let expiresAt = 0;
let refreshTimer: ReturnType<typeof setTimeout> | null = null;
let inflight: Promise<boolean> | null = null;
let fetchImpl: FetchLike | null = null;
const authFailureListeners = new Set<() => void>();

/** Seconds before expiry at which the proactive refresh fires. */
export const REFRESH_LEEWAY_SECONDS = 60;

function doFetch(input: RequestInfo | URL, init?: RequestInit) {
  return (fetchImpl ?? fetch)(input, init);
}

/** Test hook: swap the fetch implementation (null restores the global). */
export function __setFetchForTests(f: FetchLike | null): void {
  fetchImpl = f;
}

export function getAccessToken(): string | null {
  if (accessToken && Date.now() >= expiresAt) return null;
  return accessToken;
}

export function hasLiveAccessToken(): boolean {
  return getAccessToken() !== null;
}

function scheduleRefresh(expiresInSeconds: number): void {
  if (refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = null;
  if (typeof window === "undefined") return;
  const delayMs = Math.max(5, expiresInSeconds - REFRESH_LEEWAY_SECONDS) * 1000;
  refreshTimer = setTimeout(() => {
    void refreshSession();
  }, delayMs);
}

export function setSession(payload: SessionPayload): void {
  accessToken = payload.access_token;
  expiresAt = Date.now() + payload.expires_in * 1000;
  scheduleRefresh(payload.expires_in);
}

export function clearSession(): void {
  accessToken = null;
  expiresAt = 0;
  if (refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = null;
}

export function onAuthFailure(listener: () => void): () => void {
  authFailureListeners.add(listener);
  return () => authFailureListeners.delete(listener);
}

export function notifyAuthFailure(): void {
  clearSession();
  for (const l of authFailureListeners) l();
}

// M7.1: the API answers 403 {"detail": "mfa_enrollment_required"} to members
// whose role is under the organisation's MFA policy until they enrol. The
// shell listens and sends them to /settings/security.
const mfaEnrollmentListeners = new Set<() => void>();

export function onMfaEnrollmentRequired(listener: () => void): () => void {
  mfaEnrollmentListeners.add(listener);
  return () => mfaEnrollmentListeners.delete(listener);
}

export function notifyMfaEnrollmentRequired(): void {
  for (const l of mfaEnrollmentListeners) l();
}

// Something that /auth/me reports changed (e.g. MFA was just enabled, the
// org profile or MFA policy was saved): the shell re-reads /auth/me.
const meChangedListeners = new Set<() => void>();

export function onMeChanged(listener: () => void): () => void {
  meChangedListeners.add(listener);
  return () => meChangedListeners.delete(listener);
}

export function notifyMeChanged(): void {
  for (const l of meChangedListeners) l();
}

async function refreshOnce(): Promise<boolean> {
  try {
    const res = await doFetch("/api/session/refresh", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    if (!res.ok) {
      clearSession();
      return false;
    }
    const data = (await res.json()) as SessionPayload;
    setSession(data);
    return true;
  } catch {
    reportNetworkFailure(); // network down, not a dead session (lib/connectivity.ts)
    return false;
  }
}

/**
 * Exchange the refresh cookie for a new access token. Concurrent callers in
 * the same tab share one request; other tabs wait on a Web Lock.
 */
export function refreshSession(): Promise<boolean> {
  if (inflight) return inflight;
  const locks =
    typeof navigator !== "undefined" &&
    (navigator as Navigator & { locks?: LockManager }).locks;
  const run = locks
    ? (locks.request("hms-session-refresh", () => refreshOnce()) as unknown as Promise<boolean>)
    : refreshOnce();
  inflight = run.finally(() => {
    inflight = null;
  });
  return inflight;
}

/** Return a usable access token, refreshing from the cookie if needed. */
export async function ensureAccessToken(): Promise<string | null> {
  const t = getAccessToken();
  if (t) return t;
  const ok = await refreshSession();
  return ok ? getAccessToken() : null;
}
