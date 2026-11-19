#!/bin/sh
# The daily round of the backup service (ADR-0026, ADR-0027): a backup, then the
# free space of the disk that holds the volumes. Each result pings its
# dead-man's switch: the URL on success, the URL + /fail on failure. An empty
# URL skips the ping. The URLs are secrets: wget's errors, which print them, are
# dropped.
set -u

ping() {
    [ -n "$1" ] || return 0
    wget -q -T 10 -O /dev/null "$1$2" 2> /dev/null || echo "monitoring: a ping failed"
}

if backup.sh; then
    ping "${BACKUP_HEARTBEAT_URL:-}" ""
else
    echo "backup failed"
    ping "${BACKUP_HEARTBEAT_URL:-}" /fail
fi

# The media volume lives on the Docker host's disk, with the database's volume.
used=$(df -P /srv/media | awk 'NR == 2 { sub("%", "", $5); print $5 }')
if [ "$used" -ge "${DISK_ALERT_PERCENT:-80}" ]; then
    echo "disk: ${used}% used"
    ping "${DISK_HEARTBEAT_URL:-}" /fail
else
    ping "${DISK_HEARTBEAT_URL:-}" ""
fi
