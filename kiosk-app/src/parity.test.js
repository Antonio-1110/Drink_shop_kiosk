// The kiosk and the phone app preview a designed drink's price and Nutri-Grade on their own.
// These check both previews against what the backend actually charges and records, from
// test-cases/*.json (written by kiosk_backend/ordering/test_app_parity.py). If one fails after a
// backend change, make the app match; if it fails after an app change, the preview is now wrong.
import { describe, expect, it } from 'vitest';
import designerCases from '../../test-cases/designer.json';
import gradeCases from '../../test-cases/nutrigrade.json';
import * as kioskDesigner from './designer';
import { nutriGrade as kioskGrade } from './nutrigrade';
import * as mobileDesigner from '../../mobile-app/lib/designer';
import { nutriGrade as mobileGrade } from '../../mobile-app/lib/nutrigrade';

const apps = { kiosk: { designer: kioskDesigner, grade: kioskGrade }, mobile: { designer: mobileDesigner, grade: mobileGrade } };
const label = ({ picks, size, sugar }) => `${picks.join('+')} size ${size} sugar ${sugar}`;

describe.each(Object.entries(apps))('%s app matches the backend', (_, app) => {
    it('Nutri-Grade at and around each limit', () => {
        for (const c of gradeCases.cases) {
            expect(app.grade(c.sugar, c.sat_fat, c.sweetener), JSON.stringify(c)).toBe(c.grade);
        }
    });

    it.each(designerCases.cases.map((c) => [label(c.design), c]))('designed drink %s', (_, c) => {
        const { options } = designerCases;
        expect(app.designer.designPrice(options, c.design).toFixed(2)).toBe(c.price);
        expect(app.designer.designNutrition(options, c.design).grade).toBe(c.grade);
        const amounts = Object.fromEntries(app.designer.recipe(options, c.design)
            .filter((line) => line.amount > 0).map((line) => [line.code, line.amount]));
        expect(Object.keys(amounts).sort()).toEqual(Object.keys(c.amounts).sort());
        for (const [code, amount] of Object.entries(c.amounts)) {
            // the backend rounds each amount to 0.01
            expect(Math.abs(amounts[code] - amount), code).toBeLessThanOrEqual(0.005 + 1e-9);
        }
    });

    it('its drink code scans back to the same design at the kiosk', () => {
        const { options } = designerCases;
        for (const { design } of designerCases.cases) {
            const code = app.designer.encodeDesign(design);
            expect(kioskDesigner.decodeDesign(options, code)).toEqual({ design });
        }
    });
});
