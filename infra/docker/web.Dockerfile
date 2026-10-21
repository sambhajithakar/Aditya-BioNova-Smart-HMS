# syntax=docker/dockerfile:1
# Aditya BioNova Smart HMS — web image (multi-stage Next.js build).
# Build from the repository root:
#   docker build -f infra/docker/web.Dockerfile \
#     --build-arg API_ORIGIN=http://api:8000 -t hms-web:local .
#
# API_ORIGIN IS A BUILD-TIME SETTING (audit finding I1): next.config.mjs
# builds the `/api/v1/*` rewrite destination from process.env.API_ORIGIN and
# `next build` serialises it into .next/routes-manifest.json. Setting
# API_ORIGIN only at container run time has NO effect. Build one image per
# target API origin (compose passes it as a build arg).

# Base: node:22.23.3-alpine pinned by multi-arch index digest (resolved
# 2026-10-20). Bump tag+digest together (all three FROM lines) when patching.

# --- production-only node_modules -------------------------------------------
FROM node:22.23.3-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS prod-deps
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
# sharp (an optional dependency of next) ships prebuilt libvips binaries under
# LGPL-3.0. The app does no server-side image optimisation
# (next.config.mjs: images.unoptimized), so they are not shipped (LICENSES.md).
# `--omit=optional` is not used because it would also drop @next/swc.
# Playwright (an optional peer of next, a devDependency here) is not needed
# at runtime either.
RUN npm ci --omit=dev --no-audit --no-fund \
 && rm -rf node_modules/sharp node_modules/@img \
           node_modules/@playwright node_modules/playwright node_modules/playwright-core \
 && test -z "$(find node_modules -path '*libvips*' -print -quit)"

# --- build (needs devDependencies: typescript, @types/*) ---------------------
FROM node:22.23.3-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
ARG API_ORIGIN=http://api:8000
ENV API_ORIGIN=${API_ORIGIN}
RUN npm run build
# Fail the build if the rewrite destination was not baked in as requested.
RUN grep -qF "\"${API_ORIGIN}/api/v1/:path*\"" .next/routes-manifest.json \
 || { echo "API_ORIGIN '${API_ORIGIN}' not found in .next/routes-manifest.json" >&2; exit 1; }

# --- runtime -----------------------------------------------------------------
FROM node:22.23.3-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS runtime
WORKDIR /app
ARG API_ORIGIN=http://api:8000
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    API_ORIGIN=${API_ORIGIN}
COPY --chown=root:root --from=prod-deps /app/node_modules ./node_modules
COPY --chown=root:root apps/web/package.json apps/web/next.config.mjs ./
COPY --chown=root:root --from=build /app/.next ./.next
# `next start` writes only .next/cache and .next/server/route-cache at
# runtime (verified) — the only paths owned by the runtime user. Compose
# mounts both as tmpfs so the root filesystem can be read-only.
RUN mkdir -p .next/cache .next/server/route-cache \
 && chown -R node:node .next/cache .next/server/route-cache

USER node
EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/login').then(r=>process.exit(r.status<500?0:1)).catch(()=>process.exit(1))"]

# Exec form, node as PID 1 (no npm wrapper) so SIGTERM reaches Next directly.
CMD ["node", "node_modules/next/dist/bin/next", "start", "-H", "0.0.0.0", "-p", "3000"]
