import { readFileSync } from "node:fs";
import { join } from "node:path";
import { runInNewContext } from "node:vm";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  CHORD_TIMEOUT_MS,
  GOTO,
  initialChord,
  isEditableTarget,
  newTargetSelectors,
  resolveShortcut,
  type KeyLike,
} from "./shortcuts";
import {
  OFFLINE_AFTER_FAILURES,
  PROBE_INTERVAL_ONLINE_MS,
  PROBE_INTERVAL_TROUBLE_MS,
  __resetConnForTests,
  dispatchConn,
  getConn,
  initialConn,
  nextConn,
  probeHealth,
  probeInterval,
  reportNetworkFailure,
  reportNetworkOk,
  subscribeConn,
} from "./connectivity";
import { BOTTOM_SLOTS, pickBottomNav } from "./device-nav";
import { NAV } from "./nav";
import { consumePatientSearch, debounce, onPatientSearch, requestPatientSearch } from "./quick-search";
import { pageCss, papersFor, parsePaper } from "./print-paper";
import { cachesToClear, swUrl } from "./pwa";
import { dictionaries } from "./i18n";
import { deviceDictionaries } from "./i18n-device";
import { baseDictionaries } from "./i18n";
import { saasDictionaries } from "./i18n-saas";
import { aiDictionaries } from "./i18n-ai";

// ---------------------------------------------------------------- shortcuts
describe("keyboard shortcut parser", () => {
  const k = (key: string, extra: Partial<KeyLike> = {}): KeyLike => ({ key, ...extra });

  it("/ and Ctrl/⌘+K focus the patient search", () => {
    expect(resolveShortcut(k("/"), initialChord, 0).action).toEqual({ type: "focusSearch" });
    expect(resolveShortcut(k("k", { ctrlKey: true }), initialChord, 0).action).toEqual({ type: "focusSearch" });
    expect(resolveShortcut(k("K", { metaKey: true }), initialChord, 0).action).toEqual({ type: "focusSearch" });
  });

  it("Ctrl+K works inside a field, single keys do not", () => {
    expect(resolveShortcut(k("k", { ctrlKey: true, editable: true }), initialChord, 0).action).toEqual({
      type: "focusSearch",
    });
    for (const key of ["/", "?", "n", "g"]) {
      const r = resolveShortcut(k(key, { editable: true }), initialChord, 0);
      expect(r.action, key).toBeNull();
      expect(r.state.pendingG, key).toBeNull();
    }
  });

  it("g then a key navigates; the chord expires", () => {
    const g = resolveShortcut(k("g"), initialChord, 1000);
    expect(g.action).toBeNull();
    expect(g.state.pendingG).toBe(1000);
    expect(resolveShortcut(k("p"), g.state, 1500).action).toEqual({ type: "goto", nav: "patients" });
    expect(resolveShortcut(k("q"), g.state, 1500).action).toEqual({ type: "goto", nav: "queue" });
    expect(resolveShortcut(k("b"), g.state, 1500).action).toEqual({ type: "goto", nav: "billing" });
    // too late: "p" is just a key again (no action), chord cleared
    const late = resolveShortcut(k("p"), g.state, 1000 + CHORD_TIMEOUT_MS + 1);
    expect(late.action).toBeNull();
    expect(late.state.pendingG).toBeNull();
    // unknown second key cancels the chord
    const bad = resolveShortcut(k("z"), g.state, 1100);
    expect(bad.action).toBeNull();
    expect(bad.state).toEqual(initialChord);
  });

  it("typing g then p in a field never navigates", () => {
    const g = resolveShortcut(k("g", { editable: true }), initialChord, 0);
    expect(resolveShortcut(k("p", { editable: true }), g.state, 10).action).toBeNull();
  });

  it("? opens help, n is the page's new action", () => {
    expect(resolveShortcut(k("?", { shiftKey: true }), initialChord, 0).action).toEqual({ type: "help" });
    expect(resolveShortcut(k("n"), initialChord, 0).action).toEqual({ type: "new" });
  });

  it("modifier combos, IME composition and auto-repeat are ignored", () => {
    expect(resolveShortcut(k("n", { ctrlKey: true }), initialChord, 0).action).toBeNull(); // browser new window
    expect(resolveShortcut(k("p", { altKey: true }), initialChord, 0).action).toBeNull();
    expect(resolveShortcut(k("/", { isComposing: true }), initialChord, 0).action).toBeNull();
    expect(resolveShortcut(k("n", { repeat: true }), initialChord, 0).action).toBeNull();
  });

  it("every g-target is a real nav item", () => {
    for (const nav of Object.values(GOTO)) expect(NAV.some((n) => n.key === nav), nav).toBe(true);
  });

  it("detects editable targets", () => {
    const input = document.createElement("input");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    const div = document.createElement("div");
    const ce = document.createElement("div");
    ce.setAttribute("contenteditable", "true");
    expect(isEditableTarget(input)).toBe(true);
    expect(isEditableTarget(document.createElement("textarea"))).toBe(true);
    expect(isEditableTarget(document.createElement("select"))).toBe(true);
    expect(isEditableTarget(ce)).toBe(true);
    expect(isEditableTarget(checkbox)).toBe(false);
    expect(isEditableTarget(div)).toBe(false);
    expect(isEditableTarget(null)).toBe(false);
  });

  it("new-record targets prefer data-shortcut, then the page map", () => {
    expect(newTargetSelectors("/patients")).toEqual(['[data-shortcut="new"]', "#full_name"]);
    expect(newTargetSelectors("/reports")).toEqual(['[data-shortcut="new"]']);
  });
});

// ------------------------------------------------------------- connectivity
describe("connectivity state machine", () => {
  afterEach(() => __resetConnForTests());

  it("failures go reconnecting → offline; any success is online", () => {
    let s = initialConn;
    s = nextConn(s, "fetchFailed");
    expect(s.status).toBe("reconnecting");
    for (let i = 1; i < OFFLINE_AFTER_FAILURES; i++) s = nextConn(s, "probeFailed");
    expect(s.status).toBe("offline");
    expect(nextConn(s, "probeOk")).toEqual(initialConn);
    expect(nextConn(s, "fetchOk")).toEqual(initialConn);
  });

  it("browser offline is immediate; browser online waits for a probe", () => {
    const off = nextConn(initialConn, "browserOffline");
    expect(off.status).toBe("offline");
    const back = nextConn(off, "browserOnline");
    expect(back.status).toBe("reconnecting");
    expect(nextConn(back, "probeOk").status).toBe("online");
  });

  it("probes fast while in trouble, slowly when healthy", () => {
    expect(probeInterval(initialConn)).toBe(PROBE_INTERVAL_ONLINE_MS);
    expect(probeInterval({ status: "offline", failures: 3 })).toBe(PROBE_INTERVAL_TROUBLE_MS);
    expect(PROBE_INTERVAL_TROUBLE_MS).toBeLessThan(PROBE_INTERVAL_ONLINE_MS);
  });

  it("store notifies on change only", () => {
    const seen: string[] = [];
    const off = subscribeConn((s) => seen.push(s.status));
    reportNetworkOk(); // already online: no event
    reportNetworkFailure();
    reportNetworkFailure();
    reportNetworkFailure();
    reportNetworkOk();
    off();
    expect(seen).toEqual(["reconnecting", "reconnecting", "offline", "online"]);
  });

  it("health probe hits /api/v1/health without credentials and maps the result", async () => {
    const calls: [string, RequestInit | undefined][] = [];
    const ok = vi.fn(async (u: RequestInfo | URL, i?: RequestInit) => {
      calls.push([String(u), i]);
      return new Response("{}", { status: 200 });
    });
    dispatchConn("fetchFailed");
    expect(await probeHealth(ok as unknown as typeof fetch)).toBe(true);
    expect(getConn().status).toBe("online");
    expect(calls[0][0]).toBe("/api/v1/health");
    expect(calls[0][1]?.credentials).toBe("omit");
    expect(calls[0][1]?.cache).toBe("no-store");
    const down = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    expect(await probeHealth(down as unknown as typeof fetch)).toBe(false);
    expect(getConn().status).toBe("reconnecting");
    const bad = vi.fn(async () => new Response("", { status: 502 }));
    await probeHealth(bad as unknown as typeof fetch);
    await probeHealth(bad as unknown as typeof fetch);
    expect(getConn().status).toBe("offline");
  });
});

// --------------------------------------------------------------- bottom nav
describe("phone bottom navigation", () => {
  const all = NAV;
  it("picks the role's most-used modules, never dashboard", () => {
    expect(pickBottomNav(all, "doctor").primary.map((i) => i.key)).toEqual(["queue", "consultation", "patients"]);
    expect(pickBottomNav(all, "receptionist").primary.map((i) => i.key)).toEqual([
      "patients",
      "appointments",
      "queue",
    ]);
    expect(pickBottomNav(all, "pharmacist").primary.map((i) => i.key)).toEqual(["pharmacy", "inventory", "patients"]);
    for (const role of ["owner", "nurse", "billing", "lab_technician", "unknown", undefined]) {
      const { primary } = pickBottomNav(all, role);
      expect(primary.length).toBeLessThanOrEqual(BOTTOM_SLOTS);
      expect(primary.some((i) => i.key === "dashboard")).toBe(false);
    }
  });

  it("only uses the gated list it is given (permissions + edition)", () => {
    const gated = all.filter((i) => ["dashboard", "patients", "security"].includes(i.key));
    const { primary, rest } = pickBottomNav(gated, "doctor");
    expect(primary.map((i) => i.key)).toEqual(["patients"]);
    expect(rest.map((i) => i.key)).toEqual(["security"]);
  });

  it("everything not in the bar is in the More sheet exactly once", () => {
    const { primary, rest } = pickBottomNav(all, "owner");
    const keys = [...primary, ...rest].map((i) => i.key).sort();
    expect(keys).toEqual(all.filter((i) => i.key !== "dashboard").map((i) => i.key).sort());
  });
});

// ------------------------------------------------------------- quick search
describe("quick patient search hand-off", () => {
  it("queues in memory until the page mounts, then delivers live", () => {
    requestPatientSearch("  Asha  ");
    expect(consumePatientSearch()).toEqual({ q: "Asha" });
    expect(consumePatientSearch()).toBeNull();
    const got: string[] = [];
    const off = onPatientSearch((r) => got.push(r.q));
    requestPatientSearch("9876");
    off();
    expect(got).toEqual(["9876"]);
    expect(consumePatientSearch()).toBeNull();
  });

  it("never touches Web Storage", () => {
    localStorage.clear();
    sessionStorage.clear();
    requestPatientSearch("Secret Name");
    consumePatientSearch();
    expect(localStorage.length + sessionStorage.length).toBe(0);
  });

  it("debounce fires once with the last value", () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const d = debounce(fn, 250);
    d("a");
    d("as");
    d("ash");
    vi.advanceTimersByTime(249);
    expect(fn).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("ash");
    d("x");
    d.cancel();
    vi.advanceTimersByTime(500);
    expect(fn).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});

// -------------------------------------------------------------------- print
describe("print paper sizes", () => {
  it("80 mm roll is for receipts only", () => {
    expect(parsePaper("80mm", true)).toBe("80mm");
    expect(parsePaper("80mm", false)).toBe("a4");
    expect(parsePaper("a5", false)).toBe("a5");
    expect(parsePaper(null, true)).toBe("a4");
    expect(parsePaper("letter", true)).toBe("a4");
    expect(papersFor(false)).toEqual(["a4", "a5"]);
    expect(papersFor(true)).toEqual(["a4", "a5", "80mm"]);
  });
  it("emits the matching @page size", () => {
    expect(pageCss("a4")).toMatch(/@page \{ size: A4;/);
    expect(pageCss("a5")).toMatch(/@page \{ size: A5;/);
    expect(pageCss("80mm")).toMatch(/@page \{ size: 80mm auto;/);
  });
});

// ---------------------------------------------------------- service worker
type Listener = (e: unknown) => void;
function loadSw(version = "test1") {
  const listeners: Record<string, Listener[]> = {};
  const self: Record<string, unknown> = {
    location: { href: `https://clinic.example/sw.js?v=${version}`, origin: "https://clinic.example" },
    addEventListener: (t: string, l: Listener) => (listeners[t] ||= []).push(l),
    clients: { claim: vi.fn(async () => undefined) },
    skipWaiting: vi.fn(),
  };
  const src = readFileSync(join(__dirname, "..", "..", "public", "sw.js"), "utf8");
  runInNewContext(src, { self, URL, Request, Response, Promise, caches: undefined, fetch: undefined });
  return {
    self,
    listeners,
    route: self.__hmsRoute as (m: string, u: string, mode: string, o: string) => string,
    names: self.__hmsCaches as { SHELL_CACHE: string; STATIC_CACHE: string; PREFIX: string },
  };
}

describe("service worker (public/sw.js)", () => {
  const O = "https://clinic.example";
  it("never intercepts /api/** (network-only, never cached)", () => {
    const { route } = loadSw();
    for (const u of ["/api/v1/patients?q=asha", "/api/v1/health", "/api/session/refresh", "/api"]) {
      expect(route("GET", O + u, "cors", O), u).toBe("network");
    }
    expect(route("POST", `${O}/api/v1/billing/invoices/1/payments`, "cors", O)).toBe("network");
  });

  it("caches only hashed static assets and the shell; HTML is network-first with offline fallback", () => {
    const { route } = loadSw();
    expect(route("GET", `${O}/_next/static/chunks/main-abc.js`, "no-cors", O)).toBe("static");
    expect(route("GET", `${O}/offline.html`, "navigate", O)).toBe("shell");
    expect(route("GET", `${O}/manifest.webmanifest`, "cors", O)).toBe("shell");
    expect(route("GET", `${O}/icons/icon-192.png`, "no-cors", O)).toBe("shell");
    expect(route("GET", `${O}/patients`, "navigate", O)).toBe("navigate");
    expect(route("GET", `${O}/dashboard?_rsc=1`, "cors", O)).toBe("network"); // RSC payloads
    expect(route("GET", "https://cdn.example/x.js", "no-cors", O)).toBe("network");
    expect(route("POST", `${O}/_next/static/x.js`, "cors", O)).toBe("network");
  });

  it("cache names are versioned by the registration URL", () => {
    expect(loadSw("abc").names.STATIC_CACHE).toBe("hms-static-abc");
    expect(loadSw("abc").names.SHELL_CACHE).toBe("hms-shell-abc");
  });

  it("does not skipWaiting on install; does on the user's Reload", () => {
    const { self, listeners } = loadSw();
    expect(self.skipWaiting).not.toHaveBeenCalled();
    listeners.message[0]({ data: { type: "SKIP_WAITING" } });
    expect(self.skipWaiting).toHaveBeenCalledTimes(1);
  });

  it("client helpers: versioned URL and logout cache clearing", () => {
    expect(swUrl("b1")).toBe("/sw.js?v=b1");
    expect(cachesToClear(["hms-static-b1", "hms-shell-b1", "hms-static-b0", "other"], "b1")).toEqual([
      "hms-static-b0",
      "other",
    ]);
  });
});

// ------------------------------------------------------------ i18n + a11y
describe("device strings and colour contrast", () => {
  it("device strings exist in all three languages and never override older keys", () => {
    const en = Object.keys(deviceDictionaries.en).sort();
    expect(Object.keys(deviceDictionaries.mr).sort()).toEqual(en);
    expect(Object.keys(deviceDictionaries.hi).sort()).toEqual(en);
    const older = { ...baseDictionaries.en, ...saasDictionaries.en, ...aiDictionaries.en };
    expect(en.filter((key) => key in older)).toEqual([]);
    for (const key of en) expect(dictionaries.hi[key]).toBe(deviceDictionaries.hi[key]);
  });

  // WCAG 2.x relative luminance contrast for the design tokens in globals.css.
  const lum = (hex: string) => {
    const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
    const l = c.map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2];
  };
  const ratio = (a: string, b: string) => {
    const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
    return (x + 0.05) / (y + 0.05);
  };
  const css = readFileSync(join(__dirname, "..", "app", "globals.css"), "utf8");
  const token = (name: string) => {
    const m = css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`));
    if (!m) throw new Error(name);
    return m[1];
  };

  it.each([
    ["text", "surface"],
    ["text", "white"],
    ["text-muted", "white"],
    ["text-muted", "surface"],
    ["white", "teal-600"], // primary button
    ["white", "navy-800"], // header
    ["navy-800", "teal-100"], // active nav / notice
    ["danger", "white"],
    ["teal-600", "white"], // active bottom-nav item
    ["warn-text", "warn-bg"],
  ])("%s on %s meets WCAG AA (4.5:1)", (fg, bg) => {
    expect(ratio(token(fg), token(bg))).toBeGreaterThanOrEqual(4.5);
  });
});
