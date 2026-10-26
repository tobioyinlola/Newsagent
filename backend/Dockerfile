# One image for the whole backend: the API, the Celery worker, the Celery scheduler and the Remotion renderer, run together by
# start.sh. (The renderer can still be split into its own service later: renderer/Dockerfile is kept for that.)

FROM node:22-bookworm-slim AS renderer-build
# the same pnpm major as the lockfile and CI (a newer one ignores package.json's pnpm.overrides)
RUN corepack enable && corepack prepare pnpm@10.28.0 --activate
WORKDIR /renderer
COPY renderer/package.json renderer/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile
COPY renderer/ .
RUN node_modules/.bin/remotion browser ensure

FROM python:3.12-slim-bookworm
# FFmpeg and Chromium's runtime libraries (Remotion renders in Chromium)
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ffmpeg libnss3 libdbus-1-3 libatk1.0-0 libasound2 libxrandr2 libxkbcommon-dev libxfixes3 libxcomposite1 \
    libxdamage1 libgbm-dev libatk-bridge2.0-0 libcups2 libpango-1.0-0 libcairo2 fonts-liberation ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# Node runs the renderer's server; same Debian release as the build stage above, so the native parts match
COPY --from=renderer-build /usr/local/bin/node /usr/local/bin/node
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen || uv sync --no-dev
COPY . .
COPY --from=renderer-build /renderer/node_modules /app/renderer/node_modules
ENV PATH="/app/.venv/bin:$PATH" PORT=8000 NODE_ENV=production
EXPOSE 8000
CMD ["bash", "start.sh"]
