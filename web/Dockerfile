# Build the React app, then serve the static bundle with nginx (which proxies
# /api and /health to the argus-server container on the compose network).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
# Keep HTTP_TOKEN always defined (default empty) so the nginx image's envsubst step
# substitutes ${HTTP_TOKEN} in the template instead of leaving it literal. Set it
# (matching argus-server's HTTP_TOKEN) to make the dashboard authenticate to the API.
ENV HTTP_TOKEN=""
# Templated config: the nginx image runs envsubst over /etc/nginx/templates/*.template
# at startup, writing the result to /etc/nginx/conf.d/default.conf.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
