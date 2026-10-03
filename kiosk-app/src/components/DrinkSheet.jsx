import React, { useState } from 'react';
import { LEVELS, SIZE, itemPrice } from '../menu';
import DrinkArt from './DrinkArt';
import './DrinkSheet.css';

function ChoiceRow({ label, children }) {
    return (
        <div className="sheet-group">
            <div className="eyebrow">{label}</div>
            <div className="chips">{children}</div>
        </div>
    );
}

// Choose size, sugar and ice for a drink, as a panel over the menu. `item` is the cart line being
// added or edited; a designed drink keeps the size it was designed in, so only sugar and ice show.
function DrinkSheet({ item, confirmLabel, onConfirm, onClose }) {
    const [choice, setChoice] = useState({ size: item.size, sugar: item.sugar, ice: item.ice });
    const { drink, custom } = item;
    const price = itemPrice({ ...item, ...choice });
    const set = (changes) => setChoice({ ...choice, ...changes });

    return (
        <div className="sheet-backdrop" onClick={onClose}>
            <div className="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title"
                onClick={(e) => e.stopPropagation()}>
                <button className="sheet-close" onClick={onClose} aria-label="Close">×</button>
                <div className="sheet-art">
                    <DrinkArt drink={drink} size="lg" />
                </div>
                <div className="sheet-body">
                    <h2 id="sheet-title">{drink.name}</h2>
                    {drink.description && <p className="sheet-description">{drink.description}</p>}

                    {!custom && (
                        <ChoiceRow label="Size">
                            {[[SIZE.SMALL, 'Regular', drink.s_price], [SIZE.LARGE, 'Large', drink.l_price]].map(([value, label, cost]) => (
                                <button key={value} className={`chip ${choice.size === value ? 'selected' : ''}`}
                                    onClick={() => set({ size: value })}>
                                    {label} <small className="price">${Number(cost).toFixed(2)}</small>
                                </button>
                            ))}
                        </ChoiceRow>
                    )}
                    <ChoiceRow label="Sugar">
                        {LEVELS.map((level) => (
                            <button key={level.value} className={`chip ${choice.sugar === level.value ? 'selected' : ''}`}
                                onClick={() => set({ sugar: level.value })}>
                                {level.label}
                            </button>
                        ))}
                    </ChoiceRow>
                    <ChoiceRow label="Ice">
                        {LEVELS.map((level) => (
                            <button key={level.value} className={`chip ${choice.ice === level.value ? 'selected' : ''}`}
                                onClick={() => set({ ice: level.value })}>
                                {level.label}
                            </button>
                        ))}
                    </ChoiceRow>

                    <button className="btn btn-primary btn-block sheet-confirm" onClick={() => onConfirm(choice)}>
                        <span>{confirmLabel}</span>
                        <span className="price">${price.toFixed(2)}</span>
                    </button>
                </div>
            </div>
        </div>
    );
}

export default DrinkSheet;
