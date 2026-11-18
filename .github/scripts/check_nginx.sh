#!/bin/sh
# Runs the Nginx image alone and checks what `nginx -t` cannot: the media
# location and its headers, and the body limits (ADR-0021, ADR-0022).
#
#     sh .github/scripts/check_nginx.sh [image]
#
# No backend runs, so a request that Nginx lets through gets 502; only its
# own answers (200 from the volume, 404, 413) are checked.
set -eu

image=${1:-nginx-check}
name=nginx-check-run
volume=nginx-check-media
port=18443
host=example.com
dir=projects/11111111-1111-4111-8111-111111111111
key=$dir/22222222-2222-4222-8222-222222222222.webp
tmp=$(mktemp -d)
failed=0

cleanup() {
    docker rm -f "$name" >/dev/null 2>&1 || true
    docker volume rm "$volume" >/dev/null 2>&1 || true
    rm -rf "$tmp"
}
trap cleanup EXIT

docker volume create "$volume" >/dev/null
docker run --rm -v "$volume:/srv/media" --entrypoint sh "$image" -c \
    "mkdir -p /srv/media/$dir && printf webp > /srv/media/$key \
     && printf tmp > /srv/media/$dir/.22222222-2222-4222-8222-222222222222.webp.tmp"
docker run -d --name "$name" -e SERVER_NAME="$host" -v "$volume:/srv/media:ro" \
    -p "127.0.0.1:$port:443" "$image" >/dev/null

url() { echo "https://$host:$port$1"; }
request() { curl -sk --resolve "$host:$port:127.0.0.1" "$@"; }

ready=0
for _ in $(seq 1 30); do
    if request "$(url /media/)" >/dev/null; then ready=1; break; fi
    sleep 1
done
if [ "$ready" -ne 1 ]; then
    echo "FAIL nginx did not answer"; docker logs "$name"; exit 1
fi

check() {  # label, expected, actual
    if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: expected $2, got $3"; failed=1; fi
}
# No -o: curl for Windows (Git Bash) cannot open /dev/null; the last line is the code.
status() { { request -w '\n%{http_code}' "$@" || true; } | tail -n 1; }
header() {  # path, header name: the header's value (HEAD gets the same headers)
    request -I "$(url "$1")" | tr -d '\r' \
        | sed -n "s/^$2: //Ip" | head -n 1
}

check "a stored key is served" 200 "$(status "$(url "/media/$key")")"
check "its type" "image/webp" "$(header "/media/$key" Content-Type)"
check "it is cached for good" "public, max-age=31536000, immutable" \
    "$(header "/media/$key" Cache-Control)"
check "nosniff" nosniff "$(header "/media/$key" X-Content-Type-Options)"
check "HSTS is kept beside the media headers" "max-age=31536000" \
    "$(header "/media/$key" Strict-Transport-Security)"
check "a temporary file is not served" 404 \
    "$(status "$(url "/media/$dir/.22222222-2222-4222-8222-222222222222.webp.tmp")")"
check "no listing" 404 "$(status "$(url "/media/$dir/")")"
check "a missing key is 404" 404 \
    "$(status "$(url "/media/$dir/33333333-3333-4333-8333-333333333333.webp")")"

head -c 2000000 /dev/zero > "$tmp/2mb"
head -c 7000000 /dev/zero > "$tmp/7mb"
upload=/api/v1/projects/44444444-4444-4444-8444-444444444444/screenshots
post() {  # body file, path: the status (the body goes through stdin, see status)
    status -X POST -H "Content-Type: application/octet-stream" --data-binary @- \
        "$(url "$2")" <"$tmp/$1"
}
check "7 MB to the upload path is refused" 413 "$(post 7mb "$upload")"
check "2 MB to the upload path goes through (502: no backend)" 502 "$(post 2mb "$upload")"
check "2 MB elsewhere in the API is refused" 413 "$(post 2mb /api/v1/projects)"

exit "$failed"
