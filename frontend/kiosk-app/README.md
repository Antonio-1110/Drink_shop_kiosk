# Kiosk app

The touchscreen ordering UI customers use at the kiosk. React 19 + Vite, talking to the Django
backend in `kiosk_backend/`.

## Run it

The easiest way is `./dev.sh` from the repo root, which starts the backend too. To run only this app:

```
npm ci
npm run dev        # http://localhost:5173
```

It expects the backend on http://localhost:8000. In development Vite forwards every `/api/...`
request there (see `vite.config.js`), so the browser only ever talks to one origin.

| Script | What it does |
| --- | --- |
| `npm run dev` | Dev server with hot reload |
| `npm run build` | Production build into `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run lint` | ESLint |

## Settings

Set these in the environment or in a `.env.local` file next to this README.

| Variable | Default | What it does |
| --- | --- | --- |
| `VITE_SHOP_ID` | `1` | Which shop's menu and stock this kiosk uses |
| `VITE_API_BASE` | `/api` | Where the backend is. Set a full URL when the backend isn't behind the Vite proxy |

## How an order flows

1. **Menu** (`/`, `/milktea`, `/fruittea`, ...): shows the drinks the shop can still make. The list
   is fetched again every time the cart changes, so a drink disappears as soon as the cart would use
   up its last ingredients.
2. **Cart** (`/cart`): pick size, sugar and ice for each cup, then **Checkout** places the order.
   If another customer took the last stock in the meantime, the backend answers 409 and the cart
   names the drinks that are now sold out.
3. **Payment** (`/payment/:orderId`): shows the PayNow QR code, the amount, the reference and a
   countdown. The ingredients are held until the countdown ends. The page asks the backend every
   few seconds whether the order is paid, and switches to "Payment received" or "Order cancelled".
   **Cancel order** releases the ingredients at once (it sends the `order_token` from step 2).
   Placing the order also returns a 6-digit pickup PIN and a pickup QR token.
4. **Collect** (`/collect`, "Collect my order" in the sidebar): the screen at the machine. The
   customer types their PIN on the keypad, or scans their pickup QR. QR scanners that act as a
   keyboard work out of the box: the page keeps a hidden input focused and submits on Enter. The
   screen then shows "Order collected", or says the order isn't paid yet, was already collected,
   or the code isn't recognised, and goes back to the keypad after 8 seconds.

## Code map

| Path | What's there |
| --- | --- |
| `src/App.jsx` | Routes, cart state, and the menu reload when the cart changes |
| `src/api.js` | Every call to the backend |
| `src/menu.js` | Sizes, sugar/ice levels and categories. These mirror the backend's choices, so change both together |
| `src/pages/` | Menu, cart, payment and collect screens |
| `src/components/` | Sidebar navigation, drink cards |

## Backend API

The endpoints this app uses are described in the backend's API contract,
[`kiosk_backend/openapi.yaml`](../../kiosk_backend/openapi.yaml). With the backend running you can
also browse it at http://localhost:8000/api/docs/.

| Call | Used for |
| --- | --- |
| `GET /ordering/drinks/?shop_id=&cart=` | Menu of drinks that can still be made |
| `POST /ordering/log-order/` | Placing the order |
| `GET /ordering/orders/{id}/paynow-qr/` | Starting the PayNow payment and getting its QR code |
| `GET /ordering/orders/{id}/status/` | Checking whether the order is paid |
| `POST /ordering/orders/{id}/cancel/` | The Cancel button |
| `POST /ordering/pickup/` | Collecting a paid order with its PIN or QR token |
