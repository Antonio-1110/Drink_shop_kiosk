import React, { useEffect, useRef, useState } from 'react';
import { LEVELS, SIZE, itemPrice } from '../menu';
import DrinkArt from './DrinkArt';
import NutriGradeMark from './NutriGradeMark';
import { useT } from '../i18n';
import './DrinkSheet.css';

function ChoiceRow({ label, children }) {
    return (
        <div className="sheet-group" role="group" aria-label={label}>
            <div className="eyebrow">{label}</div>
            <div className="chips">{children}</div>
        </div>
    );
}

// Choose size, sugar and ice for a drink, as a panel over the menu. `item` is the cart line being
// added or edited; a designed drink keeps the size it was designed in, so only sugar and ice show.
function DrinkSheet({ item, confirmLabel, onConfirm, onClose }) {
    const t = useT();
    const [choice, setChoice] = useState({ size: item.size, sugar: item.sugar, ice: item.ice });
    const { drink, custom } = item;
    const price = itemPrice({ ...item, ...choice });
    const set = (changes) => setChoice({ ...choice, ...changes });
    const confirmButton = useRef(null);
    const close = useRef(onClose);
    useEffect(() => { close.current = onClose; });

    // a keyboard or screen reader lands on the main button, and Escape closes the panel
    useEffect(() => {
        confirmButton.current?.focus({ preventScroll: true });
        const onKey = (e) => { if (e.key === 'Escape') close.current(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, []);

    const levelChips = (key, value) => LEVELS.map((level) => (
        <button key={level.value} aria-pressed={value === level.value} aria-label={`${t(key)} ${level.label}`}
            className={`chip ${value === level.value ? 'selected' : ''}`}
            onClick={() => set({ [key === 'drink.sugar' ? 'sugar' : 'ice']: level.value })}>
            {level.label}
        </button>
    ));

    return (
        <div className="sheet-backdrop" onClick={onClose}>
            <div className="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title"
                onClick={(e) => e.stopPropagation()}>
                <button className="sheet-close" onClick={onClose} aria-label={t('drink.close')}>×</button>
                <div className="sheet-art">
                    <DrinkArt drink={drink} size="lg" />
                </div>
                <div className="sheet-body">
                    <h2 id="sheet-title">{drink.name}</h2>
                    {drink.description && <p className="sheet-description">{drink.description}</p>}
                    {/* graded at 100% sugar, as the menu shows it */}
                    <NutriGradeMark grade={drink.nutri_grade} size="lg" />

                    {!custom && (
                        <ChoiceRow label={t('drink.size')}>
                            {[[SIZE.SMALL, t('drink.regular'), drink.s_price], [SIZE.LARGE, t('drink.large'), drink.l_price]].map(([value, label, cost]) => (
                                <button key={value} aria-pressed={choice.size === value}
                                    className={`chip ${choice.size === value ? 'selected' : ''}`}
                                    onClick={() => set({ size: value })}>
                                    {label} <small className="price">${Number(cost).toFixed(2)}</small>
                                </button>
                            ))}
                        </ChoiceRow>
                    )}
                    <ChoiceRow label={t('drink.sugar')}>{levelChips('drink.sugar', choice.sugar)}</ChoiceRow>
                    <ChoiceRow label={t('drink.ice')}>{levelChips('drink.ice', choice.ice)}</ChoiceRow>

                    <button ref={confirmButton} className="btn btn-primary btn-block sheet-confirm"
                        onClick={() => onConfirm(choice)}>
                        <span>{confirmLabel}</span>
                        <span className="price">${price.toFixed(2)}</span>
                    </button>
                </div>
            </div>
        </div>
    );
}

export default DrinkSheet;
