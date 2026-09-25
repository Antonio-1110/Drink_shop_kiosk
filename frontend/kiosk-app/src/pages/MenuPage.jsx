import React from 'react';
import DrinkCard from '../components/DrinkCard';

// Pass in 'title' and list of 'drinks' to make this page reusable
function MenuPage({ title, drinks, addToCart }) {
    return (
        <div className="page-container">
                <h1 style={{fontSize: '40px', marginBottom: '20px', color: '#1e3a8a'}}>{title}</h1>
                <div className="grid-layout">
                {drinks.map((drink, index) => (
                    <DrinkCard key={index} name={drink} onAdd={() => addToCart(drink)} />
                ))}
            </div>
        </div>
    );
}

export default MenuPage;