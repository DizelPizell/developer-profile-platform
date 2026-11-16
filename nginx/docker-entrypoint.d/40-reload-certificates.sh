#!/bin/sh
# Picks up certificates the certbot service renews: nginx reads them only at
# start and on reload. Let's Encrypt renews 30 days ahead, so 6 hours is plenty.
(while sleep 6h; do nginx -s reload; done) &
