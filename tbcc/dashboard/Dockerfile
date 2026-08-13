# TBCC dashboard — static Vite build + nginx reverse-proxy to island API.
# On the revenue island this is the always-on control plane UI (no home npm required).
#
# Build (from tbcc/):
#   docker build -f dashboard/Dockerfile -t tbcc-dashboard:local \
#     --build-arg TBCC_INTERNAL_API_KEY_PLACEHOLDER=unused .
#
# Runtime injects TBCC_INTERNAL_API_KEY into nginx so the browser never sees it.

FROM node:22-alpine AS build
WORKDIR /src
COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm ci || npm install
COPY dashboard/ ./
# Island container always talks to sibling api via /api (nginx).
ENV VITE_DEFAULT_API_TARGET=local
# Skip tsc -b in image builds (pre-existing dashboard type debt); Vite emits production assets.
RUN npx vite build

FROM nginx:1.27-alpine
# Official image envsubst: /etc/nginx/templates/*.template → /etc/nginx/conf.d/
COPY dashboard/docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /src/dist /usr/share/nginx/html
ENV TBCC_API_UPSTREAM=http://api:8000
ENV TBCC_API_UPSTREAM_HOST=api
ENV TBCC_API_UPSTREAM_PORT=8000
EXPOSE 80
