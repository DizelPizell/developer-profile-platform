#!/bin/sh
# Checks deploy.sh against a throwaway repository, with docker, curl and sleep
# replaced by stubs: the migration gate, the rollback and the failed check.
#
#   sh .github/scripts/check_deploy.sh
set -eu

script=$(cd "$(dirname "$0")/../.." && pwd)/deploy.sh
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

mkdir "$work/bin"
# The stub logs its call and fails a backup while $work/backup-fails exists.
printf '#!/bin/sh\necho "docker $*" >> "%s/docker.log"\ncase "$*" in *backup.sh*) [ ! -f "%s/backup-fails" ] ;; esac\n' "$work" "$work" > "$work/bin/docker"
printf '#!/bin/sh\n[ ! -f "%s/down" ]\n' "$work" > "$work/bin/curl"
printf '#!/bin/sh\n' > "$work/bin/sleep"
chmod +x "$work/bin/"*
PATH=$work/bin:$PATH

git init --quiet --bare "$work/origin.git"
git clone --quiet "$work/origin.git" "$work/seed" 2>/dev/null
git clone --quiet "$work/origin.git" "$work/server" 2>/dev/null
cp "$script" "$work/server/deploy.sh"
echo "SERVER_NAME=example.com" > "$work/server/.env"

commit() { # commit <file>: adds the file in the seed and pushes it
    mkdir -p "$work/seed/$(dirname "$1")"
    echo "$1" > "$work/seed/$1"
    git -C "$work/seed" add "$1"
    git -C "$work/seed" -c user.name=ci -c user.email=ci@example.com commit --quiet -m "$1"
    git -C "$work/seed" push --quiet origin HEAD:main
    git -C "$work/seed" rev-parse HEAD
}
at() { git -C "$work/server" rev-parse HEAD; }
deploy() { sh "$work/server/deploy.sh" "$@" > "$work/out" 2>&1; }
fail() {
    echo "FAIL: $*"
    cat "$work/out"
    exit 1
}

first=$(commit README)
git -C "$work/server" fetch --quiet origin
git -C "$work/server" checkout --quiet --detach "$first"

second=$(commit app.py)
deploy || fail "a plain update"
[ "$(at)" = "$second" ] || fail "a plain update ends at origin/main"
grep -q "up -d --build" "$work/docker.log" || fail "a plain update runs docker compose up"

grep -q "backup.sh" "$work/docker.log" && fail "a plain update makes no backup"

third=$(commit backend/alembic/versions/0001.py)
touch "$work/backup-fails"
deploy && fail "an update with a migration stops when the backup fails"
[ "$(at)" = "$second" ] || fail "an update without a backup keeps the commit"
rm "$work/backup-fails"
: > "$work/docker.log"
deploy || fail "an update with a migration"
[ "$(at)" = "$third" ] || fail "an update with a migration ends at origin/main"
[ "$(head -n 1 "$work/docker.log")" = "docker compose run --rm backup backup.sh" ] ||
    fail "an update with a migration backs up before anything else"

deploy --rollback && fail "a rollback over a migration is refused"
[ "$(at)" = "$third" ] || fail "a refused rollback keeps the commit"

fourth=$(commit web.ts)
deploy || fail "an update after the migration"
deploy --rollback || fail "a rollback without migrations"
[ "$(at)" = "$third" ] || fail "a rollback returns to the previous commit"

touch "$work/down"
deploy && fail "a site that does not answer fails the deploy"
grep -q "does not answer" "$work/out" || fail "a failed check says so"
[ "$(at)" = "$fourth" ] || fail "the failed deploy still checked out its commit"

echo "deploy.sh: all checks passed"
