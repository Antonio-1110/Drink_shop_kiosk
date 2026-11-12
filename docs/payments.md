# Payments: testing without money, and going live

Every payment method goes through the same steps (`kiosk_backend/checkout/services.py`): placing an
order holds its ingredients, starting a payment keeps them held until that payment expires, and
every method reports success through one function, `confirm_payment`. That function ignores
repeats, takes late payments if the ingredients are still there, and refunds them if not. So
sandbox and real payments behave the same way; only the money is pretend.

| Method | What the customer sees | Who confirms it's paid | Needs |
|---|---|---|---|
| `sandbox` | A test QR code that opens a fake bank page | The fake bank's buttons | Nothing. On in development only |
| `paynow` | The company's PayNow QR (SGQR) | Staff, with **Mark as paid** in `/admin` | `PAYNOW_PROXY_VALUE` (UEN) |
| `stripe_paynow` | Stripe's PayNow QR | Stripe, automatically | A Stripe account |
| `stripe_grabpay` | A QR code that opens GrabPay on their phone | Stripe, automatically | A Stripe account with GrabPay on |

The kiosk's and phone app's "Scan to pay" screen uses `PAYNOW_METHOD`; other methods are started
with `POST /ordering/orders/<id>/payments/ {"method": "..."}`. The reply says `test_mode: true`
whenever no real money moves.

## 1. Sandbox: no account, no money

On by default with `./dev.sh` (`PAYMENTS_SANDBOX=1`, `PAYNOW_METHOD=sandbox`).

1. Run `./dev.sh` and place an order on the kiosk at http://localhost:5173.
2. The payment screen shows a test QR code. Either scan it with your phone (start with
   `./dev.sh --lan` so your phone can reach the computer), or open http://localhost:8000/checkout/sandbox/
   on the computer and click the order.
3. The fake bank page has three buttons:
   - **Pay**: the order becomes Paid and the kiosk moves on. Pressing it twice counts once.
   - **Pay the wrong amount**: recorded as a separate transfer, refunded straight away; the order still waits.
   - **Decline**: the payment fails; the order waits a couple of minutes for another try.
4. To try a late payment, let the countdown run out (or press Cancel on the kiosk), then press Pay.
   The order goes through if the ingredients are still there, and is refunded if someone else bought them.

The admin's **Payment attempts** list shows each payment's status, including refunds.

The sandbox must never be on for a shop taking real orders: anyone with the link could "pay".
`manage.py check --deploy` warns if it is.

## 2. Stripe test mode: the real gateway, still no money

Stripe takes PayNow and GrabPay for Singapore businesses and has a test mode that needs only an
email sign-up. The company's details (UEN, bank account) are only needed later, to take real payments.

**What to sign up for:** a Stripe account at https://dashboard.stripe.com/register with country
Singapore. Then in the dashboard, with **Test mode** on:

1. **Settings → Payment methods**: turn on PayNow and GrabPay.
2. **Developers → API keys**: copy the secret key (`sk_test_...`).
3. Webhook secret, either:
   - on your computer, with the Stripe CLI: `stripe listen --forward-to localhost:8000/checkout/webhooks/stripe/`,
     which prints a `whsec_...` secret; or
   - on a server: **Developers → Webhooks → Add endpoint**, URL `https://<your server>/checkout/webhooks/stripe/`,
     events `payment_intent.succeeded` and `payment_intent.payment_failed`, then copy its signing secret.

Then run the backend with these in the environment (never commit them):

```sh
export PAYMENT_METHODS=stripe_paynow,stripe_grabpay,sandbox
export PAYNOW_METHOD=stripe_paynow
export STRIPE_SECRET_KEY=sk_test_...
export STRIPE_WEBHOOK_SECRET=whsec_...
./dev.sh
```

Place an order. The kiosk shows Stripe's PayNow QR code. In test mode the payment reply also has a
`test_pay_url`: open it and Stripe's test page lets you pretend the customer paid (or failed). Stripe
then notifies the backend, and the kiosk shows "Payment received". GrabPay works the same way with
`{"method": "stripe_grabpay"}`; its test page has Authorize and Fail buttons.

Refunds (wrong amount, late payment with no stock, a drink the machine couldn't make) are sent to
Stripe automatically. If Stripe refuses one, it shows in the admin as "Paid, needs refund".

## 3. Going live later

Swap in the live key (`sk_live_...`) and live webhook secret, and set `STRIPE_LIVE=1`. Without
`STRIPE_LIVE=1` a live key is refused, so real money only moves on purpose. Unset `PAYMENTS_SANDBOX`.

## Adding another method

Write a `Provider` subclass (`kiosk_backend/checkout/providers.py`): `start` returns what the screen
shows, `parse_webhook` turns the gateway's verified notification into (event, order, reference,
amount), and optionally `check_status`, `cancel` and `refund`. Add it to `PROVIDERS` and
`PAYMENT_METHODS`. `checkout/stripe_gateway.py` is a complete example. HitPay, a Singapore gateway
with PayNow and GrabPay and its own sandbox, would fit the same way if its fees suit better.
