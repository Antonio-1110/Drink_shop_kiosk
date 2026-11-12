#!/bin/sh
# Daily database backups, run by the "backup" service in docker-compose.yml (postgres image).
#
# Takes a backup when it starts, then every day at BACKUP_AT (HH:MM, in TZ), into /backups as
# kiosk-YYYYMMDD-HHMM.dump (pg_dump custom format; restore with deploy/restore.sh). Backups older
# than BACKUP_KEEP_DAYS days are deleted. /backups is a folder on the server (BACKUP_DIR), so the
# host's own snapshot or sync tool can copy it off the machine.
#
#   sh backup.sh --once    take one backup now and exit
#                          (docker compose run --rm backup --once)
set -eu

BACKUP_AT="${BACKUP_AT:-03:30}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
DIR=/backups

log() { echo "$(date '+%Y-%m-%d %H:%M:%S %Z') backup: $*"; }

take_backup() {
  name="kiosk-$(date +%Y%m%d-%H%M).dump"
  # write to a temporary name first, so a half-written file never looks like a good backup
  if pg_dump --format=custom --no-owner --file="$DIR/.$name.partial"; then
    mv "$DIR/.$name.partial" "$DIR/$name"
    log "saved $name ($(du -h "$DIR/$name" | cut -f1))"
  else
    rm -f "$DIR/.$name.partial"
    log "FAILED, will try again at the next scheduled time"
    return 1
  fi
  find "$DIR" -maxdepth 1 -name 'kiosk-*.dump' -mtime +"$KEEP_DAYS" -print -delete \
    | sed 's|^|removed old backup |'
}

seconds_until() {
  # seconds from now until the next HH:MM today or tomorrow (busybox date)
  now=$(date +%s)
  target=$(date -d "$(date +%Y-%m-%d) $1:00" +%s)
  [ "$target" -gt "$now" ] || target=$((target + 86400))
  echo $((target - now))
}

mkdir -p "$DIR"
if [ "${1:-}" = "--once" ]; then
  take_backup
  exit
fi

take_backup || true
while :; do
  wait_for=$(seconds_until "$BACKUP_AT")
  log "next backup in $((wait_for / 60)) minutes (at $BACKUP_AT)"
  sleep "$wait_for"
  take_backup || true
done
