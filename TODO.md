# To-do

What's left, most urgent first. Target: an automated drink kiosk platform for Singapore, with a
Django cloud backend, a Python edge service on each kiosk, a kiosk touchscreen UI, a mobile ordering
app, SGQR/GrabPay payments, HPB Nutri-Grade labels and a dairy temperature safety lock.

Already working: ordering with stock holds tied to each payment, PayNow QR codes, pickup by PIN or
QR at the kiosk's "Collect my order" screen, build-your-own drinks, the Expo mobile app, the
Kiosk/Nutri-Grade models, demo data, the OpenAPI contract and CI. Run it with `./dev.sh`.

## 1. Before real customers

- [ ] **Real PayNow details.** Set `PAYNOW_PROXY_VALUE` (the business UEN) and
      `PAYNOW_MERCHANT_NAME` for production. They are environment variables and never go in git.
- [ ] **Automatic payment confirmation.** Staff mark PayNow payments paid in the admin today,
      because a plain PayNow QR can't tell us the customer paid. Add a provider in
      `checkout/providers.py` for a gateway that issues SGQR codes and sends a webhook
      (the `/checkout/webhooks/<method>/` endpoint is ready), then GrabPay and cards.
- [ ] **Dairy safety lock on the menu.** `Inventory.record_temperature` sets `Kiosk.sfa_locked`
      above 4°C, but the menu doesn't read that flag yet, and nothing sends readings (see the edge
      service). Hide dairy drinks while the kiosk is locked and alert staff.
- [ ] **Deployment.** PostgreSQL, Docker Compose, a host for the cloud backend, and production
      settings (`DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`).

## 2. Kiosk experience

- [ ] Idle timeout: clear the cart, cancel an unpaid order and go back to the menu after a minute
      of no touches.
- [ ] Show the Nutri-Grade badge (A to D) on menu drink cards and in the cart, recalculated when
      the sugar level changes. HPB requires the label for grades C and D. The backend already grades
      each order line, and the designer already shows it.
- [ ] Hide drinks whose ingredients are expired or below a safety threshold, not just out of stock.
- [ ] Offline drink images. `Drink.image_url` points at the internet; store images with Django's
      `ImageField` and let the edge service cache them.
- [ ] Touch-friendly layout, full-screen kiosk mode (Chromium `--kiosk`), and a better colour theme
      (the mobile app already uses tea green / milk cream / brown-sugar amber).

## 3. Platform

- [ ] **Edge service** (new `edge/` folder, Python). Runs on each kiosk: serves the kiosk UI, keeps
      a local order queue through short internet outages, syncs orders and stock with the cloud,
      and drives the hardware (dispenser, sealer, temperature sensor) through an abstract interface
      with a simulator for development.
- [ ] **Technician app.** Restocking, cleaning logs and maintenance tickets for staff. The models
      work proposed `CleaningLog` and `MaintenanceTicket`; not built yet.
- [ ] **Customer accounts** for the mobile app: `Order.user_id` is still free text. Add token auth,
      order history and push notifications when an order is ready. Handle member data under PDPA.
- [ ] **Operations dashboard.** Sales by kiosk and drink, low-stock and temperature alerts,
      restocking lists. The Django admin covers this for now.
- [ ] **Kiosk UI framework.** The plan names Next.js; recommendation is to keep Vite for the
      offline kiosk screen and use Next.js only for a public website or dashboard, if ever.

## 4. Code health

- [ ] Frontend tests (Vitest + Testing Library) for the cart, payment and collect screens.
- [ ] Move routes under `/api/v1/` and generate the kiosk and mobile API clients from
      `kiosk_backend/openapi.yaml`.
- [ ] The designer logic is duplicated in `frontend/kiosk-app/src/designer.js` and
      `mobile-app/lib/designer.ts`; share it or generate it.
- [ ] Delete the old `branch-backend`, `branch-frontend` and merged `claude/*` branches.
