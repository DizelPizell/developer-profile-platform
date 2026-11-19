#!/bin/sh
# Backs up a throwaway database and media volume with the backup image, changes
# both, restores the snapshot and checks that the changes are gone (ADR-0026).
#
#   docker build -t backup-check backup
#   sh .github/scripts/check_backup.sh backup-check
set -eu

image=$1
name=backup-check-$$
media=$name-media
repo=$name-repo

cleanup() {
    docker rm -f "$name-pg" > /dev/null 2>&1 || true
    docker network rm "$name" > /dev/null 2>&1 || true
    docker volume rm "$media" "$repo" > /dev/null 2>&1 || true
}
trap cleanup EXIT

fail() {
    echo "FAIL: $*"
    exit 1
}

docker network create "$name" > /dev/null
docker run -d --name "$name-pg" --network "$name" --network-alias postgres \
    -e POSTGRES_USER=ci -e POSTGRES_PASSWORD=ci -e POSTGRES_DB=app postgres:17-alpine > /dev/null

psql() { docker exec "$name-pg" psql -U ci -d app -tAq -v ON_ERROR_STOP=1 -c "$1"; }
run() {
    docker run --rm --network "$name" \
        -e PGHOST=postgres -e PGUSER=ci -e PGPASSWORD=ci -e PGDATABASE=app \
        -e RESTIC_REPOSITORY=/repo -e RESTIC_PASSWORD=ci \
        -v "$media:/srv/media" -v "$repo:/repo" "$image" "$@"
}

tries=0
until psql "select 1" > /dev/null 2>&1; do
    tries=$((tries + 1))
    [ "$tries" -lt 30 ] || fail "postgres did not start"
    sleep 1
done

psql "create table shots (key text); insert into shots values ('a')"
run sh -c 'mkdir -p /srv/media/projects && echo a > /srv/media/projects/a.webp && chown -R 1000:1000 /srv/media'

run restic init > /dev/null
run backup.sh > /dev/null || fail "backup.sh"

# After the backup: a row, a table of a later migration and the files change.
psql "insert into shots values ('b'); create table later (id int)"
# The volume's owner changes as on a new host, where the backend's uid differs.
run sh -c 'rm /srv/media/projects/a.webp && echo b > /srv/media/projects/b.webp && chown -R 2000:2000 /srv/media'

run restore.sh > /dev/null || fail "restore.sh"

[ "$(psql "select string_agg(key, ',') from shots")" = "a" ] || fail "the rows are restored"
[ -z "$(psql "select to_regclass('later')")" ] || fail "a table made after the backup is gone"
files=$(run sh -c 'cd /srv/media && find . -type f | sort | tr "\n" " "')
[ "$files" = "./projects/a.webp " ] || fail "the files are restored, got: $files"
owner=$(run stat -c %u:%g /srv/media/projects/a.webp)
[ "$owner" = "2000:2000" ] || fail "the files keep the volume's owner, got: $owner"

echo "backup: backup and restore checked"
