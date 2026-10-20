import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { encodeQr, isAlphanumeric, qrSvgPath } from "./qr";

type Case = { data: string; mode: string; version: number; error: string; mask: number; rows: string[] };

// Reference matrices produced by the independent `segno` encoder (see the
// fixture's generator field). Not a runtime dependency — fixture data only.
const ref = JSON.parse(
  readFileSync(join(__dirname, "__fixtures__", "qr-segno.json"), "utf8"),
) as { cases: Case[] };

const rows = (m: boolean[][]) => m.map((r) => r.map((c) => (c ? "1" : "0")).join(""));

describe("QR encoder", () => {
  it.each(ref.cases.map((c) => [c.data.slice(0, 24), c] as const))(
    "matches segno module-for-module: %s",
    (_label, c) => {
      const qr = encodeQr(c.data, { ecl: c.error as "L" | "M" | "Q" | "H", mask: c.mask });
      expect(qr.version).toBe(c.version);
      expect(rows(qr.modules)).toEqual(c.rows);
    },
  );

  it("picks a mask automatically and stays deterministic", () => {
    const a = encodeQr("K7Q2MZJX4WNB5TRC3HPLYD6VAE");
    const b = encodeQr("K7Q2MZJX4WNB5TRC3HPLYD6VAE");
    expect(a.version).toBe(2);
    expect(a.mask).toBeGreaterThanOrEqual(0);
    expect(a.mask).toBeLessThan(8);
    expect(rows(a.modules)).toEqual(rows(b.modules));
  });

  it("uses alphanumeric mode for base32 check-in tokens", () => {
    expect(isAlphanumeric("K7Q2MZJX4WNB5TRC3HPLYD6VAE")).toBe(true);
    expect(isAlphanumeric("hello")).toBe(false);
  });

  it("renders an SVG path with a quiet zone and rejects bad input", () => {
    const qr = encodeQr("ABC");
    const svg = qrSvgPath(qr, 4);
    expect(svg.viewBox).toBe(`0 0 ${qr.size + 8} ${qr.size + 8}`);
    expect(svg.path.startsWith("M4,4h1v1h-1z")).toBe(true); // finder corner
    expect(() => encodeQr("x".repeat(4000))).toThrow();
    expect(() => encodeQr("A", { mask: 9 })).toThrow();
  });
});
