import React, { useState } from 'react';
import DrinkCard from '../components/DrinkCard';
import DrinkSheet from '../components/DrinkSheet';
import { SIZE } from '../menu';

// Pass in 'title' and list of 'drinks' to make this page reusable
function MenuPage({ title, subtitle, drinks, addToCart }) {
    const [selected, setSelected] = useState(null);
    return (
        <div className="menu-page">
            <header className="page-header">
                <h1>{title}</h1>
                {subtitle && <p>{subtitle}</p>}
            </header>
            {drinks.length === 0 && <p className="empty-note">Nothing here right now. Please check another section.</p>}
            <div className="drink-grid">
                {drinks.map((drink) => (
                    <DrinkCard key={drink.id} drink={drink} onSelect={setSelected} />
                ))}
            </div>
            {selected && (
                <DrinkSheet
                    item={{ drink: selected, size: SIZE.SMALL, sugar: 4, ice: 4 }}
                    confirmLabel="Add to order"
                    onConfirm={(choice) => { addToCart(selected, choice); setSelected(null); }}
                    onClose={() => setSelected(null)}
                />
            )}
        </div>
    );
}

export default MenuPage;
