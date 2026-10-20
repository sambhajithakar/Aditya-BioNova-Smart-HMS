import { NextRequest, NextResponse } from "next/server";
import {
  REFRESH_COOKIE,
  backendPost,
  clearSessionCookies,
  forbidden,
  isSameOrigin,
  readJson,
} from "@/lib/server/session-bff";

export const dynamic = "force-dynamic";

/**
 * Revoke the backend session and clear both cookies. The backend's logout
 * needs a Bearer access token (it revokes the session the token belongs
 * to); if the browser has none in memory, mint one from the refresh cookie
 * first so the server-side session is really revoked, not just forgotten.
 */
export async function POST(req: NextRequest) {
  if (!isSameOrigin(req)) return forbidden();
  let bearer = req.headers.get("authorization")?.replace(/^Bearer\s+/i, "") || "";
  const rt = req.cookies.get(REFRESH_COOKIE)?.value;
  try {
    if (!bearer && rt) {
      const r = await backendPost(req, "/auth/refresh", { refresh_token: rt });
      if (r.ok) bearer = String((await readJson(r)).access_token || "");
    }
    if (bearer) await backendPost(req, "/auth/logout", {}, bearer);
  } catch {
    /* backend unreachable: still clear the cookies locally */
  }
  const res = NextResponse.json({ status: "logged_out" }, { headers: { "Cache-Control": "no-store" } });
  clearSessionCookies(res);
  return res;
}
