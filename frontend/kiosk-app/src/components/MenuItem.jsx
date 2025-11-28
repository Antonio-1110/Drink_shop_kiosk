import React from 'react';

const MenuItem = ({ name, price }) => {
    return (
        <div className="menu-item">
            <h2>{name}</h2>
            <p>${price.toFixed(2)}</p>
            <button>Add to Cart</button>
        </div>
    );
};

export default MenuItem;