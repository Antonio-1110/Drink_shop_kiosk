# Drink Shop mobile app

Customer pre-ordering app built with Expo (React Native). It follows the kiosk UI in
`frontend/kiosk-app`: same menu categories, S/L sizes, sugar and ice levels and
PayNow checkout, and it calls the same Django endpoints.

Flow: pick the shop you'll collect from → browse the menu → add drinks → set sugar/ice in
the cart → place the order → pay with the PayNow QR → collect at the machine by scanning a
pickup QR or keying in a PIN.

The pickup QR and PIN come from the `pickup_qr` and `pickup_pin` fields of the
`POST /ordering/log-order/` response (the only place the backend returns them). The order
screen polls `GET /ordering/orders/{id}/status/` to show when the order is paid, collected or
cancelled, and cancels with the `order_token` from the same response. These need the backend
from PR #3.

## Run it

Start the backend first (`./dev.sh --backend` from the repo root), then:

```
cd mobile-app
npm install
npm run web        # opens in the browser; /api is proxied to the backend on :8000
npm start          # QR code for Expo Go on a phone, or press a / i for an emulator
```

In the browser, `metro.config.js` proxies `/api` to `localhost:8000`, the same way the
kiosk's Vite config does.

On a phone, start the backend with `./dev.sh --lan` (coming in PR #3) so phones on your Wi-Fi can reach it.
The app then calls the backend on the same computer as the Expo dev server
(`http://<that computer's IP>:8000`). To point somewhere else, set `EXPO_PUBLIC_API_BASE`,
e.g. `EXPO_PUBLIC_API_BASE=https://api.example.com npm start`.

## Checks

```
npm run lint
npm run typecheck
```

## Layout

- `app/` screens (Expo Router): `(tabs)/index.tsx` menu, `(tabs)/cart.tsx` cart,
  `shops.tsx` shop picker, `payment/[orderId].tsx` PayNow
- `components/` drink card, sugar/ice picker, shop list
- `lib/` API calls, cart state, menu constants shared with the kiosk
- `constants/theme.ts` colour theme (tea green, milk cream, brown-sugar amber)
