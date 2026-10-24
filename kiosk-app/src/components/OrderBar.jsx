import React from 'react';
import { Link } from 'react-router-dom';
import { itemPrice } from '../menu';

// The running order along the bottom of the menu, like a food-chain app's cart bar
function OrderBar({ cartItems }) {
    if (cartItems.length === 0) return null;
    const total = cartItems.reduce((sum, item) => sum + itemPrice(item), 0);
    return (
        <div className="order-bar">
            <div className="order-bar-count">{cartItems.length}</div>
            <div className="order-bar-text">
                <span className="eyebrow">Your order</span>
                <strong className="price">${total.toFixed(2)}</strong>
            </div>
            <Link to="/cart" className="btn btn-primary order-bar-go">Review order</Link>
        </div>
    );
}

export default OrderBar;
