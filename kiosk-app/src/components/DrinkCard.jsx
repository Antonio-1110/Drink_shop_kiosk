import React from 'react';
import { SIZE } from '../menu';
import './DrinkCard.css';

function DrinkCard({ drink, onAdd }) {
    return (
        <div className="card">
            <div className="card-image">
                {drink.image_url ? <img src={drink.image_url} alt={drink.name} /> : <span>PIC</span>}
            </div>
            <div className="card-info">
                <h3>{drink.name}</h3>
                <div className="size-buttons">
                    <button onClick={() => onAdd(drink, SIZE.SMALL)}>S ${Number(drink.s_price).toFixed(2)}</button>
                    <button onClick={() => onAdd(drink, SIZE.LARGE)}>L ${Number(drink.l_price).toFixed(2)}</button>
                </div>
            </div>
        </div>
    );
}

export default DrinkCard;
