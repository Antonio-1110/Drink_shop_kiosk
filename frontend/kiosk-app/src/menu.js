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
    { path: 'milktea', label: 'Milk Tea' },
    { path: 'fruittea', label: 'Fruit Tea' },
    { path: 'smoothie', label: 'Smoothie' },
    { path: 'coffee', label: 'Coffee' },
    { path: 'others', label: 'Others' },
];

export const itemPrice = (item) => item.custom ? item.custom.price :
    Number(item.size === SIZE.LARGE ? item.drink.l_price : item.drink.s_price);
