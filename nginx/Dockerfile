FROM nginx:1.28-alpine

# openssl makes the temporary self-signed certificate (15-tls-certificate.sh).
RUN apk add --no-cache openssl

# The image's entrypoint renders templates/*.template into conf.d with envsubst
# (only variables set in the environment, so nginx's own $host etc. stay) and
# runs docker-entrypoint.d/*.sh before nginx starts.
COPY templates/ /etc/nginx/templates/
COPY docker-entrypoint.d/ /docker-entrypoint.d/
RUN chmod +x /docker-entrypoint.d/*.sh \
    && rm -f /etc/nginx/conf.d/default.conf \
    && mkdir -p /var/www/certbot
