import { describe, expect, it } from "vitest";
import { apiRoutePath, isBlockedProxyPath } from "../middleware";

describe("token endpoints cannot be reached through the /api/v1 proxy (M8.1)", () => {
  it("blocks the plain paths", () => {
    expect(isBlockedProxyPath("/api/v1/auth/login")).toBe(true);
    expect(isBlockedProxyPath("/api/v1/auth/refresh")).toBe(true);
  });

  it("blocks encoded, doubled-slash and trailing-slash variants", () => {
    for (const p of [
      "/api/v1/auth/%6Cogin",
      "/api/v1/auth/%6c%6f%67%69%6e",
      "/api/v1//auth/login",
      "/api/v1/auth/login/",
      "/api/v1/auth%2Frefresh",
      "/api/v1/auth/mfa%2Fverify",
      "/api/v1/auth/invitations/accept//",
    ]) {
      expect(isBlockedProxyPath(p), p).toBe(true);
    }
  });

  it("refuses undecodable paths and leaves other endpoints alone", () => {
    expect(apiRoutePath("/api/v1/auth/%E0%A4")).toBeNull();
    expect(isBlockedProxyPath("/api/v1/auth/%E0%A4")).toBe(true);
    expect(isBlockedProxyPath("/api/v1/auth/me")).toBe(false);
    expect(isBlockedProxyPath("/api/v1/patients/123")).toBe(false);
    expect(isBlockedProxyPath("/api/session/login")).toBe(false);
    expect(isBlockedProxyPath("/login")).toBe(false);
  });
});
