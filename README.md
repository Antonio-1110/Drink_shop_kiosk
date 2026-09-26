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
| `PAYNOW_PROXY_TYPE` | `UEN` (a company, the default) or `MOBILE` (a +65 number registered with PayNow). |
| `PAYNOW_PROXY_VALUE` | The company's UEN, or the mobile number as `+6591234567`. Required when `DJANGO_DEBUG` is off; development uses a dummy UEN. |
| `PAYNOW_MERCHANT_NAME` | Name shown in the customer's banking app (25 characters max). |
| `PAYNOW_MERCHANT_CITY`, `PAYNOW_MERCHANT_CATEGORY_CODE` | Optional; default `Singapore` and `0000`. |
| `PAYMENT_METHODS` | Payment methods customers can use, comma-separated (default `paynow`). |
| `PAYNOW_HOLD_MINUTES`, `PAYMENT_HOLD_MINUTES` | How long a PayNow payment (or any other method) stays open, default 10. The order's ingredients are held that long. |
| `PAYMENT_START_GRACE_MINUTES` | Time to start paying after ordering, or to try another method after one fails (default 2). |
| `ORDER_MAX_HOLD_MINUTES` | The longest any order can hold stock (default 30). |

How stock and payment fit together (`kiosk_backend/checkout/`):

- Placing an order holds its ingredients, so nobody else can buy them.
- The hold lasts as long as the customer's payment is open. Each payment method sets that time, so there is no single fixed timeout. Tapping **Cancel** on the payment screen releases the hold at once.
- When a payment runs out, the payment method is asked whether it was paid after all before the order is cancelled.
- Every payment method confirms payment through one function, `checkout.services.confirm_payment`. A payment that arrives after its order was cancelled gets the ingredients back if they are still there. If they have sold out, it is refunded, or flagged for staff under **Payment attempts** when the method can't refund automatically.
- Adding GrabPay, cards or a PayNow gateway means writing one `Provider` class in `checkout/providers.py`. Payment notifications arrive at `/checkout/webhooks/<method>/`.
- `python manage.py expire_orders` runs the same clean-up from a cron job. It also runs whenever the kiosk loads the menu or takes an order.
- Until a payment gateway is connected, staff confirm PayNow payments with **Mark as paid** under **Orders** in `/admin`.

Only the kiosk's ordering endpoints are public. Everything else, including `PATCH /operation/inventory/...`, needs a staff login.

Frontend (http://localhost:5173, proxies `/api` to the backend):

```
cd frontend/kiosk-app
npm install
npm run dev
```

The kiosk shows shop 1 by default; set `VITE_SHOP_ID` to use another shop.

PayNow QR codes are built by `kiosk_backend/payments/paynow.py`, a standalone module that follows the SGQR (EMVCo) format and has no Django dependency, so the kiosk's edge service can reuse it. Order codes are single-use, carry the amount and an `ORDER<id>` reference, and stop working after the day the order expires. A payment provider is still needed to confirm automatically that a customer paid.

Drink designer: `GET /ordering/designer/options/?shop_id=` lists the sizes, prices and ingredients customers can build a drink from, and an order item can carry `custom: [ingredient codes]` instead of `drink`. Amounts and price come from **Drink designer settings** in `/admin`, and the ingredients are held like any menu drink.

Pickup: every order gets a 6-digit PIN and a QR code, returned only in the reply to placing it. At the machine the customer types the PIN or scans the code, and the kiosk calls `POST /ordering/pickup/`. That hands over a paid order once and marks it collected. Attempts are limited per machine (`PICKUP_ATTEMPTS_PER_MINUTE`, default 10), so PINs can't be guessed.

## Testing the mobile app on a phone

```
./dev.sh --lan            # or ./dev.sh --lan --backend to skip the kiosk UI
```

The backend then listens on your network as well as on localhost, and prints the address phones use (`http://<your computer's IP>:8000`). Keep the phone on the same Wi-Fi. Without `--lan` the backend only answers on this computer. For a server, set `DJANGO_ALLOWED_HOSTS` to its host name instead.

No CORS setup is needed: the phone app isn't a browser page, and the browser versions of both apps go through their dev server's `/api` proxy.

## API contract

The backend's endpoints are described in [`kiosk_backend/openapi.yaml`](kiosk_backend/openapi.yaml) (OpenAPI 3). With the backend running, browse it at http://localhost:8000/api/docs/. After changing an endpoint, regenerate the file with `python manage.py spectacular --file openapi.yaml`; a test fails if it is out of date.

## Mobile app

`mobile-app/` is an Expo (React Native) app for customers to pre-order from their phone,
using the same backend and look as the kiosk. It also runs in a browser:

```
cd mobile-app && npm install && npm run web
```

See [mobile-app/README.md](mobile-app/README.md) for running it on a phone.

## Drink designer

Customers can build their own drink from the shop's ingredients, on the kiosk ("Design your own") and in the mobile app. Liquids share the cup by each ingredient's `share` (tea 3 : milk 2 : fruit 1), so picking more of them makes each smaller; toppings split the size's topping allowance. The sugar level sets the Brown sugar syrup and the ice level sets the ice.

Staff set prices and amounts in the Django admin: the designer settings hold a cup price per size, a default price per liquid and per topping, and the amounts per size, and each ingredient can override its price. Both apps read these from `GET /ordering/designer/options/`.

In the app, "Kiosk QR" shows the drink as a code like `DD1:144:OT-OM-TP`: size, sugar and ice digits, then each ingredient's short code. The kiosk's designer page reads it from a QR reader that types like a keyboard, from a `?code=` link, or typed into the box, and fills in the drink.

## Tests

```
cd kiosk_backend && DJANGO_DEBUG=1 python manage.py test
```


## What's next

See [TODO.md](TODO.md).
