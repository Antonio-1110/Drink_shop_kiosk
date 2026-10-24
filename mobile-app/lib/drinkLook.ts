// Until the shop has photos, each drink gets a drawn cup tinted from its name and category.
// Same rules as kiosk-app/src/drinkLook.js; change both together.
export type DrinkLook = {
  liquid: string;
  top: string;
  backdrop: string;
  base?: string;
  seeds?: boolean;
  slice?: boolean;
  pearls?: boolean;
};

const KEYWORD_LOOKS: [RegExp, DrinkLook][] = [
  [/mango/i, { liquid: '#f2b23e', top: '#f7cf73', backdrop: '#fbefd6' }],
  [/passion/i, { liquid: '#e9a23b', top: '#f3c46b', backdrop: '#fbeed8', seeds: true }],
  [/lemon/i, { liquid: '#c98b3c', top: '#ead27a', backdrop: '#f8f0d6', slice: true }],
  [/brown sugar/i, { liquid: '#efe2cf', top: '#f6eee2', base: '#7a4321', backdrop: '#f3e6d6' }],
  [/matcha/i, { liquid: '#93ac5f', top: '#dfe6c8', backdrop: '#eaf0dc' }],
  [/latte|coffee|espresso/i, { liquid: '#a8774f', top: '#e9d8c4', backdrop: '#f1e5d8' }],
  [/oat|milk tea/i, { liquid: '#c99c6f', top: '#ecdcc7', backdrop: '#f4e9dc' }],
  [/oolong/i, { liquid: '#b97a3c', top: '#d6a368', backdrop: '#f4e7d6' }],
  [/green tea|jasmine/i, { liquid: '#c8b45a', top: '#e2d58e', backdrop: '#f2eed6' }],
];

const CATEGORY_LOOKS: Record<string, DrinkLook> = {
  'Milk Tea': { liquid: '#c99c6f', top: '#ecdcc7', backdrop: '#f4e9dc' },
  'Fruit Tea': { liquid: '#e39a54', top: '#f1c58c', backdrop: '#fbecdc' },
  Smoothie: { liquid: '#e7a0a0', top: '#f3cccc', backdrop: '#fbe8e6' },
  Coffee: { liquid: '#a8774f', top: '#e9d8c4', backdrop: '#f1e5d8' },
};
const DEFAULT_LOOK: DrinkLook = { liquid: '#b98a52', top: '#d9b98c', backdrop: '#f3ebe0' };

export function drinkLook(drink: { name: string; category?: string }): DrinkLook {
  const match = KEYWORD_LOOKS.find(([pattern]) => pattern.test(drink.name));
  const look = match ? match[1] : CATEGORY_LOOKS[drink.category ?? ''] ?? DEFAULT_LOOK;
  return { ...look, pearls: /pearl|boba/i.test(drink.name) };
}
