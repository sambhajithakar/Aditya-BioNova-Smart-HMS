/**
 * Edge middleware:
 * 1. Per-request CSP with a script nonce (Next applies the nonce to its own
 *    framework/inline scripts when it finds it in the request's CSP header).
 * 2. Route protection: page requests without the session-presence cookie are
 *    redirected to /login?next=… before any page code runs.
 * 3. The token-issuing backend endpoints are not reachable through the web
 *    origin's /api/v1 proxy — browsers must use /api/session/* so refresh
 *    tokens only ever live in the httpOnly cookie.
 */
import { NextRequest, NextResponse } from "next/server";
import { buildCsp } from "./lib/csp";

const PRESENCE_COOKIE = "hms_session";
const PUBLIC_PAGES = ["/login", "/forgot-password", "/reset-password", "/accept-invite", "/licenses"];
const BLOCKED_PROXY = [
  "/api/v1/auth/login",
  "/api/v1/auth/refresh",
  "/api/v1/auth/mfa/verify",
  "/api/v1/auth/invitations/accept",
];

/**
 * The path the API will route: percent-decoded, duplicate and trailing
 * slashes removed. Without this, `/api/v1/auth/%6Cogin` or
 * `/api/v1//auth/login/` slipped past the block list while the backend still
 * resolved them to the login endpoint (M8.1). Undecodable input → null.
 */
export function apiRoutePath(pathname: string): string | null {
  let p: string;
  try {
    p = decodeURIComponent(pathname);
  } catch {
    return null;
  }
  return p.replace(/\/{2,}/g, "/").replace(/(.)\/+$/, "$1");
}

export function isBlockedProxyPath(pathname: string): boolean {
  if (!pathname.startsWith("/api/")) return false;
  const p = apiRoutePath(pathname);
  return p === null || BLOCKED_PROXY.includes(p);
}

function isPublicPage(pathname: string): boolean {
  return PUBLIC_PAGES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl;

  if (isBlockedProxyPath(pathname)) {
    return NextResponse.json({ detail: "Use /api/session/*" }, { status: 404 });
  }
  if (pathname.startsWith("/api/")) return NextResponse.next();

  if (!isPublicPage(pathname) && !req.cookies.get(PRESENCE_COOKIE)?.value) {
    // Build the target from the Host the browser actually used: when bound to
    // an IP, req.nextUrl may say "localhost", and a host switch would drop
    // the host-only session cookies.
    const host = req.headers.get("host") || req.nextUrl.host;
    const proto = req.headers.get("x-forwarded-proto") || req.nextUrl.protocol.replace(":", "");
    const target = new URL(`${proto}://${host}/login`);
    target.searchParams.set("next", pathname + search);
    return NextResponse.redirect(target, 307);
  }

  const nonce = btoa(crypto.randomUUID());
  const csp = buildCsp(
    nonce,
    process.env.NODE_ENV !== "production",
    process.env.RAZORPAY_CHECKOUT === "1",
  );
  const requestHeaders = new Headers(req.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);
  const res = NextResponse.next({ request: { headers: requestHeaders } });
  res.headers.set("Content-Security-Policy", csp);
  return res;
}

export const config = {
  matcher: [
    {
      // PWA files (worker, manifest, icons, static offline page) are public,
      // hold no user data and must not redirect to /login; their headers
      // (incl. a script-free CSP for /offline.html) come from next.config.mjs.
      source:
        "/((?!_next/static|_next/image|favicon.ico|robots.txt|sw\\.js|manifest\\.webmanifest|offline\\.html|icons/).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
