import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { placeOrder } from '../api';
import DrinkArt from '../components/DrinkArt';
import DrinkSheet from '../components/DrinkSheet';
import Steps from '../components/Steps';
import { LEVELS, SIZE, itemPrice } from '../menu';
import './CartPage.css';

const levelLabel = (value) => LEVELS.find((level) => level.value === value)?.label;

function CartPage({ cartItems, updateCartItem, removeFromCart }) {
    const navigate = useNavigate();
    const [error, setError] = useState(null);
    const [submitting, setSubmitting] = useState(false);
    const [editing, setEditing] = useState(null); // index of the line whose options are open
    const total = cartItems.reduce((sum, item) => sum + itemPrice(item), 0).toFixed(2);

    const checkout = async () => {
        setSubmitting(true);
        setError(null);
        try {
            const order = await placeOrder(cartItems);
            // the token proves this kiosk placed the order, so the payment screen can cancel it
            navigate(`/payment/${order.id}`, { state: { orderToken: order.order_token } });
        } catch (err) {
            // the backend lists the drinks and designer ingredients it no longer has stock for
            const soldOut = cartItems
                .filter((item) => (item.custom
                    ? item.custom.picks.some((code) => err.data?.options?.includes(code))
                    : err.data?.drinks?.includes(item.drink.id)))
                .map((item) => item.drink.name);
            setError(soldOut.length
                ? `Sorry, not enough stock for: ${[...new Set(soldOut)].join(', ')}`
                : err.message);
        } finally {
            setSubmitting(false);
        }
    };

    if (cartItems.length === 0) {
        return (
            <div className="cart-empty">
                <h1>Your order is empty</h1>
                <p>Pick a drink from the menu to get started.</p>
                <Link to="/" className="btn btn-primary">Browse the menu</Link>
            </div>
        );
    }

    return (
        <div className="cart-page">
            <Steps current={0} />
            <header className="page-header">
                <h1>Review your order</h1>
            </header>

            <div className="cart-columns">
                <ul className="cart-list">
                    {cartItems.map((item, index) => (
                        <li key={index} className="cart-line">
                            <DrinkArt drink={item.drink} size="sm" />
                            <div className="cart-line-main">
                                <div className="cart-line-name">
                                    {item.drink.name}
                                    {item.custom && <span className="custom-tag">Designed</span>}
                                </div>
                                <div className="cart-line-detail">
                                    {item.size === SIZE.LARGE ? 'Large' : 'Regular'}
                                    {' · '}Sugar {levelLabel(item.sugar)}
                                    {' · '}Ice {levelLabel(item.ice)}
                                </div>
                                <div className="cart-line-actions">
                                    <button className="btn-text" onClick={() => setEditing(index)}>Edit</button>
                                    <button className="btn-text" onClick={() => removeFromCart(index)}>Remove</button>
                                </div>
                            </div>
                            <div className="cart-line-price price">${itemPrice(item).toFixed(2)}</div>
                        </li>
                    ))}
                </ul>

                <aside className="cart-summary">
                    <div className="summary-row">
                        <span>{cartItems.length} {cartItems.length === 1 ? 'drink' : 'drinks'}</span>
                        <span className="price">${total}</span>
                    </div>
                    <div className="summary-row summary-total">
                        <span>Total</span>
                        <span className="price">${total}</span>
                    </div>
                    {error && <p className="error-banner">{error}</p>}
                    <button className="btn btn-primary btn-block" onClick={checkout} disabled={submitting}>
                        {submitting ? 'Placing order…' : 'Continue to payment'}
                    </button>
                    <Link to="/" className="btn btn-ghost btn-block">Add another drink</Link>
                </aside>
            </div>

            {editing !== null && (
                <DrinkSheet
                    item={cartItems[editing]}
                    confirmLabel="Save changes"
                    onConfirm={(choice) => { updateCartItem(editing, choice); setEditing(null); }}
                    onClose={() => setEditing(null)}
                />
            )}
        </div>
    );
}

export default CartPage;
