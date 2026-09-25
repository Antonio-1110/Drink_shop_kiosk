import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { placeOrder } from '../api';
import { LEVELS, SIZE, itemPrice } from '../menu';
import './CartPage.css';

function LevelSelect({ label, value, onChange }) {
    return (
        <label className="level-select">
            {label}
            <select value={value} onChange={(e) => onChange(Number(e.target.value))}>
                {LEVELS.map((level) => <option key={level.value} value={level.value}>{level.label}</option>)}
            </select>
        </label>
    );
}

function CartPage({ cartItems, updateCartItem, removeFromCart }) {
    const navigate = useNavigate();
    const [error, setError] = useState(null);
    const [submitting, setSubmitting] = useState(false);
    const total = cartItems.reduce((sum, item) => sum + itemPrice(item), 0).toFixed(2);

    const checkout = async () => {
        setSubmitting(true);
        setError(null);
        try {
            const order = await placeOrder(cartItems);
            navigate(`/payment/${order.id}`);
        } catch (err) {
            // the backend lists the drinks it no longer has stock for
            const soldOut = cartItems
                .filter((item) => err.data?.drinks?.includes(item.drink.id))
                .map((item) => item.drink.name);
            setError(soldOut.length
                ? `Sorry, not enough stock for: ${[...new Set(soldOut)].join(', ')}`
                : err.message);
        } finally {
            setSubmitting(false);
        }
    };
    
    return (
        <div className="cart-page-container">
            <h1>Your Cart</h1>

            <div className="cart-list">
                {cartItems.length === 0 ? (
                    <p>Your cart is empty.</p>
                ) : (
                    <ul>
                        {cartItems.map((item, index) => (
                            <li key={index} className="cart-item">
                                <span>{item.drink.name} ({item.size === SIZE.LARGE ? 'L' : 'S'})</span>
                                <LevelSelect label="Sugar" value={item.sugar}
                                    onChange={(sugar) => updateCartItem(index, { sugar })} />
                                <LevelSelect label="Ice" value={item.ice}
                                    onChange={(ice) => updateCartItem(index, { ice })} />
                                <span>${itemPrice(item).toFixed(2)}</span>
                                <button className="remove-btn" onClick={() => removeFromCart(index)}>Remove</button>
                            </li>
                            ))}
                    </ul>
                )}
            </div>

            {error && <p className="error-banner">{error}</p>}

            <div className="cart-summary">
                <h3>Total: ${total}</h3>
            </div>

            {/* Footer actions */}
            <div className="cart-actions">
                {/* Left Button */}
                <Link to="/" className="action-btn back-btn">
                    &larr;Continue Shopping
                </Link>

                {/* Right Button */}
                <button className="action-btn pay-btn" onClick={checkout}
                    disabled={cartItems.length === 0 || submitting}>
                    {submitting ? 'Placing order...' : 'Proceed to Payment →'}
                </button>
            </div>
        </div>
    );
}

export default CartPage;
