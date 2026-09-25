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
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser   # then add a shop, drinks, recipes and stock at /admin
python manage.py runserver
```

Set `PAYNOW_UEN` and `PAYNOW_MERCHANT_NAME` in the environment so payment QR codes pay the right account.

Frontend (http://localhost:5173, proxies `/api` to the backend):

```
cd frontend/kiosk-app
npm install
npm run dev
```

The kiosk shows shop 1 by default; set `VITE_SHOP_ID` to use another shop.

## Mobile app

`mobile-app/` is an Expo (React Native) app for customers to pre-order from their phone,
using the same backend and look as the kiosk. It also runs in a browser:

```
cd mobile-app && npm install && npm run web
```

See [mobile-app/README.md](mobile-app/README.md) for running it on a phone.

## Tests

```
cd kiosk_backend && python manage.py test
```


## What's next

See [TODO.md](TODO.md).
