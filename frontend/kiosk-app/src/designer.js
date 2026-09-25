// Building your own drink: how much of each ingredient goes in, its price, its Nutri-Grade,
// and the drink code customers bring to the kiosk.
// mobile-app/lib/designer.ts is the same logic in TypeScript; change both together.
import { nutriGrade } from './nutrigrade';

export const findIngredient = (options, code) => options.ingredients.find((i) => i.code === code);

// categories in the order the options list them
export const categories = (options) => [...new Set(options.ingredients.map((i) => i.category))];

export function newDesign(options) {
    // start from the first liquid in stock so the cup is never empty
    const first = options.ingredients.find((i) => i.kind === 'liquid' && i.available !== false);
    return { size: options.sizes[0].value, sugar: 4, ice: 4, picks: first ? [first.code] : [] };
}

export function togglePick(options, design, code) {
    if (design.picks.includes(code)) return { ...design, picks: design.picks.filter((c) => c !== code) };
    if (findIngredient(options, code).available === false) return design;
    return { ...design, picks: [...design.picks, code] };
}

const picked = (options, design, kind) =>
    design.picks.map((code) => findIngredient(options, code)).filter((i) => i.kind === kind);

// Each picked ingredient's amount. Liquids share the cup by their `share`; the sugar level's syrup
// comes out of the same volume. Toppings split the size's topping allowance evenly.
export function recipe(options, design) {
    const size = options.sizes.find((s) => s.value === design.size);
    const lines = [];
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

export function ingredientPrice(options, ingredient) {
    return Number(options.pricing.overrides?.[ingredient.code] ?? options.pricing[ingredient.kind] ?? 0);
}

export function designPrice(options, design) {
    const total = design.picks.reduce((sum, code) => sum + ingredientPrice(options, findIngredient(options, code)),
        Number(options.pricing.cup[design.size]));
    return Math.round(total * 100) / 100;
}

export function designNutrition(options, design) {
    const graded = recipe(options, design).filter((line) => line.kind === 'liquid' && !line.exclude_from_grade);
    const volume = graded.reduce((sum, line) => sum + line.amount, 0) || 1;
    const per100 = (key) => graded.reduce((sum, line) => sum + (line.amount * (line[key] ?? 0)) / 100, 0) * 100 / volume;
    const sugar = per100('sugar');
    const satFat = per100('sat_fat');
    return { sugar, satFat, grade: nutriGrade(sugar, satFat, graded.some((line) => line.sweetener)) };
}

export function designName(options, design) {
    const names = design.picks.map((code) => findIngredient(options, code).name);
    return names.length ? names.join(' + ') : 'Your own drink';
}

export const missingChoice = (options, design) =>
    picked(options, design, 'liquid').length ? null : 'Choose at least one liquid';

// The drink code in a QR: "DD1:" + size, sugar and ice digits + ingredient codes,
// e.g. DD1:144:OT-OM-TP is a large oolong oat milk with pearls, 100% sugar and ice.
const CODE_PREFIX = 'DD1:';

export const encodeDesign = (design) =>
    `${CODE_PREFIX}${design.size}${design.sugar}${design.ice}:${design.picks.join('-')}`;

// Returns { design } or { error } for a scanned code.
export function decodeDesign(options, text) {
    const match = /^DD1:(\d)(\d)(\d):([A-Z0-9-]*)$/.exec(text.trim().toUpperCase());
    if (!match) return { error: "That isn't a drink code from the app." };
    const [, size, sugar, ice, list] = match;
    const picks = list ? [...new Set(list.split('-'))] : [];
    const design = { size: Number(size), sugar: Number(sugar), ice: Number(ice), picks };
    if (!options.sizes.some((s) => s.value === design.size) || design.sugar > 4 || design.ice > 4) {
        return { error: "That drink code isn't valid." };
    }
    const unknown = picks.filter((code) => !findIngredient(options, code));
    if (unknown.length) return { error: `This kiosk doesn't have: ${unknown.join(', ')}` };
    const soldOut = picks.filter((code) => findIngredient(options, code).available === false);
    if (soldOut.length) {
        return { error: `Sold out here: ${soldOut.map((code) => findIngredient(options, code).name).join(', ')}` };
    }
    return { design };
}

// A cart line for the designed drink. It has no menu drink id, so the cart treats it as custom.
export function designToCartItem(options, design) {
    return {
        drink: { id: null, name: designName(options, design) },
        custom: { picks: design.picks, price: designPrice(options, design), stub: Boolean(options.stub) },
        size: design.size,
        sugar: design.sugar,
        ice: design.ice,
    };
}
