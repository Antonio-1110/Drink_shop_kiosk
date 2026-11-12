#!/bin/sh
# Runs once before each deploy starts the web server and the worker (the "release" service in
# docker-compose.yml): brings the database up to date, then exits.
set -eu
python manage.py migrate --noinput
python manage.py check --deploy --fail-level ERROR
# staging and demos: load the demo shops and menu into an empty database
if [ "${SEED_DEMO:-}" = 1 ]; then
  if python manage.py shell -c "from operation.models import Shop; exit(0 if Shop.objects.exists() else 1)"; then
    echo "Database already has shops, not loading demo data."
  else
    python manage.py seed_demo
  fi
fi
