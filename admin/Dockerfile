FROM node:22-slim AS build
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install
COPY . .
ARG VITE_API_URL
# API_ORIGIN / STORAGE_ORIGIN are baked into the Content-Security-Policy at build time
ARG API_ORIGIN
ARG STORAGE_ORIGIN
ENV API_ORIGIN=$API_ORIGIN STORAGE_ORIGIN=$STORAGE_ORIGIN
RUN pnpm build && node scripts/gen-caddyfile.mjs

FROM caddy:2-alpine
COPY --from=build /app/dist /srv
COPY --from=build /app/Caddyfile /etc/caddy/Caddyfile
