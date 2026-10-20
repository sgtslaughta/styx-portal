FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
# Pull latest patched OS packages so the image clears fixable HIGH/CRITICAL CVEs
# (e.g. libcrypto3/libxml2) flagged by the CI Trivy image scan. Rebuilds re-patch.
RUN apk upgrade --no-cache
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template
ENV NGINX_RESOLVER=127.0.0.11 BACKEND_HOST=backend:8000
EXPOSE 3000
