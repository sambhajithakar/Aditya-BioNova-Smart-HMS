/**
 * Per-attempt idempotency keys (H13).
 *
 * The backend stores a key permanently once a request SUCCEEDS and replays
 * the stored response for any later request with the same key (409 if the
 * payload differs). Keys must therefore identify one user attempt, never
 * business data: a random UUID is minted lazily for a form submission, kept
 * across retries of that same attempt (network error, 5xx, double click),
 * and replaced only after success or an explicit reset (form cleared).
 */
import { useCallback, useRef, useState } from "react";

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Fallback for very old browsers: RFC 4122 v4 from getRandomValues.
  const b = new Uint8Array(16);
  crypto.getRandomValues(b);
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export class IdempotencyKeyHolder {
  private key: string | null = null;
  constructor(private readonly mint: () => string = newIdempotencyKey) {}

  /** The key for the current attempt (minted on first use). */
  current(): string {
    if (!this.key) this.key = this.mint();
    return this.key;
  }

  /** Forget the key: the next submission is a new attempt. */
  reset(): void {
    this.key = null;
  }

  /**
   * Run `fn` with the attempt's key; on success the key is retired so the
   * next submission gets a fresh one. On failure it is kept for a retry.
   */
  async run<T>(fn: (key: string) => Promise<T>): Promise<T> {
    const key = this.current();
    const out = await fn(key);
    if (this.key === key) this.key = null;
    return out;
  }
}

/** React hook: one holder per form for the component's lifetime. */
export function useIdempotencyKey(): IdempotencyKeyHolder {
  const ref = useRef<IdempotencyKeyHolder | null>(null);
  if (!ref.current) ref.current = new IdempotencyKeyHolder();
  return ref.current;
}

/**
 * Guard against double submission: `run(fn)` ignores calls while one is in
 * flight (synchronously, so a double click cannot slip through before React
 * re-renders) and exposes `busy` for disabling the submit button.
 */
export function useInFlight(): {
  busy: boolean;
  run: <T>(fn: () => Promise<T>) => Promise<T | undefined>;
} {
  const flight = useRef(false);
  const [busy, setBusy] = useState(false);
  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    if (flight.current) return undefined;
    flight.current = true;
    setBusy(true);
    try {
      return await fn();
    } finally {
      flight.current = false;
      setBusy(false);
    }
  }, []);
  return { busy, run };
}
