#!/bin/sh
# One backup to the restic repository (ADR-0026): a dump of the database, then
# the media volume, then old snapshots removed. Reads PG* and RESTIC_* from the
# environment; the repository is created once by hand (DEPLOY.md).
set -eu

mkdir -p /backup
pg_dump --format=custom --file=/backup/database.dump
restic backup --host developer-platform /backup/database.dump /srv/media
rm /backup/database.dump

restic forget --host developer-platform --prune --keep-daily 7 --keep-weekly 4 --keep-monthly 6
# Reads every pack's header: a damaged repository is found before a restore needs it.
if [ "$(date +%u)" = 1 ]; then
    restic check
fi
echo "backup: done"
