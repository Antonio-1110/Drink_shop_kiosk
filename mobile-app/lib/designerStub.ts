// STUB: stands in for GET /ordering/designer/options/ until the backend serves it.
// Everything here is a placeholder for the shop to confirm: which ingredients are offered,
// prices, cup limits, which combinations are blocked, and the nutrition values
// (sugar and saturated fat in g per 100 mL or g). Names match seed_demo where the ingredient exists.
// The kiosk has the same stub in frontend/kiosk-app/src/designerStub.js; change both together.

import type { DesignerOptions } from './designer';

export const DESIGNER_OPTIONS_STUB: DesignerOptions = {
  stub: true,
  // volume_ml is the drink without ice or toppings, which is what Nutri-Grade is measured on
  sizes: [
    { value: 0, label: 'Small', volume_ml: 360, base_price: '2.80' },
    { value: 1, label: 'Large', volume_ml: 500, base_price: '3.40' },
  ],
  // the sugar level scales this syrup: 100% adds volume_ml, 50% adds half
  sweetener: { name: 'Cane sugar syrup', sugar: 65, sat_fat: 0, volume_ml: { 0: 30, 1: 40 } },
  groups: [
    {
      key: 'base', label: 'Base', hint: 'Pick one', min: 1, max: 1, options: [
        { id: 'black-tea', name: 'Black tea', price: '0.00', color: '#8a4b24', sugar: 0, sat_fat: 0 },
        { id: 'green-tea', name: 'Green tea', price: '0.00', color: '#b5c46a', sugar: 0, sat_fat: 0 },
        { id: 'oolong-tea', name: 'Oolong tea', price: '0.00', color: '#c08a3e', sugar: 0, sat_fat: 0 },
        { id: 'espresso', name: 'Espresso', price: '0.80', color: '#3b2417', sugar: 0, sat_fat: 0,
          incompatible: ['passion-fruit', 'lemon', 'mango-puree'] },
      ],
    },
    {
      key: 'milk', label: 'Milk', hint: 'Optional', min: 0, max: 1, options: [
        { id: 'fresh-milk', name: 'Fresh milk', price: '0.60', color: '#f4efe6', sugar: 4.8, sat_fat: 2.3,
          volume_ml: { 0: 100, 1: 140 } },
        { id: 'oat-milk', name: 'Oat milk', price: '0.90', color: '#e8d9bd', sugar: 4.0, sat_fat: 0.3,
          volume_ml: { 0: 100, 1: 140 } },
      ],
    },
    {
      key: 'fruit', label: 'Fruit', hint: 'Up to 2', min: 0, max: 2, options: [
        { id: 'passion-fruit', name: 'Passion fruit', price: '0.80', color: '#f2b705', sugar: 11, sat_fat: 0,
          volume_ml: { 0: 40, 1: 55 } },
        // citrus curdles milk
        { id: 'lemon', name: 'Lemon', price: '0.60', color: '#f7e463', sugar: 2.5, sat_fat: 0,
          volume_ml: { 0: 30, 1: 40 }, incompatible: ['fresh-milk', 'oat-milk'] },
        { id: 'mango-puree', name: 'Mango', price: '1.00', color: '#ffa630', sugar: 14, sat_fat: 0.1,
          volume_ml: { 0: 60, 1: 80 } },
      ],
    },
    {
      // HPB grades toppings separately, so they don't count towards the drink's grade
      key: 'topping', label: 'Toppings', hint: 'Up to 3', min: 0, max: 3, options: [
        { id: 'tapioca-pearls', name: 'Tapioca pearls', price: '0.60', color: '#2e1a12', exclude_from_grade: true },
        { id: 'coconut-jelly', name: 'Coconut jelly', price: '0.60', color: '#f5f5f0', exclude_from_grade: true },
        { id: 'grass-jelly', name: 'Grass jelly', price: '0.60', color: '#1d1d1d', exclude_from_grade: true },
        { id: 'aloe-vera', name: 'Aloe vera', price: '0.70', color: '#cfe8c4', exclude_from_grade: true },
        { id: 'cheese-foam', name: 'Cheese foam', price: '1.00', color: '#fff6d8', exclude_from_grade: true },
      ],
    },
  ],
};
