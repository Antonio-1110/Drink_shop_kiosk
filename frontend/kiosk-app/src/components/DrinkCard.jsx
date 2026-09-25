import React from 'react';
import './DrinkCard.css';

function DrinkCard({ name, onAdd }) {
    return (
        <div className="card" onClick={onAdd}>
            <div className="card-image">
                <span>PIC</span>
            </div>
            <div className="card-info">
                <h3>{name}</h3>
            </div>
        </div>
    );
}

export default DrinkCard;