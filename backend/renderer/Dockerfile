FROM node:22-bookworm-slim
# Chromium runtime libs + FFmpeg for Remotion
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libnss3 libdbus-1-3 libatk1.0-0 libasound2 libxrandr2 libxkbcommon-dev libxfixes3 libxcomposite1 \
    libxdamage1 libgbm-dev libatk-bridge2.0-0 libcups2 libpango-1.0-0 libcairo2 fonts-liberation ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# the same pnpm major as the lockfile and CI (a newer one ignores package.json's pnpm.overrides)
RUN corepack enable && corepack prepare pnpm@10.28.0 --activate
WORKDIR /app
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN npx remotion browser ensure
ENV NODE_ENV=production PORT=4000
EXPOSE 4000
HEALTHCHECK CMD node -e "fetch('http://localhost:'+process.env.PORT+'/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["npx", "tsx", "src/server/index.ts"]
