// Same values as frontend/kiosk-app/src/menu.js, which match the backend models.

// OrderItem.Size
export const SIZE = { SMALL: 0, LARGE: 1 } as const;
export type Size = (typeof SIZE)[keyof typeof SIZE];

// OrderItem sugar / ice levels
export const LEVELS = [
  { value: 4, label: '100%' },
  { value: 3, label: '75%' },
  { value: 2, label: '50%' },
  { value: 1, label: '25%' },
  { value: 0, label: '0%' },
];

// Drink.Category, which the API returns as its label
export const CATEGORIES = ['Milk Tea', 'Fruit Tea', 'Smoothie', 'Coffee', 'Others'];

export type Drink = {
  id: number;
  name: string;
  category: string;
  image_url: string;
  s_price: string;
  l_price: string;
  description: string;
};

export type Shop = {
  id: number;
  name: string;
  address: string;
  shop_type: string;
};

export type MenuCartItem = { drink: Drink; custom?: undefined; size: Size; sugar: number; ice: number };
// a drink built in the designer (see lib/designer.ts)
export type CustomDrink = { picks: string[]; price: number };
export type CustomCartItem = { drink: { id: null; name: string }; custom: CustomDrink; size: Size; sugar: number; ice: number };
export type CartItem = MenuCartItem | CustomCartItem;

export const itemPrice = (item: CartItem) => item.custom ? item.custom.price :
  Number(item.size === SIZE.LARGE ? item.drink.l_price : item.drink.s_price);

export const formatPrice = (value: number | string) => `$${Number(value).toFixed(2)}`;
