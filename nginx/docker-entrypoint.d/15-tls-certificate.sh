#!/bin/sh
# Points /etc/nginx/tls at the Let's Encrypt certificate of SERVER_NAME, or at a
# self-signed one until it is issued: without any certificate nginx does not
# start on 443, and certbot needs nginx on 80 to issue one (ADR-0021).
# After the first issuance `docker compose restart nginx` switches to it.
set -eu

: "${SERVER_NAME:?SERVER_NAME is not set}"
live="/etc/letsencrypt/live/${SERVER_NAME}"
tls=/etc/nginx/tls
mkdir -p "$tls"

if [ -f "$live/fullchain.pem" ] && [ -f "$live/privkey.pem" ]; then
    ln -sf "$live/fullchain.pem" "$tls/fullchain.pem"
    ln -sf "$live/privkey.pem" "$tls/privkey.pem"
    echo "$0: using the Let's Encrypt certificate for ${SERVER_NAME}"
else
    rm -f "$tls/fullchain.pem" "$tls/privkey.pem"
    openssl req -x509 -nodes -newkey rsa:2048 -days 30 \
        -subj "/CN=${SERVER_NAME}" -addext "subjectAltName=DNS:${SERVER_NAME}" \
        -keyout "$tls/privkey.pem" -out "$tls/fullchain.pem" 2>/dev/null
    echo "$0: no certificate for ${SERVER_NAME} yet, using a self-signed one"
fi
