import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, ReactNode, useContext, useEffect, useState } from 'react';

import type { PlacedOrder } from './api';
import { CartItem, CustomCartItem, Drink, sameDrink, Shop, Size } from './menu';

// An order placed from this phone. The pickup PIN and QR only come back once, when the order is
// placed, so they are kept on the phone: closing the app must not lose them.
export type SavedOrder = PlacedOrder & {
  shopName?: string;
  placedAt: number;
  count: number;
  // set once the order screen saw it collected or cancelled, so it stops showing on the menu
  finished?: boolean;
};

type CartState = {
  // false until what was saved on the phone has been read back
  ready: boolean;
  shop: Shop | null;
  cartItems: CartItem[];
  chooseShop: (shop: Shop) => void;
  addToCart: (drink: Drink, choice: { size: Size; sugar: number; ice: number }) => void;
  addCustomToCart: (item: CustomCartItem) => void;
  updateCartItem: (index: number, changes: Partial<Pick<CartItem, 'size' | 'sugar' | 'ice' | 'qty'>>) => void;
  removeFromCart: (index: number) => void;
  clearCart: () => void;
  // newest first
  orders: SavedOrder[];
  saveOrder: (order: PlacedOrder, count: number) => void;
  finishOrder: (id: number) => void;
};

const STORAGE_KEY = 'drink-shop/cart-v1';
// how many orders, and for how long, the phone keeps
const KEEP_ORDERS = 10;
const KEEP_MS = 3 * 24 * 60 * 60 * 1000;

const CartContext = createContext<CartState | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [shop, setShop] = useState<Shop | null>(null);
  const [cartItems, setCartItems] = useState<CartItem[]>([]);
  const [orders, setOrders] = useState<SavedOrder[]>([]);

  // read back the shop, the unfinished cart and recent orders
  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((raw) => {
        if (!raw) return;
        const saved = JSON.parse(raw);
        if (saved.shop) setShop(saved.shop);
        if (Array.isArray(saved.cartItems)) setCartItems(saved.cartItems);
        if (Array.isArray(saved.orders)) {
          setOrders(saved.orders.filter((o: SavedOrder) => Date.now() - o.placedAt < KEEP_MS));
        }
      })
      .catch(() => {}) // nothing saved, or storage unavailable: start fresh
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    if (!ready) return;
    AsyncStorage.setItem(STORAGE_KEY, JSON.stringify({ shop, cartItems, orders })).catch(() => {});
  }, [ready, shop, cartItems, orders]);

  const addLine = (line: CartItem) => setCartItems((items) => {
    const index = items.findIndex((item) => sameDrink(item, line));
    if (index === -1) return [...items, { ...line, qty: 1 }];
    return items.map((item, i) => (i === index ? { ...item, qty: (item.qty ?? 1) + 1 } : item));
  });

  const value: CartState = {
    ready,
    shop,
    cartItems,
    chooseShop: (next) => {
      // stock is per shop, so a cart built for one shop can't carry over
      if (next.id !== shop?.id) setCartItems([]);
      setShop(next);
    },
    addToCart: (drink, { size, sugar, ice }) => addLine({ drink, size, sugar, ice }),
    addCustomToCart: (item) => addLine(item),
    updateCartItem: (index, changes) =>
      setCartItems((items) => items.map((item, i) => (i === index ? { ...item, ...changes } as CartItem : item))),
    removeFromCart: (index) => setCartItems((items) => items.filter((_, i) => i !== index)),
    clearCart: () => setCartItems([]),
    orders,
    saveOrder: (order, count) => setOrders((list) => [
      { ...order, shopName: shop?.name, placedAt: Date.now(), count },
      ...list.filter((o) => o.id !== order.id),
    ].slice(0, KEEP_ORDERS)),
    finishOrder: (id) => setOrders((list) => (list.some((o) => o.id === id && !o.finished)
      ? list.map((o) => (o.id === id ? { ...o, finished: true } : o))
      : list)),
  };

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart() {
  const cart = useContext(CartContext);
  if (!cart) throw new Error('useCart must be used inside CartProvider');
  return cart;
}
