# The backend as one image. docker-compose.yml (repo root) runs it three ways:
#   release  migrate the database, then exit             (sh release.sh)
#   web      the API, admin and dashboard on port 8000   (the default command, gunicorn)
#   worker   background jobs                             (python manage.py run_jobs)
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # static files are collected into the image below and served by WhiteNoise
    DJANGO_COLLECTED_STATIC=1 \
    DJANGO_STATIC_ROOT=/app/staticfiles

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# collectstatic only reads code, but settings refuse to load without a secret key, so give it a
# throwaway one for this step only
RUN DJANGO_SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput --verbosity 0 \
    && useradd --system --uid 10001 --no-create-home kiosk

USER kiosk
EXPOSE 8000

# gunicorn reads WEB_CONCURRENCY for the number of worker processes (default 2 here)
CMD ["sh", "-c", "exec gunicorn kiosk_backend.wsgi --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-2} --access-logfile -"]
