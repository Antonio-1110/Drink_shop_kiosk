# To-do

Where the code is today versus where it is headed: an automated drink kiosk platform for Singapore
with a Django cloud backend, a Python edge service on each kiosk, a kiosk touchscreen UI, a mobile
ordering app, SGQR/GrabPay payments, HPB Nutri-Grade labels and a dairy temperature safety lock.

What works now: a React + Vite kiosk UI that lists drinks the shop has stock for, a cart with
size/sugar/ice, order placement that deducts stock under a row lock, and a PayNow SGQR code for the
order. Run it with `./dev.sh`.

Items marked **(models)** touch `operation/models.py` or `ordering/models.py`, which the
"Kiosk models and Nutri-Grade" work is changing right now (Kiosk model, richer Ingredient and
Inventory, Nutri-Grade module). Fold them into that work or do them after it lands.

## 1. Fix before building more

- [ ] **Unpaid orders keep their stock forever.** `key_in_order` deducts stock when the order is
      created, but nothing marks an order paid, and nothing cancels an abandoned one. Add an order
      expiry (for example 10 minutes in `PENDING`) that sets `CANCELLED` and puts the stock back,
      plus a way to mark an order paid (admin action now, payment webhook later).
- [ ] **Every endpoint is public.** DRF's default permission is `AllowAny`, so anyone who can reach
      the server can `PATCH /operation/inventory/...` and change stock. Put inventory behind
      staff auth or an API key per kiosk, and set `DEFAULT_PERMISSION_CLASSES` in settings.
- [ ] **Settings are dev-only.** `SECRET_KEY` is committed, `DEBUG = True`, `ALLOWED_HOSTS = []`.
      Read all three from environment variables (with a `.env.example`), and rotate the key.
- [ ] **Sales history can be deleted by accident** **(models)**. `Order.shop` and `OrderItem.drink`
      use `on_delete=CASCADE`, so deleting a shop or a drink wipes its orders. Use `PROTECT`, and
      add `is_active` to `Drink` so drinks can be retired instead of deleted.
- [ ] **Order line prices are not stored** **(models)**. Revenue is computed from the drink's
      current price, but each `OrderItem` should keep the price it sold at so reports stay right
      after a price change.
- [ ] Small cleanups in `operation/views.py`: remove the stray `print(1)` and the `try/except`
      around `get_object_or_404` (it never raises `DoesNotExist`). In `ordering/views.py`, stop
      returning `str(e)` to the client on unexpected errors, and rename `avaliable_drinks`.
- [ ] Delete `common/models/drinks.py`; it is an unused plain Python class from before Django.
- [ ] Sugar and ice default to 0% on the model but 100% in the UI **(models)**; pick one.

## 2. Make it easy to work on

- [ ] **Demo data.** A fresh database has no shops or drinks, so the kiosk shows an empty menu.
      Add a `seed_demo` management command (a shop, ingredients, stock, a few drinks with recipes)
      and have `./dev.sh` offer to run it on an empty database. Write it after the models work
      lands so it matches the new schema.
- [ ] **CI.** A GitHub Actions workflow that runs `python manage.py test`, `npm run lint` and
      `npm run build` on every pull request.
- [ ] **API contract.** Add `drf-spectacular` to publish an OpenAPI schema, move routes under
      `/api/v1/`, and generate the frontend client from it. The mobile app will need the same
      contract.
- [ ] Replace the Vite boilerplate in `frontend/kiosk-app/README.md`, and add a few frontend tests
      (Vitest + Testing Library) for the cart and checkout flow.
- [ ] Merge PR #1 so `main` has the real code, then delete the old `branch-backend` and
      `branch-frontend` branches.

## 3. After the models work lands

- [ ] Update `ordering/utils.py`, `views.py`, `serializer.py` and `tests.py` for the renamed or
      extended models (for example `Shop` becoming `Kiosk`), and the frontend's `SHOP_ID`.
- [ ] Show the Nutri-Grade badge (A to D) on each drink card and in the cart, recalculated when
      the customer changes the sugar level. HPB requires the label to be shown for grades C and D.
- [ ] Hide drinks whose ingredients are expired or below a safety threshold, not just out of stock.

## 4. Kiosk experience

- [ ] Idle timeout: clear the cart and go back to the menu after a minute of no touches.
- [ ] Payment screen: poll the order status and show "Paid, your drink is being made" or
      "Payment expired", instead of a static QR code.
- [ ] Offline drink images. `Drink.image_url` points at the internet; store images with Django's
      `ImageField` and let the edge service cache them on the kiosk.
- [ ] Touch-friendly layout and full-screen kiosk mode (Chromium `--kiosk`).
- [ ] Order number screen / receipt for pickup.

## 5. Platform roadmap

- [ ] **Payments.** Add a `Payment` model and an order status flow of `PENDING → PAID → MAKING →
      COMPLETED` (or `CANCELLED`). Integrate a payment provider that issues SGQR codes and sends a
      webhook when paid (the current PayNow QR cannot tell us the customer paid), then GrabPay.
      Replace the placeholder `PAYNOW_UEN` with the real business UEN.
- [ ] **Edge service** (new `edge/` folder, Python). Runs on each kiosk: serves the kiosk UI,
      keeps a local order queue so the kiosk works through short internet outages, syncs orders
      and stock with the cloud, and talks to the hardware through an abstract interface (dispenser,
      sealer, temperature sensor) with a simulator for development.
- [ ] **Dairy safety lock.** The edge service reads the fridge temperature; above 4°C it marks dairy
      ingredients unavailable (so milk drinks disappear from the menu) and alerts staff. Log every
      reading for food-safety records.
- [ ] **Kiosk UI framework.** The plan names Next.js, but the kiosk is a single offline screen served
      locally, where Next.js's server rendering adds little. Recommendation: keep Vite for the
      kiosk and reconsider Next.js only for a public website or ops dashboard.
- [ ] **Mobile app** (React Native). Needs customer accounts (today `Order.user_id` is a free-text
      string), token auth, order-ahead with pickup at a chosen kiosk, and order status updates.
      Handle member data under PDPA.
- [ ] **Operations dashboard.** Sales by kiosk and drink, low-stock and temperature alerts,
      restocking lists. The Django admin covers this until it doesn't.
- [ ] **Deployment.** PostgreSQL for the cloud database, Docker Compose for local and server
      setup, and a hosting choice for the cloud backend.
