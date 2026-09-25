# Drink_shop_kiosk

Self-order kiosk for a drink shop: a React + Vite touchscreen UI and a Django REST backend that tracks per-shop ingredient stock.

## Run it locally

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

## Tests

```
cd kiosk_backend && python manage.py test
```
