# Drink_shop_kiosk

Self-order kiosk for a drink shop: a React + Vite touchscreen UI and a Django REST backend that tracks per-shop ingredient stock.

## Run it locally

The quick way, from the repo root (needs Python 3 and Node.js):

```
./dev.sh           # installs dependencies, migrates, starts both; Ctrl-C stops them
./dev.sh --help    # run only one side, set up only, or run the tests
```

Or by hand:

Backend (http://localhost:8000):

```
cd kiosk_backend
export DJANGO_DEBUG=1              # local development settings
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo          # demo shops, drinks, recipes and stock
python manage.py createsuperuser    # for /admin
python manage.py runserver
```

Settings come from environment variables:

| Variable | What it does |
| --- | --- |
| `DJANGO_DEBUG` | `1` for local development. Leave unset in production. |
| `DJANGO_SECRET_KEY` | Required when `DJANGO_DEBUG` is off. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names the server answers to in production. |
| `PAYNOW_UEN`, `PAYNOW_MERCHANT_NAME` | The account the PayNow QR codes pay. |
| `ORDER_PAYMENT_TIMEOUT_MINUTES` | How long an unpaid order holds its ingredients (default 10). |

Unpaid orders are cancelled and their stock returned after the timeout. This happens whenever the kiosk loads the menu or places an order; `python manage.py expire_orders` does the same from a cron job. Staff mark orders paid (or cancel them) from **Orders** in `/admin`.

Only the kiosk's ordering endpoints are public. Everything else, including `PATCH /operation/inventory/...`, needs a staff login.

Frontend (http://localhost:5173, proxies `/api` to the backend):

```
cd frontend/kiosk-app
npm install
npm run dev
```

The kiosk shows shop 1 by default; set `VITE_SHOP_ID` to use another shop.

## Testing the mobile app on a phone

```
./dev.sh --lan            # or ./dev.sh --lan --backend to skip the kiosk UI
```

The backend then listens on your network as well as on localhost, and prints the address phones use (`http://<your computer's IP>:8000`). Keep the phone on the same Wi-Fi. Without `--lan` the backend only answers on this computer. For a server, set `DJANGO_ALLOWED_HOSTS` to its host name instead.

No CORS setup is needed: the phone app isn't a browser page, and the browser versions of both apps go through their dev server's `/api` proxy.

## API contract

The backend's endpoints are described in [`kiosk_backend/openapi.yaml`](kiosk_backend/openapi.yaml) (OpenAPI 3). With the backend running, browse it at http://localhost:8000/api/docs/. After changing an endpoint, regenerate the file with `python manage.py spectacular --file openapi.yaml`; a test fails if it is out of date.

## Tests

```
cd kiosk_backend && DJANGO_DEBUG=1 python manage.py test
```


## What's next

See [TODO.md](TODO.md).
