/** @type {import('next').NextConfig} */
// Read at build time AND by the /api/session/* route handlers at runtime.
// Rewrites are compiled into the routes manifest during `next build`, so the
// value must be present when building (see infra docs).
const API_ORIGIN = process.env.API_ORIGIN || "http://127.0.0.1:8000";
const isProd = process.env.NODE_ENV === "production";
// Versions the service worker (/sw.js?v=…): each build installs a new worker,
// which purges the previous build's static cache on activation.
const BUILD_ID =
  process.env.NEXT_PUBLIC_BUILD_ID || process.env.GIT_SHA || `b${Date.now().toString(36)}`;

// Static security headers for every response. The Content-Security-Policy
// itself is set per request by src/middleware.ts because it carries a nonce.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  // Reset-password / invitation links carry tokens in the query string:
  // never leak them through Referer.
  { key: "Referrer-Policy", value: "no-referrer" },
  {
    key: "Permissions-Policy",
    value:
      "camera=(), microphone=(), geolocation=(), payment=(), usb=(), serial=()",
  },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
  ...(isProd
    ? [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }]
    : []),
];

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // No next/image optimisation: the app uses no raster images, and this keeps
  // `sharp` and its LGPL-3.0 libvips binaries out of the runtime image (the
  // web Dockerfile deletes them). See LICENSES.md.
  images: { unoptimized: true },
  env: { NEXT_PUBLIC_BUILD_ID: BUILD_ID },
  async headers() {
    return [
      { source: "/:path*", headers: securityHeaders },
      // QR check-in scans with the device camera (same origin only); every
      // other page keeps camera=() from securityHeaders. Later rules win.
      {
        source: "/checkin",
        headers: [
          {
            key: "Permissions-Policy",
            value:
              "camera=(self), microphone=(), geolocation=(), payment=(), usb=(), serial=()",
          },
        ],
      },
      // PWA. The worker must always be revalidated. The static offline page
      // is outside the middleware (no nonce), so it gets a script-free CSP.
      {
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, max-age=0" },
          { key: "Content-Security-Policy", value: "default-src 'self'; script-src 'self'" },
        ],
      },
      {
        source: "/offline.html",
        headers: [
          { key: "Cache-Control", value: "no-cache, max-age=0" },
          {
            key: "Content-Security-Policy",
            value:
              "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
          },
        ],
      },
      {
        source: "/manifest.webmanifest",
        headers: [{ key: "Content-Type", value: "application/manifest+json; charset=utf-8" }],
      },
      {
        source: "/api/session/:path*",
        headers: [{ key: "Cache-Control", value: "no-store" }],
      },
    ];
  },
  // Proxy API calls through the Next server: same-origin for the browser
  // (no CORS needed in production deployments behind one domain).
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${API_ORIGIN}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
