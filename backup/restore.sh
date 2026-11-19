#!/bin/sh
# Restores the database and the media volume from a restic snapshot (ADR-0026):
#
#   docker compose run --rm restore            # the latest snapshot
#   docker compose run --rm restore <snapshot>
#
# backend and github-worker must be stopped: the database is dropped and
# created again from the dump (DEPLOY.md, "Восстановление").
set -eu

snapshot=${1:-latest}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

restic restore "$snapshot" --host developer-platform --target "$work"
[ -f "$work/backup/database.dump" ] || { echo "restore: no database dump in $snapshot" >&2; exit 1; }

# --create with --clean drops the database and creates it from the dump, so no
# table of a later migration is left behind.
pg_restore --clean --if-exists --create --dbname=postgres "$work/backup/database.dump"

# The volume keeps its owner, the backend's user, which must delete files later.
owner=$(stat -c %u:%g /srv/media)
find /srv/media -mindepth 1 -delete
cp -a "$work/srv/media/." /srv/media/
chown -R "$owner" /srv/media
echo "restore: $snapshot restored"
