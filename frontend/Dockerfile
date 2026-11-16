FROM node:24-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# NEXT_PUBLIC_API_URL is inlined into the browser bundle, so the image is built
# for one address (ADR-0021: the site's own origin, e.g. https://example.com).
ARG NEXT_PUBLIC_API_URL
ARG API_INTERNAL_URL=http://backend:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    API_INTERNAL_URL=$API_INTERNAL_URL \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build


FROM node:24-alpine

WORKDIR /app

ARG NEXT_PUBLIC_API_URL
ARG API_INTERNAL_URL=http://backend:8000
# The server checks both addresses at start (src/instrumentation-node.ts).
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000 \
    NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    API_INTERNAL_URL=$API_INTERNAL_URL

COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static

USER node

EXPOSE 3000

CMD ["node", "server.js"]
