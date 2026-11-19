# Backups of the database and the media volume with restic (ADR-0026, step 9.5).
# The Postgres image gives a pg_dump of the server's major version.
FROM postgres:17-alpine

RUN apk add --no-cache restic

COPY --chmod=755 backup.sh restore.sh daily.sh /usr/local/bin/

# Not the Postgres entrypoint: this image never runs a server.
ENTRYPOINT []
CMD ["backup.sh"]
