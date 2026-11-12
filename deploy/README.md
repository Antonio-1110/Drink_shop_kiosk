# Running the backend with Docker

`docker-compose.yml` (repo root) runs the cloud backend as five containers:

| Service | What it does |
| --- | --- |
| `db` | PostgreSQL 17. Its data lives in the `pgdata` volume. |
| `release` | Runs the migrations (and loads the demo menu when `SEED_DEMO=1`), then exits. The other backend containers wait for it. |
| `web` | gunicorn serving the API, `/admin/`, the dashboard and the API docs on port 8000. Static files are built into the image and served by WhiteNoise. `/healthz/` says whether it's up and can reach the database. |
| `worker` | `manage.py run_jobs`: cancels unpaid orders on time, marks silent machines offline, runs the daily order check. |
| `backup` | `pg_dump` every day at `BACKUP_AT` (Singapore time), kept for `BACKUP_KEEP_DAYS`. |
| `caddy` | Only with `--profile https`: HTTPS with automatic certificates, in front of `web`. |

`./dev.sh` is unchanged: it still uses SQLite and `runserver`. The backend only switches to
PostgreSQL when `DATABASE_URL` is set, which `docker-compose.yml` does for you.

## Try it on your computer

Needs Docker Desktop (or Docker Engine with the compose plugin).

```
cp .env.example .env
# in .env, set POSTGRES_PASSWORD and DJANGO_SECRET_KEY to long random strings
docker compose up -d --build
docker compose exec web python manage.py seed_demo          # demo shops and menu
docker compose exec web python manage.py createsuperuser
```

Then open http://localhost:8000/admin/. `docker compose logs -f web worker` shows what's happening,
`docker compose down` stops it (the database is kept; `down -v` deletes it).

## Put it on a server

Any Linux server with Docker works (see "Choosing a host" below).

1. Point the domain at the server, e.g. an `A` record for `api.example.sg` (and
   `staging-api.example.sg` if you want staging there too).
2. On the server: install Docker, clone this repo, `cp .env.example .env`, and fill in `.env`:
   `POSTGRES_PASSWORD`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS=api.example.sg`,
   `DJANGO_HTTPS=1`, `SITE_ADDRESS=api.example.sg`, `PAYNOW_PROXY_VALUE`, and the email settings
   for staff alerts.
3. `docker compose --profile https up -d --build`
4. `docker compose exec web python manage.py createsuperuser`
5. Open the firewall for ports 80 and 443 only (and SSH). The web container itself only listens on
   the server's own `127.0.0.1`.

To deploy a new version: `git pull && docker compose --profile https up -d --build`. The `release`
container migrates the database before the new web server and worker start.

Once HTTPS has worked for a while, raise `DJANGO_HSTS_SECONDS` to `31536000` (one year).

## Staging

Staging is a second copy with its own database, its own secrets and the demo menu, for trying a
change before the shops get it. It runs from the same `docker-compose.yml` under another project name:

```
cp .env.staging.example .env.staging     # fill in POSTGRES_PASSWORD and DJANGO_SECRET_KEY (not production's)
docker compose -p kiosk-staging --env-file .env.staging up -d --build
```

On the same server as production it listens on port 8001, and production's Caddy serves it at
`STAGING_SITE_ADDRESS` (set that in production's `.env`, and add the staging domain to
`DJANGO_ALLOWED_HOSTS` and set `DJANGO_HTTPS=1` in `.env.staging`). Every `docker compose` command
for staging needs the same `-p kiosk-staging --env-file .env.staging`.

## Backups

The `backup` container saves `kiosk-YYYYMMDD-HHMM.dump` into `backups/production/` on the server
(`backups/staging/` for staging) every day, and once when it starts.

- Take one now: `docker compose run --rm backup --once`
- Restore one (stops the web server and worker while it runs, asks first):
  `deploy/restore.sh backups/production/kiosk-20261112-0330.dump`
- Restore into staging:
  `COMPOSE="docker compose -p kiosk-staging --env-file .env.staging" deploy/restore.sh backups/staging/<file>`

These backups are on the same server as the database, so they don't survive losing the server.
Also turn on the host's own daily server backups or snapshots, or copy `backups/` somewhere else
(object storage, another machine) on a schedule. Try a restore into staging now and then, so you
know the backups work.

## Choosing a host

Hosting in Singapore keeps the kiosks' requests fast and keeps customer data in Singapore (PDPA).
Prices are per month in US dollars, before GST, as checked in November 2026; check the provider's
page before you sign up.

| Option | Roughly | Notes |
| --- | --- | --- |
| **One server** (DigitalOcean Droplet, Singapore, 2 GB) running this compose file, production and staging together | about $12 + $3.60 daily server backups = **~$16** | Recommended to start. Cheapest, and it's exactly what's tested here. You look after the server (updates, disk). |
| Same server, but the database on DigitalOcean Managed PostgreSQL | ~$16 + $15 = **~$31** (+$15 for a staging database) | The provider handles database backups, restores to a point in time and upgrades. Needs a small change to `docker-compose.yml` so the backend uses that database instead of the `db` container. |
| AWS Lightsail Singapore 2 GB instance | **~$12** | Like the first option, on AWS. Snapshots are extra. |
| Render (Singapore region): web service + background worker + Postgres | several separate charges, typically **$25–45**, doubled for staging | No server to look after; the Dockerfile deploys as is. Paid Postgres plans include point-in-time backups. |
| Hetzner Singapore (CPX12) | ~$18 | Hetzner raised Singapore prices in June 2026, so it's no longer the cheap option there. |

Whichever you pick, you also need a domain (~$15–30 a year for `.sg`, less for `.com`) and an email
service for staff alerts (most have a free tier).
