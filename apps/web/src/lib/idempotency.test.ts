import { describe, expect, it } from "vitest";
import { IdempotencyKeyHolder, newIdempotencyKey } from "./idempotency";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("idempotency keys", () => {
  it("mints random v4 UUIDs, not business-data strings", () => {
    const a = newIdempotencyKey();
    const b = newIdempotencyKey();
    expect(a).toMatch(UUID_RE);
    expect(a).not.toBe(b);
  });

  it("keeps the same key for retries of one attempt", async () => {
    const h = new IdempotencyKeyHolder();
    const seen: string[] = [];
    const failing = async (k: string) => {
      seen.push(k);
      throw new Error("network");
    };
    await expect(h.run(failing)).rejects.toThrow();
    await expect(h.run(failing)).rejects.toThrow();
    expect(seen[0]).toBe(seen[1]);
  });

  it("retires the key after success so the next submission is new", async () => {
    const h = new IdempotencyKeyHolder();
    const seen: string[] = [];
    await h.run(async (k) => seen.push(k));
    await h.run(async (k) => seen.push(k));
    expect(seen[0]).not.toBe(seen[1]);
  });

  it("explicit reset starts a new attempt", () => {
    let n = 0;
    const h = new IdempotencyKeyHolder(() => `k${++n}`);
    expect(h.current()).toBe("k1");
    expect(h.current()).toBe("k1");
    h.reset();
    expect(h.current()).toBe("k2");
  });

  it("identical payloads in two separate attempts get different keys", async () => {
    // e.g. the same patient re-queued later the same day, or two equal expenses
    const h = new IdempotencyKeyHolder();
    const keys: string[] = [];
    const submit = () => h.run(async (k) => keys.push(k));
    await submit();
    await submit();
    expect(new Set(keys).size).toBe(2);
  });
});
