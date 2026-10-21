/*
 * Aditya BioNova Smart HMS — service worker (hand-written, no dependencies).
 *
 * PATIENT-DATA RULE: this worker caches ONLY non-personal static files:
 *   - the static offline page, the manifest and the app icons ("shell")
 *   - content-hashed build assets under /_next/static/ (cache-first)
 * It NEVER caches:
 *   - /api/** (network-only: the request is not even intercepted)
 *   - HTML pages (network-only; on a network failure the static
 *     /offline.html is shown instead), so no user-specific page is stored
 *   - anything that is not a same-origin GET with a 200 "basic" response
 *
 * Versioning: the page registers /sw.js?v=<build id>. A new build id makes
 * the browser install a new worker, which waits until the user clicks
 * "Reload" in the update toast (message SKIP_WAITING). On activate every
 * cache whose name is not one of this version's is deleted.
 */
"use strict";

var VERSION = (function () {
  try {
    return new URL(self.location.href).searchParams.get("v") || "dev";
  } catch {
    return "dev";
  }
})();
var PREFIX = "hms-";
var SHELL_CACHE = PREFIX + "shell-" + VERSION;
var STATIC_CACHE = PREFIX + "static-" + VERSION;
var OFFLINE_URL = "/offline.html";
var SHELL_URLS = [
  OFFLINE_URL,
  "/manifest.webmanifest",
  "/icons/icon.svg",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

/**
 * Routing decision for a request (exported for unit tests via self.__hmsRoute).
 * Returns "network" (do not intercept), "static" (cache-first, hashed asset),
 * "shell" (cache-first, shell file) or "navigate" (network, offline fallback).
 */
function route(method, url, mode, origin) {
  if (method !== "GET") return "network";
  var u;
  try {
    u = new URL(url);
  } catch {
    return "network";
  }
  if (u.origin !== origin) return "network";
  var p = u.pathname;
  if (p === "/api" || p.indexOf("/api/") === 0) return "network";
  if (p.indexOf("/_next/static/") === 0) return "static";
  if (SHELL_URLS.indexOf(p) !== -1) return "shell";
  if (mode === "navigate") return "navigate";
  return "network";
}
self.__hmsRoute = route;
self.__hmsCaches = { SHELL_CACHE: SHELL_CACHE, STATIC_CACHE: STATIC_CACHE, PREFIX: PREFIX };

function cacheable(res) {
  return !!res && res.status === 200 && res.type === "basic";
}

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(SHELL_CACHE).then(function (c) {
      return c.addAll(
        SHELL_URLS.map(function (u) {
          return new Request(u, { cache: "reload", credentials: "omit" });
        }),
      );
    }),
  );
  // No skipWaiting() here: an update waits for the user's "Reload".
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches
      .keys()
      .then(function (keys) {
        return Promise.all(
          keys
            .filter(function (k) {
              return k !== SHELL_CACHE && k !== STATIC_CACHE;
            })
            .map(function (k) {
              return caches.delete(k);
            }),
        );
      })
      .then(function () {
        return self.clients.claim();
      }),
  );
});

self.addEventListener("message", function (event) {
  var data = event.data || {};
  if (data.type === "SKIP_WAITING") self.skipWaiting();
});

function cacheFirst(cacheName, request) {
  return caches.open(cacheName).then(function (cache) {
    return cache.match(request).then(function (hit) {
      if (hit) return hit;
      return fetch(request).then(function (res) {
        if (cacheable(res)) cache.put(request, res.clone());
        return res;
      });
    });
  });
}

self.addEventListener("fetch", function (event) {
  var req = event.request;
  var kind = route(req.method, req.url, req.mode, self.location.origin);
  if (kind === "network") return; // browser default: straight to the network, never cached
  if (kind === "static") {
    event.respondWith(cacheFirst(STATIC_CACHE, req));
    return;
  }
  if (kind === "shell") {
    event.respondWith(
      caches.match(req, { ignoreSearch: true }).then(function (hit) {
        return hit || fetch(req);
      }),
    );
    return;
  }
  // navigate: always the network (pages are per-user and per-request CSP);
  // only when the network fails, the static offline page.
  event.respondWith(
    fetch(req).catch(function () {
      return caches.match(OFFLINE_URL).then(function (hit) {
        return (
          hit ||
          new Response("Offline", { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } })
        );
      });
    }),
  );
});
