#!/bin/sh
# Updates the production stack on this host (step 9.4, ADR-0025):
#
#   ./deploy.sh                    # to origin/main
#   ./deploy.sh <commit>           # to a given commit
#   ./deploy.sh --rollback         # back to the commit before the last deploy
#
# An update with a migration makes a backup first (step 9.5, ADR-0026).
#
# Run by hand on the server, from the checkout with .env (DEPLOY.md).
set -eu

cd "$(dirname "$0")"
state=.deploy/previous

die() {
    echo "deploy: $*" >&2
    exit 1
}

rollback=0
target=origin/main
for arg in "$@"; do
    case "$arg" in
        --rollback) rollback=1 ;;
        -*) die "unknown option $arg" ;;
        *) target=$arg ;;
    esac
done

# Not `. .env`: the file holds secrets and is not a shell script.
server_name=$(sed -n 's/^SERVER_NAME=//p' .env | tail -n 1)
[ -n "$server_name" ] || die "SERVER_NAME is not set in .env"

# Local edits would be carried over or block the checkout.
[ -z "$(git status --porcelain --untracked-files=no)" ] || die "the checkout has local changes"

current=$(git rev-parse HEAD)
if [ "$rollback" = 1 ]; then
    [ -f "$state" ] || die "no previous deploy in $state"
    target=$(cat "$state")
else
    git fetch --quiet origin
fi
target=$(git rev-parse --verify --quiet "$target^{commit}") || die "unknown commit $target"

if [ "$target" = "$current" ]; then
    echo "deploy: already at $(git rev-parse --short HEAD)"
    exit 0
fi

# Migrations are not reverted automatically: an update with one needs a fresh
# backup of the database and the media volume, a rollback over one a restore.
if ! git diff --quiet "$current" "$target" -- backend/alembic/versions; then
    [ "$rollback" = 0 ] || die "migrations changed since $target; restore from the backup instead (DEPLOY.md)"
    echo "deploy: the update has migrations, backing up first"
    docker compose run --rm backup backup.sh || die "the backup failed; nothing is updated"
fi

mkdir -p .deploy
echo "$current" > "$state"
git checkout --quiet --detach "$target"
echo "deploy: $(git rev-parse --short "$current") -> $(git rev-parse --short HEAD)"

# migrate runs before backend and github-worker; `up` fails if it fails.
docker compose up -d --build

# -k: until Let's Encrypt issues the first certificate Nginx serves a
# self-signed one. --resolve: Nginx drops requests for any other host.
check() {
    curl -fsSk --max-time 5 -o /dev/null --resolve "$server_name:443:127.0.0.1" "https://$server_name$1"
}
tries=0
until check /api/v1/health && check /; do
    tries=$((tries + 1))
    [ "$tries" -lt 30 ] || die "the site does not answer after 60 s; see docker compose logs, ./deploy.sh --rollback"
    sleep 2
done
echo "deploy: done, the site answers"
