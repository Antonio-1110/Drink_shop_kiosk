import { expandCart } from './menu';

// Calls the Django backend. In dev, Vite proxies /api to the backend (see vite.config.js).
const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';
export const SHOP_ID = import.meta.env.VITE_SHOP_ID ?? '1';

async function request(path, options) {
    let res;
    try {
        res = await fetch(`${API_BASE}${path}`, options);
    } catch {
        // no network, or the backend is down: no answer at all
        const error = new Error('offline');
        error.offline = true;
        error.data = {};
        throw error;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        const error = new Error(data.error ?? data.detail ?? 'Request failed');
        error.data = data;
        error.status = res.status;
        throw error;
    }
    return data;
}

// drinks the shop can still make after the ones already in the cart
export function fetchAvailableDrinks(cartItems) {
    const params = new URLSearchParams({ shop_id: SHOP_ID });
    // only menu drinks count here; designed drinks are checked when the order is placed
    expandCart(cartItems).filter((item) => !item.custom).forEach((item) => params.append('cart', item.drink.id));
    return request(`/ordering/drinks/?${params}`);
}

export function placeOrder(cartItems) {
    return request('/ordering/log-order/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            shop: Number(SHOP_ID),
            items: expandCart(cartItems).map(({ drink, custom, size, sugar, ice }) => (custom
                ? { custom: custom.picks, size, sugar, ice }
                : { drink: drink.id, size, sugar, ice })),
        }),
    });
}

// starts (or reuses) the PayNow payment; the ingredients stay held until it expires
// the order's token proves this kiosk placed it; the backend refuses a wrong one
const withToken = (orderToken) => (orderToken ? { headers: { 'X-Order-Token': orderToken } } : undefined);

export function fetchPaynowQr(orderId, orderToken) {
    return request(`/ordering/orders/${orderId}/paynow-qr/`, withToken(orderToken));
}

export function fetchOrderStatus(orderId, orderToken) {
    return request(`/ordering/orders/${orderId}/status/`, withToken(orderToken));
}

// reason 'idle_timeout' tells the backend the kiosk cancelled it, not the customer
export function cancelOrder(orderId, orderToken, reason) {
    return request(`/ordering/orders/${orderId}/cancel/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reason ? { order_token: orderToken, reason } : { order_token: orderToken }),
    });
}

// what the drink designer offers at this shop: ingredients, their amounts and prices
export function fetchDesignerOptions() {
    return request(`/ordering/designer/options/?shop_id=${SHOP_ID}`);
}

// code is the 6-digit pickup PIN the customer typed, or the token their pickup QR code holds
export function collectOrder(code) {
    return request('/ordering/pickup/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ shop: Number(SHOP_ID), code }),
    });
}
