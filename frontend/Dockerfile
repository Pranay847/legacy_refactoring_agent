# syntax=docker/dockerfile:1
# ============================================================================
# Frontend image — build the Vite SPA, serve it with nginx, and reverse-proxy
# /api/* to the backend container (so the browser never needs CORS or to know
# the backend's address). Build context is ./frontend.
# ============================================================================

# --- Build stage ---------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Only browser-safe (publishable) values — baked into the static bundle.
# VITE_API_BASE_URL defaults to the relative /api path that nginx proxies.
ARG VITE_API_BASE_URL=/api
ARG VITE_CLERK_PUBLISHABLE_KEY=
ARG VITE_SUPABASE_URL=
ARG VITE_SUPABASE_ANON_KEY=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY \
    VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY

RUN npm run build

# --- Serve stage ---------------------------------------------------------
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
