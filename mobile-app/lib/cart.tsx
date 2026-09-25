import { createContext, ReactNode, useContext, useState } from 'react';

import type { PlacedOrder } from './api';
import { CartItem, Drink, Shop, Size } from './menu';

type CartState = {
  shop: Shop | null;
  cartItems: CartItem[];
  chooseShop: (shop: Shop) => void;
  addToCart: (drink: Drink, size: Size) => void;
  updateCartItem: (index: number, changes: Partial<CartItem>) => void;
  removeFromCart: (index: number) => void;
  clearCart: () => void;
  // the order just placed, with its pickup code
  lastOrder: PlacedOrder | null;
  setLastOrder: (order: PlacedOrder) => void;
};

const CartContext = createContext<CartState | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const [shop, setShop] = useState<Shop | null>(null);
  const [cartItems, setCartItems] = useState<CartItem[]>([]);
  const [lastOrder, setLastOrder] = useState<PlacedOrder | null>(null);

  const value: CartState = {
    shop,
    cartItems,
    chooseShop: (next) => {
      // stock is per shop, so a cart built for one shop can't carry over
      if (next.id !== shop?.id) setCartItems([]);
      setShop(next);
    },
    addToCart: (drink, size) => setCartItems((items) => [...items, { drink, size, sugar: 4, ice: 4 }]),
    updateCartItem: (index, changes) =>
      setCartItems((items) => items.map((item, i) => (i === index ? { ...item, ...changes } : item))),
    removeFromCart: (index) => setCartItems((items) => items.filter((_, i) => i !== index)),
    clearCart: () => setCartItems([]),
    lastOrder,
    setLastOrder,
  };

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart() {
  const cart = useContext(CartContext);
  if (!cart) throw new Error('useCart must be used inside CartProvider');
  return cart;
}
