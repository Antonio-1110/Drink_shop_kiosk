import { DESIGNER_OPTIONS_STUB } from './designerStub';

// Calls the Django backend. In dev, Vite proxies /api to the backend (see vite.config.js).
const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';
export const SHOP_ID = import.meta.env.VITE_SHOP_ID ?? '1';

async function request(path, options) {
    const res = await fetch(`${API_BASE}${path}`, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        const error = new Error(data.error ?? 'Request failed');
        error.data = data;
        error.status = res.status;
        throw error;
    }
    return data;
}

// drinks the shop can still make after the ones already in the cart
export function fetchAvailableDrinks(cartItems) {
    const params = new URLSearchParams({ shop_id: SHOP_ID });
    // custom drinks aren't menu drinks, so the backend can't count them yet
    cartItems.filter((item) => !item.custom).forEach((item) => params.append('cart', item.drink.id));
    return request(`/ordering/drinks/?${params}`);
}

export function placeOrder(cartItems) {
    return request('/ordering/log-order/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            shop: Number(SHOP_ID),
            items: cartItems.map(({ drink, custom, size, sugar, ice }) => (custom
                ? { custom: custom.picks, size, sugar, ice }
                : { drink: drink.id, size, sugar, ice })),
        }),
    });
}

export function fetchPaynowQr(orderId) {
    return request(`/ordering/orders/${orderId}/paynow-qr/`);
}

// What the drink designer offers at this shop. Until the backend has the endpoint
// (a 404), the designer runs on the placeholder options in designerStub.js.
export async function fetchDesignerOptions() {
    try {
        return await request(`/ordering/designer/options/?shop_id=${SHOP_ID}`);
    } catch (err) {
        if (err.status === 404) return DESIGNER_OPTIONS_STUB;
        throw err;
    }
}
