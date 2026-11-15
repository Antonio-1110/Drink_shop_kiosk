// matches the Size and Level choices on the backend OrderItem model
export const SIZE = { SMALL: 0, LARGE: 1 };
export const LEVELS = [
    { value: 4, label: '100%' },
    { value: 3, label: '75%' },
    { value: 2, label: '50%' },
    { value: 1, label: '25%' },
    { value: 0, label: '0%' },
];

// matches Drink.Category on the backend, which the API returns as its label
export const CATEGORIES = [
    { path: 'milktea', label: 'Milk Tea', subtitle: 'Freshly brewed tea with milk.' },
    { path: 'fruittea', label: 'Fruit Tea', subtitle: 'Light, bright teas with fruit.' },
    { path: 'smoothie', label: 'Smoothie', subtitle: 'Blended with fruit and ice.' },
    { path: 'coffee', label: 'Coffee', subtitle: 'Espresso-based drinks.' },
    { path: 'others', label: 'Others', subtitle: 'Plain teas and more.' },
];

// the most drinks one order may have; matches the backend's ORDER_MAX_ITEMS (default 20)
export const MAX_ORDER_DRINKS = 20;

export const itemPrice = (item) => item.custom ? item.custom.price :
    Number(item.size === SIZE.LARGE ? item.drink.l_price : item.drink.s_price);

// the name in the corner of the kiosk until the shop has a logo
export const BRAND_NAME = import.meta.env.VITE_BRAND_NAME ?? 'Tea House';

// A cart line is one drink with its options and a quantity (`qty`, 1 when missing).
export const lineQty = (item) => item.qty ?? 1;
export const lineTotal = (item) => itemPrice(item) * lineQty(item);
export const cartCount = (items) => items.reduce((sum, item) => sum + lineQty(item), 0);
export const cartTotal = (items) => items.reduce((sum, item) => sum + lineTotal(item), 0);

// two lines that would make the same cup, so adding one again just raises the quantity
export function sameDrink(a, b) {
    if (a.size !== b.size || a.sugar !== b.sugar || a.ice !== b.ice) return false;
    if (a.custom || b.custom) return Boolean(a.custom && b.custom) && a.custom.picks.join('-') === b.custom.picks.join('-');
    return a.drink.id === b.drink.id;
}

// one entry per cup, the way the backend takes them
export const expandCart = (items) => items.flatMap((item) => Array.from({ length: lineQty(item) }, () => item));
