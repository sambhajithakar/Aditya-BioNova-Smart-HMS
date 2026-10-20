/**
 * Server-only helpers for the /api/session/* route handlers (H19).
 *
 * The browser never sees the refresh token: these handlers call the FastAPI
 * backend server-side, store the refresh token in an httpOnly,
 * SameSite=Strict cookie scoped to Path=/api/session, and return only the
 * access token + user payload. A second, value-less httpOnly cookie
 * (`hms_session`, Path=/) lets middleware.ts tell "has a session" from
 * "anonymous" on page routes, which the path-scoped refresh cookie cannot.
 */
import { NextRequest, NextResponse } from "next/server";

export const REFRESH_COOKIE = "hms_rt";
export const PRESENCE_COOKIE = "hms_session";
const REFRESH_PATH = "/api/session";

export function apiOrigin(): string {
  return process.env.API_ORIGIN || "http://127.0.0.1:8000";
}

function cookieSecure(): boolean {
  const flag = process.env.SESSION_COOKIE_SECURE;
  if (flag === "true") return true;
  if (flag === "false") return false;
  return process.env.NODE_ENV === "production";
}

function cookieMaxAge(): number {
  const n = Number(process.env.SESSION_COOKIE_MAX_AGE);
  return Number.isFinite(n) && n > 0 ? n : 60 * 60 * 24 * 14; // backend default refresh TTL
}

/**
 * CSRF defence in depth on top of SameSite=Strict: state-changing session
 * calls must come from our own origin (Origin header, when the browser sends
 * one, must match the Host we are served on).
 */
export function isSameOrigin(req: NextRequest): boolean {
  const origin = req.headers.get("origin");
  if (!origin) return true; // same-origin fetch from older browsers / curl
  const host = req.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

export function forbidden(): NextResponse {
  return NextResponse.json({ detail: "Cross-origin request refused" }, { status: 403 });
}

/** POST JSON to the backend, forwarding client context headers. */
export async function backendPost(
  req: NextRequest,
  path: string,
  body: unknown,
  bearer?: string,
): Promise<Response> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const ua = req.headers.get("user-agent");
  if (ua) headers["User-Agent"] = ua;
  const xff = req.headers.get("x-forwarded-for");
  if (xff) headers["X-Forwarded-For"] = xff;
  const cid = req.headers.get("x-correlation-id");
  if (cid) headers["X-Correlation-ID"] = cid;
  if (bearer) headers["Authorization"] = `Bearer ${bearer}`;
  return fetch(`${apiOrigin()}/api/v1${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body ?? {}),
    cache: "no-store",
  });
}

export async function readJson(res: Response): Promise<Record<string, unknown>> {
  try {
    return (await res.json()) as Record<string, unknown>;
  } catch {
    return { detail: res.statusText || "Upstream error" };
  }
}

/** Relay a backend error (status, detail, Retry-After) without cookies. */
export function relayError(res: Response, data: Record<string, unknown>): NextResponse {
  const out = NextResponse.json(
    { detail: data.detail ?? "Request failed" },
    { status: res.status },
  );
  const ra = res.headers.get("retry-after");
  if (ra) out.headers.set("Retry-After", ra);
  return out;
}

export function setSessionCookies(res: NextResponse, refreshToken: string): void {
  const base = {
    httpOnly: true,
    sameSite: "strict" as const,
    secure: cookieSecure(),
    maxAge: cookieMaxAge(),
  };
  res.cookies.set(REFRESH_COOKIE, refreshToken, { ...base, path: REFRESH_PATH });
  res.cookies.set(PRESENCE_COOKIE, "1", { ...base, path: "/" });
}

export function clearSessionCookies(res: NextResponse): void {
  const base = { httpOnly: true, sameSite: "strict" as const, secure: cookieSecure(), maxAge: 0 };
  res.cookies.set(REFRESH_COOKIE, "", { ...base, path: REFRESH_PATH });
  res.cookies.set(PRESENCE_COOKIE, "", { ...base, path: "/" });
}

type Tokens = { access_token: string; refresh_token: string; expires_in: number };

/**
 * Turn a backend AuthSessionOut into the browser payload + cookies. MFA
 * challenges (`mfa_required: true`) are passed through untouched.
 */
export function sessionResponse(data: Record<string, unknown>): NextResponse {
  if (data.mfa_required === true) {
    return NextResponse.json(data, { headers: { "Cache-Control": "no-store" } });
  }
  const tokens = data.tokens as Tokens | undefined;
  if (!tokens?.access_token || !tokens.refresh_token) {
    return NextResponse.json({ detail: "Malformed session response" }, { status: 502 });
  }
  const res = NextResponse.json(
    {
      access_token: tokens.access_token,
      expires_in: tokens.expires_in,
      user: data.user,
      organization: data.organization,
      role: data.role,
      permissions: data.permissions,
    },
    { headers: { "Cache-Control": "no-store" } },
  );
  setSessionCookies(res, tokens.refresh_token);
  return res;
}

/** Shared body for login / mfa-verify / accept-invite. */
export async function proxySessionCall(req: NextRequest, path: string): Promise<NextResponse> {
  if (!isSameOrigin(req)) return forbidden();
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 });
  }
  let upstream: Response;
  try {
    upstream = await backendPost(req, path, body);
  } catch {
    return NextResponse.json({ detail: "API unavailable" }, { status: 502 });
  }
  const data = await readJson(upstream);
  if (!upstream.ok) return relayError(upstream, data);
  return sessionResponse(data);
}
