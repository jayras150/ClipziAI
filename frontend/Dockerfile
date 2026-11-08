# syntax=docker/dockerfile:1
# =============================================================================
# Clipzi AI - Frontend (Next.js 14) production image
# Build : docker build -t <dockerhub-user>/clipzi-frontend:latest -f frontend/Dockerfile frontend
# Run   : docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=https://api.domain.com <image>
#
# NEXT_PUBLIC_API_URL di-inject SAAT CONTAINER JALAN (bukan saat build) lewat
# docker-entrypoint.sh -> /app/public/runtime-env.js, sehingga satu image yang
# sama bisa dipakai di laptop, Vast.ai, atau server mana pun tanpa rebuild.
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: install dependencies
# -----------------------------------------------------------------------------
FROM node:20-alpine AS deps

WORKDIR /app
# libc6-compat dibutuhkan beberapa paket native (mis. swc)
RUN apk add --no-cache libc6-compat

COPY package.json package-lock.json ./
RUN npm ci

# -----------------------------------------------------------------------------
# Stage 2: build aplikasi
# -----------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 \
    DOCKER_BUILD=1

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN npm run build

# -----------------------------------------------------------------------------
# Stage 3: runtime image (hanya file hasil standalone build)
# -----------------------------------------------------------------------------
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup -g 10001 -S nodejs \
    && adduser -u 10001 -S nextjs -G nodejs

# Output "standalone" hanya membawa dependency yang benar-benar dipakai.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

COPY --chown=nextjs:nodejs docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "require('http').get('http://127.0.0.1:'+(process.env.PORT||3000)+'/',r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["node", "server.js"]