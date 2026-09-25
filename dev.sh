#!/usr/bin/env bash
# Starts the Django backend and the Vite kiosk UI together for local development.
# Installs dependencies and runs migrations the first time (and again when they change).
#
#   ./dev.sh              set up if needed, then run backend + frontend
#   ./dev.sh --backend    run only the backend
#   ./dev.sh --frontend   run only the frontend
#   ./dev.sh --setup      install dependencies and migrate, then exit
#   ./dev.sh --test       run the backend tests, then exit
#
# Ctrl-C stops everything. The backend always runs on port 8000 because
# frontend/kiosk-app/vite.config.js proxies /api there.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/kiosk_backend"
FRONTEND="$ROOT/frontend/kiosk-app"
VENV="$BACKEND/.venv"
# local development settings (see kiosk_backend/kiosk_backend/settings.py)
export DJANGO_DEBUG="${DJANGO_DEBUG:-1}"
PY="$VENV/bin/python"

RUN_BACKEND=1
RUN_FRONTEND=1
case "${1:-}" in
  "") ;;
  --backend) RUN_FRONTEND=0 ;;
  --frontend) RUN_BACKEND=0 ;;
  --setup|--test) ;;
  -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "Unknown option: $1 (try --help)" >&2; exit 1 ;;
esac

log() { printf '\033[1;36m[dev]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[dev]\033[0m %s\n' "$*" >&2; exit 1; }

setup_backend() {
  local python
  python="$(command -v python3 || command -v python || true)"
  [ -n "$python" ] || die "Python 3 is not installed."
  if [ ! -x "$PY" ]; then
    log "Creating Python virtualenv in kiosk_backend/.venv"
    "$python" -m venv "$VENV"
  fi
  # reinstall only when requirements.txt is newer than the last install
  local stamp="$VENV/.requirements-installed"
  if [ ! -f "$stamp" ] || [ "$BACKEND/requirements.txt" -nt "$stamp" ]; then
    log "Installing backend dependencies"
    "$PY" -m pip install --quiet --upgrade pip
    "$PY" -m pip install --quiet -r "$BACKEND/requirements.txt"
    touch "$stamp"
  fi
  log "Applying database migrations"
  (cd "$BACKEND" && "$PY" manage.py migrate --noinput)
  # a brand-new database has no shops or drinks, so load the demo menu
  if ! (cd "$BACKEND" && "$PY" manage.py shell -c \
      "from operation.models import Shop; exit(0 if Shop.objects.exists() else 1)" >/dev/null 2>&1); then
    log "Empty database: loading demo data (run 'manage.py seed_demo' again any time to restock it)"
    (cd "$BACKEND" && "$PY" manage.py seed_demo)
  fi
}

setup_frontend() {
  command -v npm >/dev/null || die "Node.js / npm is not installed."
  local stamp="$FRONTEND/node_modules/.package-lock.json"
  if [ ! -f "$stamp" ] || [ "$FRONTEND/package-lock.json" -nt "$stamp" ]; then
    log "Installing frontend dependencies"
    # npm ci installs exactly what package-lock.json says and never rewrites it
    (cd "$FRONTEND" && npm ci --no-audit --no-fund)
  fi
}

if [ "${1:-}" = "--test" ]; then
  setup_backend
  cd "$BACKEND" && exec "$PY" manage.py test
fi

if [ "${1:-}" = "--setup" ]; then
  setup_backend
  setup_frontend
  log "Setup done."
  exit 0
fi
if [ "$RUN_BACKEND" = 1 ]; then setup_backend; fi
if [ "$RUN_FRONTEND" = 1 ]; then setup_frontend; fi

PIDS=()
cleanup() {
  trap - INT TERM EXIT
  log "Stopping..."
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT
trap "exit 0" INT TERM

if [ "$RUN_BACKEND" = 1 ]; then
  if ! (cd "$BACKEND" && "$PY" manage.py shell -c \
      "from django.contrib.auth import get_user_model; exit(0 if get_user_model().objects.filter(is_superuser=True).exists() else 1)" \
      >/dev/null 2>&1); then
    log "No admin user yet. Create one with: cd kiosk_backend && .venv/bin/python manage.py createsuperuser"
  fi
  log "Backend:  http://localhost:8000  (admin at /admin)"
  (cd "$BACKEND" && exec "$PY" manage.py runserver 8000) &
  PIDS+=($!)
fi

if [ "$RUN_FRONTEND" = 1 ]; then
  log "Frontend: http://localhost:5173"
  (cd "$FRONTEND" && exec npm run dev) &
  PIDS+=($!)
fi

# stop everything as soon as either server exits (works on macOS's bash 3.2, which lacks wait -n)
while :; do
  for pid in "${PIDS[@]}"; do
    kill -0 "$pid" 2>/dev/null || { log "A server exited."; exit 1; }
  done
  sleep 1
done
