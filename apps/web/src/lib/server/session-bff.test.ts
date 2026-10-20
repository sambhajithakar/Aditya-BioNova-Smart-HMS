// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST as loginPOST } from "@/app/api/session/login/route";
import { POST as refreshPOST } from "@/app/api/session/refresh/route";
import { POST as logoutPOST } from "@/app/api/session/logout/route";

const SESSION = {
  user: { id: "u" },
  organization: { id: "o" },
  role: "owner",
  permissions: ["member.read"],
  tokens: { access_token: "acc", refresh_token: "r".repeat(40), token_type: "bearer", expires_in: 1800 },
};

function req(path: string, init: { body?: unknown; headers?: Record<string, string> } = {}) {
  return new NextRequest(`http://web.test${path}`, {
    method: "POST",
    headers: { host: "web.test", "content-type": "application/json", ...(init.headers ?? {}) },
    body: JSON.stringify(init.body ?? {}),
  });
}

function upstream(status: number, body: unknown, headers: Record<string, string> = {}) {
  return vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } }));
}

afterEach(() => vi.unstubAllGlobals());

describe("/api/session/login", () => {
  it("keeps the refresh token in an httpOnly SameSite=Strict cookie, not the body", async () => {
    vi.stubGlobal("fetch", upstream(200, SESSION));
    const res = await loginPOST(req("/api/session/login", { body: { email: "a@b.in", password: "x" } }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.access_token).toBe("acc");
    expect(JSON.stringify(body)).not.toContain("r".repeat(40));
    const cookies = res.headers.getSetCookie().join("\n");
    expect(cookies).toMatch(/hms_rt=r{40}; Path=\/api\/session; .*HttpOnly/i);
    expect(cookies).toMatch(/hms_rt=[^\n]*SameSite=strict/i);
    expect(cookies).toMatch(/hms_session=1; Path=\//);
  });

  it("passes MFA challenges through without setting cookies", async () => {
    vi.stubGlobal("fetch", upstream(200, { mfa_required: true, mfa_token: "mt", methods: ["totp"], expires_in: 300 }));
    const res = await loginPOST(req("/api/session/login", { body: { email: "a@b.in", password: "x" } }));
    expect(await res.json()).toMatchObject({ mfa_required: true, mfa_token: "mt" });
    expect(res.headers.getSetCookie()).toHaveLength(0);
  });

  it("relays 429 with Retry-After", async () => {
    vi.stubGlobal("fetch", upstream(429, { detail: "Too many attempts. Try again later." }, { "Retry-After": "60" }));
    const res = await loginPOST(req("/api/session/login", { body: { email: "a@b.in", password: "x" } }));
    expect(res.status).toBe(429);
    expect(res.headers.get("Retry-After")).toBe("60");
  });

  it("refuses cross-origin calls", async () => {
    vi.stubGlobal("fetch", upstream(200, SESSION));
    const res = await loginPOST(
      req("/api/session/login", { body: {}, headers: { origin: "https://evil.example" } }),
    );
    expect(res.status).toBe(403);
  });
});

describe("/api/session/refresh", () => {
  it("rotates the cookie and returns only the access token", async () => {
    const f = upstream(200, { access_token: "acc2", refresh_token: "n".repeat(40), expires_in: 1800 });
    vi.stubGlobal("fetch", f);
    const res = await refreshPOST(req("/api/session/refresh", { headers: { cookie: `hms_rt=${"r".repeat(40)}` } }));
    expect(await res.json()).toEqual({ access_token: "acc2", expires_in: 1800 });
    expect(JSON.parse(String((f.mock.calls[0] as unknown as [string, RequestInit])[1].body))).toEqual({
      refresh_token: "r".repeat(40),
    });
    expect(res.headers.getSetCookie().join("\n")).toContain(`hms_rt=${"n".repeat(40)}`);
  });

  it("401 without a cookie, clearing the presence cookie", async () => {
    vi.stubGlobal("fetch", upstream(200, {}));
    const res = await refreshPOST(req("/api/session/refresh"));
    expect(res.status).toBe(401);
    expect(res.headers.getSetCookie().join("\n")).toMatch(/hms_session=; Path=\/; .*Max-Age=0/);
  });
});

describe("/api/session/logout", () => {
  it("calls backend logout with the bearer and clears both cookies", async () => {
    const f = upstream(200, { status: "logged_out" });
    vi.stubGlobal("fetch", f);
    const res = await logoutPOST(
      req("/api/session/logout", { headers: { authorization: "Bearer acc", cookie: "hms_rt=zzz" } }),
    );
    expect(res.status).toBe(200);
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/api\/v1\/auth\/logout$/);
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer acc");
    const set = res.headers.getSetCookie().join("\n");
    expect(set).toMatch(/hms_rt=; Path=\/api\/session; .*Max-Age=0/);
    expect(set).toMatch(/hms_session=; Path=\/; .*Max-Age=0/);
  });
});
