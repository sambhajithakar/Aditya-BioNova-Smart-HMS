import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { dictionaries } from "./i18n";
import { ROUTES } from "./rx";
import { ROLE_KEYS } from "./api";

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) return sourceFiles(p);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [p] : [];
  });
}

describe("i18n dictionaries", () => {
  const en = Object.keys(dictionaries.en).sort();

  it("EN, मराठी and हिंदी have identical key sets", () => {
    expect(Object.keys(dictionaries.mr).sort()).toEqual(en);
    expect(Object.keys(dictionaries.hi).sort()).toEqual(en);
  });

  it("no translation is empty", () => {
    for (const lang of ["en", "mr", "hi"] as const) {
      for (const [k, v] of Object.entries(dictionaries[lang])) {
        expect(v.trim(), `${lang}.${k}`).not.toBe("");
      }
    }
  });

  it("every literal t(\"key\") used in the app exists", () => {
    const src = join(__dirname, "..");
    const used = new Set<string>();
    for (const f of sourceFiles(src)) {
      const text = readFileSync(f, "utf8");
      for (const m of text.matchAll(/\bt\(\s*"(\w+)"/g)) used.add(m[1]);
      for (const m of text.matchAll(/"(rxErr\w+)"/g)) used.add(m[1]);
    }
    const missing = [...used].filter((k) => !(k in dictionaries.en));
    expect(missing).toEqual([]);
  });

  it("dynamic key families are complete", () => {
    for (const r of ROUTES) expect(dictionaries.en).toHaveProperty(`route_${r}`);
    for (const r of [...ROLE_KEYS, "owner"]) expect(dictionaries.en).toHaveProperty(`role_${r}`);
  });
});
