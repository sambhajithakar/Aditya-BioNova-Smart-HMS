import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { FORBIDDEN, WEB_COMPONENTS } from "./licenses";

const lock = JSON.parse(readFileSync(join(__dirname, "../../package-lock.json"), "utf8")) as {
  packages: Record<string, { version: string; license?: string; dev?: boolean }>;
};
const pkg = (name: string) => lock.packages[`node_modules/${name}`];

describe("web licence notices (M8.1 L2)", () => {
  it("match the versions and licences in package-lock.json", () => {
    for (const c of WEB_COMPONENTS) {
      const first = c.name.split(" ")[0];
      if (first.startsWith("@next/swc")) continue; // platform-specific binary
      const entry = pkg(first);
      expect(entry, c.name).toBeDefined();
      expect(entry.version, c.name).toBe(c.version);
      expect(entry.license, c.name).toBe(c.licence);
    }
  });

  it("list every runtime package and no strong-copyleft licence", () => {
    const listed = new Set(WEB_COMPONENTS.map((c) => c.name.split(" ")[0]));
    listed.add("react-dom"); // listed as "react / react-dom"
    const shipped = Object.entries(lock.packages)
      .filter(([k, v]) => k && !v.dev && !(v as { optional?: boolean }).optional
        && !(v as { devOptional?: boolean }).devOptional)
      .map(([k]) => k.replace(/.*node_modules\//, ""));
    for (const name of shipped) expect(listed.has(name), name).toBe(true);
    for (const v of Object.values(lock.packages)) {
      if (v.license) expect(v.license).not.toMatch(FORBIDDEN);
    }
  });
});
