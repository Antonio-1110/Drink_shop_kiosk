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
export type PlacedOrder = { id: number; revenue: string; pickup_pin?: string; pickup_qr?: string };

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

export function fetchPaynowQr(orderId: string | number) {
  return request<PaynowQr>(`/ordering/orders/${orderId}/paynow-qr/`);
}

// what the drink designer offers at this shop: ingredients, their amounts and prices
export function fetchDesignerOptions(shopId: number) {
  return request<DesignerOptions>(`/ordering/designer/options/?shop_id=${shopId}`);
}
