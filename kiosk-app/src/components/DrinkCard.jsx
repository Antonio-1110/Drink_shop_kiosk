import React from 'react';
import DrinkArt from './DrinkArt';
import './DrinkCard.css';

// One drink on the menu. Tapping it opens the drink's options (see DrinkSheet).
function DrinkCard({ drink, onSelect }) {
    const from = Math.min(Number(drink.s_price), Number(drink.l_price));
    return (
        <button className="drink-card" onClick={() => onSelect(drink)}>
            <DrinkArt drink={drink} />
            <div className="drink-card-info">
                <h3>{drink.name}</h3>
                {drink.description && <p>{drink.description}</p>}
                <div className="drink-card-foot">
                    <span className="price">${from.toFixed(2)}</span>
                    <span className="drink-card-add" aria-hidden="true">+</span>
                </div>
            </div>
        </button>
    );
}

export default DrinkCard;
