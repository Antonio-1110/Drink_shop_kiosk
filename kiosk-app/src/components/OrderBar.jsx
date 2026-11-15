import React from 'react';
import { Link } from 'react-router-dom';
import { cartCount, cartTotal } from '../menu';
import { useT } from '../i18n';

// The running order along the bottom of the menu, like a food-chain app's cart bar. Just after a
// drink goes in, it says so (`added`), so the customer knows the tap worked.
function OrderBar({ cartItems, added }) {
    const t = useT();
    if (cartItems.length === 0) return null;
    const count = cartCount(cartItems);
    return (
        <div className={`order-bar ${added ? 'just-added' : ''}`}>
            {/* the key restarts the little bounce on every add */}
            <div className="order-bar-count" key={added?.at ?? 'count'}>{count}</div>
            <div className="order-bar-text">
                <span className="eyebrow" aria-live="polite">
                    {added ? t('bar.added', { name: added.name }) : t('bar.yourOrder')}
                </span>
                <strong className="price">${cartTotal(cartItems).toFixed(2)}</strong>
            </div>
            <Link to="/cart" className="btn btn-primary order-bar-go">{t('bar.review')}</Link>
        </div>
    );
}

export default OrderBar;
