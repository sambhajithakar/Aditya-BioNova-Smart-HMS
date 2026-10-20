import { NextRequest } from "next/server";
import { proxySessionCall } from "@/lib/server/session-bff";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  return proxySessionCall(req, "/auth/mfa/verify");
}
