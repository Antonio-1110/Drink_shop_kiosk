import { describe, expect, it } from 'vitest';
import { translate } from './i18n';
import { cartCount, cartTotal, expandCart, sameDrink } from './menu';

describe('screen text', () => {
    it('fills in values and picks the singular in English', () => {
        expect(translate('en', 'cart.drinks', { count: 1 })).toBe('1 drink');
        expect(translate('en', 'cart.drinks', { count: 3 })).toBe('3 drinks');
        expect(translate('zh', 'cart.drinks', { count: 1 })).toBe('1 杯饮品');
    });

    it('falls back to English, then to the key', () => {
        expect(translate('fr', 'cart.total')).toBe('Total');
        expect(translate('zh', 'no.such.key')).toBe('no.such.key');
    });
});

describe('order quantities', () => {
    const tea = { id: 1, name: 'Oolong', s_price: '3.00', l_price: '4.00' };
    const line = { drink: tea, size: 0, sugar: 2, ice: 4, qty: 3 };

    it('counts, prices and sends one entry per cup', () => {
        const items = [line, { drink: tea, size: 1, sugar: 4, ice: 4 }];
        expect(cartCount(items)).toBe(4);
        expect(cartTotal(items)).toBe(13);
        expect(expandCart(items)).toHaveLength(4);
    });

    it('treats the same drink with other options as a different cup', () => {
        expect(sameDrink(line, { drink: tea, size: 0, sugar: 2, ice: 4 })).toBe(true);
        expect(sameDrink(line, { drink: tea, size: 0, sugar: 1, ice: 4 })).toBe(false);
        const custom = { drink: { id: null }, custom: { picks: ['OT', 'OM'] }, size: 0, sugar: 2, ice: 4 };
        expect(sameDrink(custom, { ...custom, custom: { picks: ['OT', 'OM'] } })).toBe(true);
        expect(sameDrink(custom, line)).toBe(false);
    });
});
