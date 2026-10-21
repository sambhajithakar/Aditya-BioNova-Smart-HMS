import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, login, verifyMfa } from "./api";
import { clearSession, getAccessToken, onAuthFailure, setSession } from "./session";

type Call = { url: string; init: RequestInit | undefined };

function json(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

function authHeader(c: Call): string | undefined {
  return (c.init?.headers as Record<string, string> | undefined)?.Authorization;
}

let calls: Call[];
let handler: (url: string, init?: RequestInit) => Response | Promise<Response>;

beforeEach(() => {
  clearSession();
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, init });
      return handler(url, init);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearSession();
});

describe("api client auth", () => {
  it("refreshes exactly once on 401 and retries with the new token", async () => {
    setSession({ access_token: "old", expires_in: 1800 });
    let apiHits = 0;
    handler = (url) => {
      if (url === "/api/session/refresh") return json(200, { access_token: "new", expires_in: 1800 });
      apiHits += 1;
      return apiHits === 1 ? json(401, { detail: "expired" }) : json(200, { ok: true });
    };
    await expect(api.get("/patients")).resolves.toEqual({ ok: true });
    const refreshes = calls.filter((c) => c.url === "/api/session/refresh");
    expect(refreshes).toHaveLength(1);
    const apiCalls = calls.filter((c) => c.url.startsWith("/api/v1"));
    expect(apiCalls.map(authHeader)).toEqual(["Bearer old", "Bearer new"]);
    expect(getAccessToken()).toBe("new");
  });

  it("does not loop: a second 401 after refresh ends the session", async () => {
    setSession({ access_token: "old", expires_in: 1800 });
    handler = (url) =>
      url === "/api/session/refresh"
        ? json(200, { access_token: "new", expires_in: 1800 })
        : json(401, { detail: "nope" });
    const failed = vi.fn();
    const off = onAuthFailure(failed);
    await expect(api.get("/auth/me")).rejects.toMatchObject({ status: 401 });
    off();
    expect(calls.filter((c) => c.url === "/api/session/refresh")).toHaveLength(1);
    expect(calls.filter((c) => c.url.startsWith("/api/v1"))).toHaveLength(2);
    expect(failed).toHaveBeenCalledTimes(1);
    expect(getAccessToken()).toBeNull();
  });

  it("concurrent 401s share a single refresh (single-flight)", async () => {
    setSession({ access_token: "old", expires_in: 1800 });
    handler = async (url, init) => {
      if (url === "/api/session/refresh") {
        await new Promise((r) => setTimeout(r, 5));
        return json(200, { access_token: "new", expires_in: 1800 });
      }
      const auth = (init?.headers as Record<string, string>).Authorization;
      return auth === "Bearer new" ? json(200, { url }) : json(401, {});
    };
    await Promise.all([api.get("/a"), api.get("/b"), api.get("/c")]);
    expect(calls.filter((c) => c.url === "/api/session/refresh")).toHaveLength(1);
  });

  it("mints an access token from the refresh cookie before the first call", async () => {
    handler = (url) =>
      url === "/api/session/refresh"
        ? json(200, { access_token: "fresh", expires_in: 900 })
        : json(200, { ok: 1 });
    await api.get("/auth/me");
    expect(calls[0].url).toBe("/api/session/refresh");
    expect(calls[0].init?.credentials).toBe("same-origin");
    expect(authHeader(calls[1])).toBe("Bearer fresh");
  });

  it("fails fast with 401 and notifies when there is no session at all", async () => {
    handler = () => json(401, { detail: "No session" });
    const failed = vi.fn();
    const off = onAuthFailure(failed);
    await expect(api.get("/auth/me")).rejects.toBeInstanceOf(ApiError);
    off();
    expect(calls.map((c) => c.url)).toEqual(["/api/session/refresh"]);
    expect(failed).toHaveBeenCalled();
  });

  it("passes Idempotency-Key through on POST", async () => {
    setSession({ access_token: "t", expires_in: 1800 });
    handler = () => json(201, { id: 1 });
    await api.post("/opd/queue", { a: 1 }, "key-123");
    expect((calls[0].init?.headers as Record<string, string>)["Idempotency-Key"]).toBe("key-123");
  });

  it("surfaces Retry-After on 429", async () => {
    setSession({ access_token: "t", expires_in: 1800 });
    handler = () => json(429, { detail: "Too many attempts. Try again later." }, { "Retry-After": "30" });
    await expect(api.get("/x")).rejects.toMatchObject({ status: 429, retryAfter: 30 });
  });

  it("publicPost sends no Authorization and never refreshes", async () => {
    handler = () => json(202, { status: "accepted" });
    await api.publicPost("/auth/password/forgot", { email: "a@b.c" });
    expect(calls).toHaveLength(1);
    expect(authHeader(calls[0])).toBeUndefined();
  });
});

describe("login flow", () => {
  it("never stores tokens in localStorage and keeps the access token in memory", async () => {
    handler = () =>
      json(200, {
        access_token: "acc",
        expires_in: 1800,
        user: { id: "u", email: "e", full_name: "n", status: "active" },
        organization: { id: "o", name: "Org", slug: "org", status: "active" },
        role: "owner",
        permissions: [],
      });
    const r = await login({ email: "e@x.in", password: "p" });
    expect(r.kind).toBe("session");
    expect(calls[0].url).toBe("/api/session/login");
    expect(getAccessToken()).toBe("acc");
    expect(JSON.stringify({ ...localStorage })).not.toContain("acc");
  });

  it("returns the MFA challenge and then verifies the code", async () => {
    handler = (url) =>
      url === "/api/session/login"
        ? json(200, { mfa_required: true, mfa_token: "mt", methods: ["totp"], expires_in: 300 })
        : json(200, {
            access_token: "after-mfa",
            expires_in: 1800,
            user: {},
            organization: {},
            role: "doctor",
            permissions: [],
          });
    const r = await login({ email: "e@x.in", password: "p" });
    expect(r.kind).toBe("mfa");
    expect(getAccessToken()).toBeNull();
    if (r.kind !== "mfa") throw new Error("expected mfa");
    await verifyMfa(r.challenge.mfa_token, "123456");
    expect(JSON.parse(String(calls[1].init?.body))).toEqual({ mfa_token: "mt", code: "123456" });
    expect(getAccessToken()).toBe("after-mfa");
  });
});
