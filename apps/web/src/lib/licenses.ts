/**
 * Third-party components shipped to the browser or run by the web server
 * (M8.1 L2). Mirrors the "Node — web runtime" table of LICENSES.md; the
 * unit test keeps the two in step. Development-only tools are not listed.
 */
export type Component = { name: string; version: string; licence: string; note?: string };

export const WEB_COMPONENTS: Component[] = [
  { name: "next", version: "15.5.27", licence: "MIT" },
  { name: "react / react-dom", version: "19.3.0", licence: "MIT" },
  { name: "scheduler", version: "0.28.0", licence: "MIT" },
  { name: "@next/env", version: "15.5.27", licence: "MIT" },
  { name: "styled-jsx", version: "5.1.6", licence: "MIT" },
  { name: "client-only", version: "0.0.1", licence: "MIT" },
  { name: "nanoid", version: "3.3.19", licence: "MIT" },
  { name: "@next/swc (prebuilt compiler binary)", version: "15.5.27", licence: "MIT" },
  { name: "@swc/helpers", version: "0.5.15", licence: "Apache-2.0" },
  { name: "detect-libc", version: "2.1.2", licence: "Apache-2.0" },
  { name: "postcss", version: "8.5.28", licence: "MIT" },
  { name: "source-map-js", version: "1.2.2", licence: "BSD-3-Clause" },
  { name: "picocolors", version: "1.1.1", licence: "ISC" },
  { name: "semver", version: "7.8.5", licence: "ISC" },
  { name: "tslib", version: "2.8.1", licence: "0BSD" },
  {
    name: "caniuse-lite",
    version: "1.0.30001814",
    licence: "CC-BY-4.0",
    note: "Browser support data © the caniuse.com contributors (Alexis Deveria).",
  },
];

/** Licence identifiers this product must never ship (strong copyleft). */
export const FORBIDDEN = /\b(A?GPL|SSPL)\b/;
