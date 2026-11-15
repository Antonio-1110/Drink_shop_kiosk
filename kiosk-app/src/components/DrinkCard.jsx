import React from 'react';
import DrinkArt from './DrinkArt';
import NutriGradeMark from './NutriGradeMark';
import { useT } from '../i18n';
import './DrinkCard.css';

// One drink on the menu. Tapping it opens the drink's options (see DrinkSheet).
function DrinkCard({ drink, onSelect }) {
    const t = useT();
    const from = Math.min(Number(drink.s_price), Number(drink.l_price));
    return (
        <button className="drink-card" onClick={() => onSelect(drink)}>
            <DrinkArt drink={drink} />
            <div className="drink-card-info">
                <h3>{drink.name}</h3>
                {drink.description && <p>{drink.description}</p>}
                <NutriGradeMark grade={drink.nutri_grade} />
                <div className="drink-card-foot">
                    <span className="price" aria-label={t('drink.from', { price: `$${from.toFixed(2)}` })}>
                        ${from.toFixed(2)}
                    </span>
                    <span className="drink-card-add" aria-hidden="true">+</span>
                </div>
            </div>
        </button>
    );
}

export default DrinkCard;
