import React from 'react';
import DrinkCard from '../components/DrinkCard';

// Pass in 'title' and list of 'drinks' to make this page reusable
function MenuPage({ title, drinks, addToCart }) {
    return (
        <div className="page-container">
                <h1 style={{fontSize: '40px', marginBottom: '20px', color: '#1e3a8a'}}>{title}</h1>
                {drinks.length === 0 && <p>No drinks available right now.</p>}
                <div className="grid-layout">
                {drinks.map((drink) => (
                    <DrinkCard key={drink.id} drink={drink} onAdd={addToCart} />
                ))}
            </div>
        </div>
    );
}

export default MenuPage;
