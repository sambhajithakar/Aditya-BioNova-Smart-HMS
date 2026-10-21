import { NextRequest, NextResponse } from "next/server";
import {
  REFRESH_COOKIE,
  backendPost,
  clearSessionCookies,
  forbidden,
  isSameOrigin,
  readJson,
  relayError,
  setSessionCookies,
} from "@/lib/server/session-bff";

export const dynamic = "force-dynamic";

/** Rotate the refresh cookie and hand the browser a fresh access token. */
export async function POST(req: NextRequest) {
  if (!isSameOrigin(req)) return forbidden();
  const rt = req.cookies.get(REFRESH_COOKIE)?.value;
  if (!rt) {
    const res = NextResponse.json({ detail: "No session" }, { status: 401 });
    clearSessionCookies(res);
    return res;
  }
  let upstream: Response;
  try {
    upstream = await backendPost(req, "/auth/refresh", { refresh_token: rt });
  } catch {
    return NextResponse.json({ detail: "API unavailable" }, { status: 502 });
  }
  const data = await readJson(upstream);
  if (!upstream.ok) {
    const res = relayError(upstream, data);
    // 401/403: the refresh token is dead (expired, revoked, reused) — drop it.
    // 429/5xx: keep the cookie so a later retry can still succeed.
    if (upstream.status === 401 || upstream.status === 403) clearSessionCookies(res);
    return res;
  }
  const res = NextResponse.json(
    { access_token: data.access_token, expires_in: data.expires_in },
    { headers: { "Cache-Control": "no-store" } },
  );
  setSessionCookies(res, String(data.refresh_token));
  return res;
}
