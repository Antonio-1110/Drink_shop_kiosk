// Calls the Django backend, the same endpoints the kiosk UI uses.
import Constants from 'expo-constants';
import { Platform } from 'react-native';

import type { DesignerOptions } from './designer';
import type { CartItem, Drink, Shop } from './menu';

function defaultApiBase() {
  // in the browser, metro.config.js proxies /api to the backend like Vite does for the kiosk
  if (Platform.OS === 'web') return '/api';
  // on a phone, assume the backend runs on the same computer as the Expo dev server
  const host = Constants.expoConfig?.hostUri?.split(':')[0];
  return `http://${host ?? 'localhost'}:8000`;
}

const API_BASE = process.env.EXPO_PUBLIC_API_BASE ?? defaultApiBase();

export class ApiError extends Error {
  data: any;
  status?: number;
  constructor(message: string, data: any, status?: number) {
    super(message);
    this.data = data;
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, options);
  } catch {
    throw new ApiError(`Can't reach the shop server at ${API_BASE}`, {});
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(data.error ?? 'Request failed', data, res.status);
  return data;
}

export function fetchShops() {
  return request<Shop[]>('/ordering/shops/');
}

// drinks the shop can still make after the ones already in the cart
export function fetchAvailableDrinks(shopId: number, cartItems: CartItem[]) {
  const params = new URLSearchParams({ shop_id: String(shopId) });
  // only menu drinks count here; designed drinks are checked when the order is placed
  cartItems.forEach((item) => { if (!item.custom) params.append('cart', String(item.drink.id)); });
  return request<Drink[]>(`/ordering/drinks/?${params}`);
}

// pickup_pin / pickup_qr only come back in this response, so the app keeps them (see lib/cart.tsx)
// order_token is needed to cancel the order
export type PlacedOrder = {
  id: number;
  revenue: string;
  order_token?: string;
  pickup_pin?: string;
  pickup_qr?: string;
};

export function placeOrder(shopId: number, cartItems: CartItem[]) {
  return request<PlacedOrder>('/ordering/log-order/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      shop: shopId,
      items: cartItems.map(({ drink, custom, size, sugar, ice }) => (custom
        ? { custom: custom.picks, size, sugar, ice }
        : { drink: drink.id, size, sugar, ice })),
    }),
  });
}

// expires_at: unpaid orders are cancelled after this time
export type PaynowQr = { qr_code: string; reference: string; amount: string; expires_at?: string };

// starts the PayNow payment (or returns the open one); ingredients are held until expires_at
export function fetchPaynowQr(orderId: string | number) {
  return request<PaynowQr>(`/ordering/orders/${orderId}/paynow-qr/`);
}

// what the drink designer offers at this shop: ingredients, their amounts and prices
export function fetchDesignerOptions(shopId: number) {
  return request<DesignerOptions>(`/ordering/designer/options/?shop_id=${shopId}`);
}

export type OrderStatus = { status: string; hold_expires_at?: string | null };

// a collected order was paid for too
// every status after payment, including the machine's steps (being made, ready, couldn't be made)
const PAID_STATUSES = ['PAID', 'PREPARING', 'READY', 'FAILED', 'REFUND_NEEDED', 'COLLECTED'];
export const isPaid = (status?: string) => PAID_STATUSES.includes(status ?? '');

// what the machine is doing with a paid order, for the order screen; other statuses show nothing
export const DRINK_PROGRESS: Record<string, { text: string; tone: 'ok' | 'warn' }> = {
  PREPARING: { text: 'Your drink is being made.', tone: 'ok' },
  READY: { text: 'Ready to collect at the machine.', tone: 'ok' },
  FAILED: { text: "Sorry, the machine couldn't make your drink. Staff have been told.", tone: 'warn' },
  REFUND_NEEDED: { text: "Sorry, your drink couldn't be made. Your payment is being refunded.", tone: 'warn' },
};

export function fetchOrderStatus(orderId: string | number) {
  return request<OrderStatus>(`/ordering/orders/${orderId}/status/`);
}

export function cancelOrder(orderId: string | number, orderToken: string) {
  return request<{ status: string }>(`/ordering/orders/${orderId}/cancel/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ order_token: orderToken }),
  });
}
