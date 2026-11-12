FROM node:24-bookworm-slim AS build
WORKDIR /build
ENV NEXT_TELEMETRY_DISABLED=1
COPY sleep_frontend/package.json sleep_frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY sleep_frontend/ ./
RUN npm run build

FROM node:24-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 DALJAM_DEMO_ONLY=1 PORT=10000 HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /build/.next/standalone/ ./web/
COPY --from=build --chown=node:node /build/.next/static/ ./web/.next/static/
COPY --from=build --chown=node:node /build/public/ ./web/public/
COPY --chown=node:node deploy/start-demo.mjs ./deploy/start-demo.mjs
USER node
EXPOSE 10000
CMD ["node", "deploy/start-demo.mjs"]
