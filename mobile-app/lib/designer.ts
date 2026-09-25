// Rules for building your own drink: which choices are allowed, its price and its Nutri-Grade.
// frontend/kiosk-app/src/designer.js is the same logic for the kiosk; change both together.
import type { CustomCartItem, Size } from './menu';
import { nutriGrade } from './nutrigrade';

// The shape of GET /ordering/designer/options/ (see lib/designerStub.ts until it exists).
// Nutrition values are g per 100 mL or g; volume_ml is keyed by cup size.
export type DesignerOption = {
  id: string;
  name: string;
  price: string;
  color: string;
  available?: boolean;
  sugar?: number;
  sat_fat?: number;
  sweetener?: boolean;
  volume_ml?: Record<number, number>;
  exclude_from_grade?: boolean;
  incompatible?: string[];
};

export type DesignerGroup = { key: string; label: string; hint: string; min: number; max: number; options: DesignerOption[] };

export type DesignerOptions = {
  stub?: boolean;
  sizes: { value: Size; label: string; volume_ml: number; base_price: string }[];
  sweetener: { name: string; sugar: number; sat_fat: number; volume_ml: Record<number, number> };
  groups: DesignerGroup[];
};

export type Design = { size: Size; sugar: number; ice: number; selections: Record<string, string[]> };

type Layer = { id: string; name: string; color: string; ml: number; sugar?: number; sat_fat?: number; sweetener?: boolean; exclude_from_grade?: boolean };

export const findOption = (options: DesignerOptions, id: string) =>
  options.groups.flatMap((group) => group.options).find((option) => option.id === id)!;
const selectedIds = (design: Design) => Object.values(design.selections).flat();

export function newDesign(options: DesignerOptions): Design {
  const selections: Record<string, string[]> = Object.fromEntries(options.groups.map((group) => [group.key, []]));
  // start from the first base in stock so the cup is never empty
  const required = options.groups.find((group) => group.min > 0);
  const base = required?.options.find((option) => option.available !== false);
  if (required && base) selections[required.key] = [base.id];
  return { size: options.sizes[0].value, sugar: 4, ice: 4, selections };
}

// the chosen option that can't go with this one, if any
export function conflictWith(options: DesignerOptions, design: Design, optionId: string) {
  const option = findOption(options, optionId);
  return selectedIds(design)
    .map((id) => findOption(options, id))
    .find((other) => other.id !== optionId
      && (option.incompatible?.includes(other.id) || other.incompatible?.includes(optionId))) ?? null;
}

// why an option can't be picked right now, or null if it can
export function blockedReason(options: DesignerOptions, design: Design, group: DesignerGroup, optionId: string) {
  if (design.selections[group.key].includes(optionId)) return null;
  if (findOption(options, optionId).available === false) return 'Sold out';
  // a single choice gets swapped, so only the other groups can clash with it
  const others = group.max === 1 ? { ...design, selections: { ...design.selections, [group.key]: [] } } : design;
  const conflict = conflictWith(options, others, optionId);
  if (conflict) return `Doesn't go with ${conflict.name}`;
  if (group.max > 1 && design.selections[group.key].length >= group.max) return `Up to ${group.max}`;
  return null;
}

export function toggleOption(options: DesignerOptions, design: Design, group: DesignerGroup, optionId: string): Design {
  const chosen = design.selections[group.key];
  let next: string[];
  if (chosen.includes(optionId)) {
    if (chosen.length <= group.min) return design; // a required choice can only be swapped
    next = chosen.filter((id) => id !== optionId);
  } else {
    if (blockedReason(options, design, group, optionId)) return design;
    next = group.max === 1 ? [optionId] : [...chosen, optionId];
  }
  return { ...design, selections: { ...design.selections, [group.key]: next } };
}

export function designPrice(options: DesignerOptions, design: Design) {
  const size = options.sizes.find((s) => s.value === design.size)!;
  const total = selectedIds(design).reduce((sum, id) => sum + Number(findOption(options, id).price), Number(size.base_price));
  return Math.round(total * 100) / 100;
}

// Liquid layers in the cup, bottom first. The base fills whatever the other liquids leave.
export function cupLayers(options: DesignerOptions, design: Design): Layer[] {
  const size = options.sizes.find((s) => s.value === design.size)!;
  const layers: Layer[] = [];
  const sugarMl = (options.sweetener.volume_ml[design.size] * design.sugar) / 4;
  if (sugarMl > 0) layers.push({ ...options.sweetener, id: 'sweetener', ml: sugarMl, color: '#e9d8b4' });
  for (const id of selectedIds(design)) {
    const option = findOption(options, id);
    if (option.volume_ml) layers.push({ ...option, ml: option.volume_ml[design.size] });
  }
  const used = layers.reduce((sum, layer) => sum + layer.ml, 0);
  for (const id of design.selections.base ?? []) {
    layers.unshift({ ...findOption(options, id), ml: Math.max(size.volume_ml - used, 0) });
  }
  return layers;
}

export function designNutrition(options: DesignerOptions, design: Design) {
  const graded = cupLayers(options, design).filter((layer) => !layer.exclude_from_grade);
  const volume = graded.reduce((sum, layer) => sum + layer.ml, 0) || 1;
  const per100 = (key: 'sugar' | 'sat_fat') =>
    (graded.reduce((sum, layer) => sum + (layer.ml * (layer[key] ?? 0)) / 100, 0) * 100) / volume;
  const sugar = per100('sugar');
  const satFat = per100('sat_fat');
  return { sugar, satFat, grade: nutriGrade(sugar, satFat, graded.some((layer) => layer.sweetener)) };
}

export function designName(options: DesignerOptions, design: Design) {
  const names = selectedIds(design).map((id) => findOption(options, id).name);
  return names.length ? names.join(' + ') : 'Your own drink';
}

// what still has to be picked before it can go in the cart
export function missingChoice(options: DesignerOptions, design: Design) {
  const group = options.groups.find((g) => design.selections[g.key].length < g.min);
  return group ? `Choose a ${group.label.toLowerCase()}` : null;
}

// A cart line for the designed drink. It has no menu drink id, so the cart treats it as custom.
export function designToCartItem(options: DesignerOptions, design: Design): CustomCartItem {
  return {
    drink: { id: null, name: designName(options, design) },
    custom: { selections: design.selections, price: designPrice(options, design), stub: Boolean(options.stub) },
    size: design.size,
    sugar: design.sugar,
    ice: design.ice,
  };
}
