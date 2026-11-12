#!/usr/bin/env bash
# Puts a backup from deploy/backup.sh back into the database, replacing what's there.
# Run it on the server, from the repo root:
#
#   deploy/restore.sh backups/production/kiosk-20261112-0330.dump
#
# For staging, say which copy to restore into:
#   COMPOSE="docker compose -p kiosk-staging --env-file .env.staging" deploy/restore.sh backups/staging/kiosk-....dump
#
# The web server and the worker are stopped while it runs, so no orders come in half-way.
set -euo pipefail

DUMP="${1:?usage: deploy/restore.sh <backup file>}"
[ -f "$DUMP" ] || { echo "No such file: $DUMP" >&2; exit 1; }
read -r -a COMPOSE <<< "${COMPOSE:-docker compose}"

echo "This replaces everything in the database with $DUMP."
read -r -p "Type 'restore' to go on: " answer
[ "$answer" = restore ] || { echo "Stopped, nothing changed."; exit 1; }

"${COMPOSE[@]}" stop web worker
# pg_restore runs inside the database container; its own login settings come from the container
# shellcheck disable=SC2016  # expanded inside the container, on purpose
"${COMPOSE[@]}" exec -T db sh -c \
  'pg_restore --clean --if-exists --no-owner --single-transaction -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$DUMP"
# a backup from an older version of the code may need newer migrations
"${COMPOSE[@]}" run --rm release
"${COMPOSE[@]}" start web worker
echo "Restored $DUMP."
