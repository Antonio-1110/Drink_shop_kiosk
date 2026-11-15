import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { placeOrder } from '../api';
import DrinkArt from '../components/DrinkArt';
import DrinkSheet from '../components/DrinkSheet';
import Steps from '../components/Steps';
import { LEVELS, MAX_ORDER_DRINKS, SIZE, cartCount, cartTotal, lineQty, lineTotal } from '../menu';
import { useT } from '../i18n';
import './CartPage.css';

const levelLabel = (value) => LEVELS.find((level) => level.value === value)?.label;
// why the shop can't take orders (the backend's 503 `reason`); nothing is placed or charged
const SHOP_CLOSED = ['machine_offline', 'maintenance', 'machine_not_ready'];

// what the customer should see when the backend turns the order down
function orderErrorMessage(err, cartItems, t) {
    if (err.offline) return t('cart.offline');
    if (err.status === 503 && SHOP_CLOSED.includes(err.data?.reason)) return t(`closed.${err.data.reason}`);
    if (err.status === 429) return t('cart.busy');
    // more drinks than the backend allows (its limit may differ from ours)
    if (err.status === 400 && err.data?.items) return t('cart.tooMany', { max: MAX_ORDER_DRINKS });
    // the backend lists the drinks and designer ingredients it no longer has stock for
    const soldOut = cartItems
        .filter((item) => (item.custom
            ? item.custom.picks.some((code) => err.data?.options?.includes(code))
            : err.data?.drinks?.includes(item.drink.id)))
        .map((item) => item.drink.name);
    return soldOut.length ? t('cart.soldOut', { names: [...new Set(soldOut)].join(', ') }) : err.message;
}

// − 2 + : one less (which removes the line at 1) or one more of the same cup
function Quantity({ item, onChange, t }) {
    const qty = lineQty(item);
    const name = item.drink.name;
    return (
        <div className="qty" role="group" aria-label={`${t('cart.quantity')}: ${name}`}>
            <button onClick={() => onChange(qty - 1)} aria-label={t(qty === 1 ? 'cart.remove' : 'cart.less', { name })}>
                {qty === 1 ? <TrashIcon /> : '−'}
            </button>
            <span aria-live="polite">{qty}</span>
            <button onClick={() => onChange(qty + 1)} aria-label={t('cart.more', { name })}>+</button>
        </div>
    );
}

function TrashIcon() {
    return (
        <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor"
            strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" />
        </svg>
    );
}

function CartPage({ cartItems, updateCartItem, removeFromCart }) {
    const t = useT();
    const navigate = useNavigate();
    const [error, setError] = useState(null);
    const [submitting, setSubmitting] = useState(false);
    const [editing, setEditing] = useState(null); // index of the line whose options are open
    const count = cartCount(cartItems);
    const total = cartTotal(cartItems).toFixed(2);
    const tooMany = count > MAX_ORDER_DRINKS;

    const checkout = async () => {
        setSubmitting(true);
        setError(null);
        try {
            const order = await placeOrder(cartItems);
            // the token proves this kiosk placed the order, so the payment screen can cancel it
            navigate(`/payment/${order.id}`, { state: { orderToken: order.order_token } });
        } catch (err) {
            setError(orderErrorMessage(err, cartItems, t));
        } finally {
            setSubmitting(false);
        }
    };

    const setQty = (index, qty) => {
        setError(null);
        if (qty < 1) removeFromCart(index);
        else updateCartItem(index, { qty });
    };

    if (cartItems.length === 0) {
        return (
            <div className="cart-empty">
                <h1>{t('cart.emptyTitle')}</h1>
                <p>{t('cart.emptyText')}</p>
                <Link to="/" className="btn btn-primary">{t('cart.browse')}</Link>
            </div>
        );
    }

    return (
        <div className="cart-page">
            <Steps current={0} />
            <header className="page-header">
                <h1>{t('cart.title')}</h1>
            </header>

            <div className="cart-columns">
                <ul className="cart-list">
                    {cartItems.map((item, index) => (
                        <li key={index} className="cart-line">
                            <DrinkArt drink={item.drink} size="sm" />
                            <div className="cart-line-main">
                                <div className="cart-line-name">
                                    {item.drink.name}
                                    {item.custom && <span className="custom-tag">{t('cart.designed')}</span>}
                                </div>
                                <div className="cart-line-detail">
                                    {t('cart.detail', {
                                        size: t(item.size === SIZE.LARGE ? 'drink.large' : 'drink.regular'),
                                        sugar: levelLabel(item.sugar),
                                        ice: levelLabel(item.ice),
                                    })}
                                </div>
                                <div className="cart-line-actions">
                                    <button className="btn-pill" onClick={() => setEditing(index)}>{t('cart.edit')}</button>
                                    <Quantity item={item} t={t} onChange={(qty) => setQty(index, qty)} />
                                </div>
                            </div>
                            <div className="cart-line-price price">${lineTotal(item).toFixed(2)}</div>
                        </li>
                    ))}
                </ul>

                <aside className="cart-summary">
                    <div className="summary-row">
                        <span>{t('cart.drinks', { count })}</span>
                        <span className="price">${total}</span>
                    </div>
                    <div className="summary-row summary-total">
                        <span>{t('cart.total')}</span>
                        <span className="price">${total}</span>
                    </div>
                    {tooMany && !error && <p className="error-banner" role="alert">{t('cart.tooMany', { max: MAX_ORDER_DRINKS })}</p>}
                    {error && <p className="error-banner" role="alert">{error}</p>}
                    <button className="btn btn-primary btn-block" onClick={checkout} disabled={submitting || tooMany}>
                        {submitting ? t('cart.placing') : t('cart.continue')}
                    </button>
                    <Link to="/" className="btn btn-ghost btn-block">{t('cart.addAnother')}</Link>
                </aside>
            </div>

            {editing !== null && (
                <DrinkSheet
                    item={cartItems[editing]}
                    confirmLabel={t('drink.save')}
                    onConfirm={(choice) => { updateCartItem(editing, choice); setEditing(null); }}
                    onClose={() => setEditing(null)}
                />
            )}
        </div>
    );
}

export default CartPage;
