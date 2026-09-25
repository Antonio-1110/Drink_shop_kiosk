// STUB: stands in for GET /ordering/designer/options/ until the backend serves it.
// The ingredients are the ones in the backend's Ingredient table (seed_demo). Ice is set by the
// ice level and Brown sugar syrup by the sugar level, so neither is picked on its own.
// Prices are placeholders: the shop sets them in `pricing`. Nutrition values (g per 100 mL or g)
// are typical figures for the shop to confirm.
// The mobile app has the same stub in mobile-app/lib/designerStub.ts; change both together.

export const DESIGNER_OPTIONS_STUB = {
    stub: true,
    // liquid_ml: the drink without ice or toppings (what Nutri-Grade is measured on);
    // topping_g: toppings per cup, shared between the toppings picked
    sizes: [
        { value: 0, label: 'Small', liquid_ml: 360, topping_g: 60 },
        { value: 1, label: 'Large', liquid_ml: 500, topping_g: 80 },
    ],
    // price = cup price for the size + each ingredient's price (its override, or the default for its kind)
    pricing: {
        cup: { 0: '2.80', 1: '3.40' },
        liquid: '0.50',
        topping: '0.60',
        overrides: { ES: '0.80' },
    },
    // the sugar level adds this much syrup at 100%, less at lower levels
    sweetener: { code: 'BS', name: 'Brown sugar syrup', color: '#a0612b', sugar: 65, sat_fat: 0, ml: { 0: 30, 1: 40 } },
    // code: the short label printed on the drink code customers bring to the kiosk.
    // share: how much of the cup a liquid takes next to the others (tea 3 : milk 2 : fruit 1)
    ingredients: [
        { code: 'BT', name: 'Black tea', kind: 'liquid', category: 'Tea', share: 3, color: '#8a4b24', sugar: 0, sat_fat: 0 },
        { code: 'GT', name: 'Green tea', kind: 'liquid', category: 'Tea', share: 3, color: '#b5c46a', sugar: 0, sat_fat: 0 },
        { code: 'OT', name: 'Oolong tea', kind: 'liquid', category: 'Tea', share: 3, color: '#c08a3e', sugar: 0, sat_fat: 0 },
        { code: 'ES', name: 'Espresso', kind: 'liquid', category: 'Coffee', share: 1, color: '#3b2417', sugar: 0, sat_fat: 0 },
        { code: 'FM', name: 'Fresh milk', kind: 'liquid', category: 'Milk', share: 2, color: '#f4efe6', sugar: 4.8, sat_fat: 2.3 },
        { code: 'OM', name: 'Oat milk', kind: 'liquid', category: 'Milk', share: 2, color: '#e8d9bd', sugar: 4.0, sat_fat: 0.3 },
        { code: 'PF', name: 'Passion fruit', kind: 'liquid', category: 'Fruit', share: 1, color: '#f2b705', sugar: 11, sat_fat: 0 },
        { code: 'LM', name: 'Lemon', kind: 'liquid', category: 'Fruit', share: 1, color: '#f7e463', sugar: 2.5, sat_fat: 0 },
        { code: 'MG', name: 'Mango puree', kind: 'liquid', category: 'Fruit', share: 1, color: '#ffa630', sugar: 14, sat_fat: 0.1 },
        // HPB grades toppings separately, so they don't count towards the drink's grade
        { code: 'TP', name: 'Tapioca pearls', kind: 'topping', category: 'Toppings', share: 1, color: '#2e1a12', exclude_from_grade: true },
    ],
};
