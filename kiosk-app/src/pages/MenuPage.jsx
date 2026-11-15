import React, { useState } from 'react';
import DrinkCard from '../components/DrinkCard';
import DrinkSheet from '../components/DrinkSheet';
import { SIZE } from '../menu';
import { useT } from '../i18n';

// Pass in the title's text key and list of 'drinks' to make this page reusable
function MenuPage({ titleKey, subtitleKey, drinks, addToCart, loading }) {
    const t = useT();
    const [selected, setSelected] = useState(null);
    return (
        <div className="menu-page">
            <header className="page-header">
                <h1>{t(titleKey)}</h1>
                {subtitleKey && <p>{t(subtitleKey)}</p>}
            </header>
            {loading && <p className="empty-note" role="status">{t('menu.loading')}</p>}
            {!loading && drinks.length === 0 && <p className="empty-note">{t('menu.empty')}</p>}
            <div className="drink-grid">
                {drinks.map((drink) => (
                    <DrinkCard key={drink.id} drink={drink} onSelect={setSelected} />
                ))}
            </div>
            {selected && (
                <DrinkSheet
                    item={{ drink: selected, size: SIZE.SMALL, sugar: 4, ice: 4 }}
                    confirmLabel={t('drink.add')}
                    onConfirm={(choice) => { addToCart(selected, choice); setSelected(null); }}
                    onClose={() => setSelected(null)}
                />
            )}
        </div>
    );
}

export default MenuPage;
