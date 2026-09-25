// Calls the Django backend, the same endpoints the kiosk UI uses.
import Constants from 'expo-constants';
import { Platform } from 'react-native';

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
  constructor(message: string, data: any) {
    super(message);
    this.data = data;
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
  if (!res.ok) throw new ApiError(data.error ?? 'Request failed', data);
  return data;
}

export function fetchShops() {
  return request<Shop[]>('/ordering/shops/');
}

// drinks the shop can still make after the ones already in the cart
export function fetchAvailableDrinks(shopId: number, cartItems: CartItem[]) {
  const params = new URLSearchParams({ shop_id: String(shopId) });
  cartItems.forEach((item) => params.append('cart', String(item.drink.id)));
  return request<Drink[]>(`/ordering/drinks/?${params}`);
}

export function placeOrder(shopId: number, cartItems: CartItem[]) {
  return request<{ id: number; revenue: string }>('/ordering/log-order/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      shop: shopId,
      items: cartItems.map(({ drink, size, sugar, ice }) => ({ drink: drink.id, size, sugar, ice })),
    }),
  });
}

export type PaynowQr = { qr_code: string; reference: string; amount: string };

export function fetchPaynowQr(orderId: string | number) {
  return request<PaynowQr>(`/ordering/orders/${orderId}/paynow-qr/`);
}
