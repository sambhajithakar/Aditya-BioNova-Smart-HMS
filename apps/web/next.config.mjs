/** @type {import('next').NextConfig} */
// Read at build time AND by the /api/session/* route handlers at runtime.
// Rewrites are compiled into the routes manifest during `next build`, so the
// value must be present when building (see infra docs).
const API_ORIGIN = process.env.API_ORIGIN || "http://127.0.0.1:8000";
const isProd = process.env.NODE_ENV === "production";

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
