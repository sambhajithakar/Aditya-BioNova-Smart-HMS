/**
 * Service-worker registration + update flow (see public/sw.js for what is
 * and is not cached — never /api/**, never HTML pages).
 *
 * - Registered only in production builds and only on secure contexts
 *   (https, or http://localhost for development/E2E).
 * - The script URL carries the build id (/sw.js?v=…), so each deploy installs
 *   a new worker, which then WAITS; the shell shows "New version available —
 *   Reload" and only on click is the waiting worker told to take over.
 * - Logout calls clearAppCaches(): defence in depth — no cache should ever
 *   hold user data, but any cache other than the current build's static ones
 *   is deleted anyway.
 */

export const SW_PATH = "/sw.js";
export const CACHE_PREFIX = "hms-";

export function buildId(): string {
  return process.env.NEXT_PUBLIC_BUILD_ID || "dev";
}

export function swUrl(id = buildId()): string {
  return `${SW_PATH}?v=${encodeURIComponent(id)}`;
}

/** Caches a logout must delete: anything ours that is not a current static/shell cache. */
export function cachesToClear(keys: string[], id = buildId()): string[] {
  const keep = new Set([`${CACHE_PREFIX}shell-${id}`, `${CACHE_PREFIX}static-${id}`]);
  return keys.filter((k) => !keep.has(k));
}

export function swSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    window.isSecureContext &&
    process.env.NODE_ENV === "production"
  );
}

/**
 * Register the worker. `onUpdate` fires when a new version is installed and
 * waiting (not on the very first install).
 */
export async function registerServiceWorker(
  onUpdate: (reg: ServiceWorkerRegistration) => void,
): Promise<ServiceWorkerRegistration | null> {
  if (!swSupported()) return null;
  try {
    const reg = await navigator.serviceWorker.register(swUrl(), { scope: "/" });
    const notifyIfWaiting = () => {
      if (reg.waiting && navigator.serviceWorker.controller) onUpdate(reg);
    };
    notifyIfWaiting();
    reg.addEventListener("updatefound", () => {
      const sw = reg.installing;
      sw?.addEventListener("statechange", () => {
        if (sw.state === "installed") notifyIfWaiting();
      });
    });
    return reg;
  } catch {
    return null; // the app works without a worker
  }
}

/** User clicked "Reload": activate the waiting worker, then reload once. */
export function applyUpdate(reg: ServiceWorkerRegistration): void {
  let reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (reloaded) return;
    reloaded = true;
    window.location.reload();
  });
  if (reg.waiting) reg.waiting.postMessage({ type: "SKIP_WAITING" });
  else window.location.reload();
}

/** Delete every cache that is not the current build's static/shell cache. */
export async function clearAppCaches(): Promise<void> {
  try {
    if (typeof caches === "undefined") return;
    const keys = await caches.keys();
    await Promise.all(cachesToClear(keys).map((k) => caches.delete(k)));
  } catch {
    /* storage unavailable — nothing to clear */
  }
}
