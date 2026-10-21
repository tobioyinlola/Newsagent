FROM node:22-slim AS build
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install
COPY . .
ARG VITE_API_URL
RUN pnpm build

FROM caddy:2-alpine
COPY --from=build /app/dist /srv
RUN printf ':{$PORT:8080} {\n  root * /srv\n  try_files {path} /index.html\n  file_server\n}\n' > /etc/caddy/Caddyfile
