// Building your own drink: how much of each ingredient goes in, its price, its Nutri-Grade,
// and the drink code customers bring to the kiosk.
// frontend/kiosk-app/src/designer.js is the same logic for the kiosk; change both together.
import type { CustomCartItem, Size } from './menu';
import { nutriGrade } from './nutrigrade';

// The shape of GET /ordering/designer/options/ (see lib/designerStub.ts until it exists).
// Nutrition values are g per 100 mL or g.
export type Ingredient = {
  code: string;
  name: string;
  kind: 'liquid' | 'topping';
  category: string;
  share?: number;
  color: string;
  available?: boolean;
  sugar?: number;
  sat_fat?: number;
  sweetener?: boolean;
  exclude_from_grade?: boolean;
};

export type DesignerOptions = {
  stub?: boolean;
  sizes: { value: Size; label: string; liquid_ml: number; topping_g: number }[];
  pricing: { cup: Record<number, string>; liquid: string; topping: string; overrides?: Record<string, string> };
  sweetener: { code: string; name: string; color: string; sugar: number; sat_fat: number; ml: Record<number, number> };
  ingredients: Ingredient[];
};

export type Design = { size: Size; sugar: number; ice: number; picks: string[] };

export type RecipeLine = Omit<Ingredient, 'kind' | 'category'> & { kind: 'liquid' | 'topping'; amount: number; unit: 'mL' | 'g' };

export const findIngredient = (options: DesignerOptions, code: string) => options.ingredients.find((i) => i.code === code);
const ingredient = (options: DesignerOptions, code: string) => findIngredient(options, code)!;

// categories in the order the options list them
export const categories = (options: DesignerOptions) => [...new Set(options.ingredients.map((i) => i.category))];

export function newDesign(options: DesignerOptions): Design {
  // start from the first liquid in stock so the cup is never empty
  const first = options.ingredients.find((i) => i.kind === 'liquid' && i.available !== false);
  return { size: options.sizes[0].value, sugar: 4, ice: 4, picks: first ? [first.code] : [] };
}

export function togglePick(options: DesignerOptions, design: Design, code: string): Design {
  if (design.picks.includes(code)) return { ...design, picks: design.picks.filter((c) => c !== code) };
  if (ingredient(options, code).available === false) return design;
  return { ...design, picks: [...design.picks, code] };
}

const picked = (options: DesignerOptions, design: Design, kind: Ingredient['kind']) =>
  design.picks.map((code) => ingredient(options, code)).filter((i) => i.kind === kind);

// Each picked ingredient's amount. Liquids share the cup by their `share`; the sugar level's syrup
// comes out of the same volume. Toppings split the size's topping allowance evenly.
export function recipe(options: DesignerOptions, design: Design): RecipeLine[] {
  const size = options.sizes.find((s) => s.value === design.size)!;
  const lines: RecipeLine[] = [];
  const syrupMl = (options.sweetener.ml[design.size] * design.sugar) / 4;
  const liquids = picked(options, design, 'liquid');
  const shares = liquids.reduce((sum, i) => sum + (i.share ?? 1), 0) || 1;
  for (const i of liquids) {
    lines.push({ ...i, amount: ((size.liquid_ml - syrupMl) * (i.share ?? 1)) / shares, unit: 'mL' });
  }
  if (syrupMl > 0) lines.push({ ...options.sweetener, kind: 'liquid', amount: syrupMl, unit: 'mL' });
  const toppings = picked(options, design, 'topping');
  for (const i of toppings) lines.push({ ...i, amount: size.topping_g / toppings.length, unit: 'g' });
  return lines;
}

export function ingredientPrice(options: DesignerOptions, i: Ingredient) {
  return Number(options.pricing.overrides?.[i.code] ?? options.pricing[i.kind] ?? 0);
}

export function designPrice(options: DesignerOptions, design: Design) {
  const total = design.picks.reduce((sum, code) => sum + ingredientPrice(options, ingredient(options, code)),
    Number(options.pricing.cup[design.size]));
  return Math.round(total * 100) / 100;
}

export function designNutrition(options: DesignerOptions, design: Design) {
  const graded = recipe(options, design).filter((line) => line.kind === 'liquid' && !line.exclude_from_grade);
  const volume = graded.reduce((sum, line) => sum + line.amount, 0) || 1;
  const per100 = (key: 'sugar' | 'sat_fat') =>
    (graded.reduce((sum, line) => sum + (line.amount * (line[key] ?? 0)) / 100, 0) * 100) / volume;
  const sugar = per100('sugar');
  const satFat = per100('sat_fat');
  return { sugar, satFat, grade: nutriGrade(sugar, satFat, graded.some((line) => line.sweetener)) };
}

export function designName(options: DesignerOptions, design: Design) {
  const names = design.picks.map((code) => ingredient(options, code).name);
  return names.length ? names.join(' + ') : 'Your own drink';
}

export const missingChoice = (options: DesignerOptions, design: Design) =>
  picked(options, design, 'liquid').length ? null : 'Choose at least one liquid';

// The drink code in a QR: "DD1:" + size, sugar and ice digits + ingredient codes,
// e.g. DD1:144:OT-OM-TP is a large oolong oat milk with pearls, 100% sugar and ice.
export const encodeDesign = (design: Design) =>
  `DD1:${design.size}${design.sugar}${design.ice}:${design.picks.join('-')}`;

// A cart line for the designed drink. It has no menu drink id, so the cart treats it as custom.
export function designToCartItem(options: DesignerOptions, design: Design): CustomCartItem {
  return {
    drink: { id: null, name: designName(options, design) },
    custom: { picks: design.picks, price: designPrice(options, design), stub: Boolean(options.stub) },
    size: design.size,
    sugar: design.sugar,
    ice: design.ice,
  };
}
