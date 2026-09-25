import React from 'react';
import { Link } from 'react-router-dom';
import './CartPage.css';

function CartPage({ cartItems }) {
    // sample total
    const total = (cartItems.length * 5.00).toFixed(2);
    
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
                                <span>{item}</span>
                                <span>$5.00</span>
                            </li>
                            ))}
                    </ul>
                )}
            </div>

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
                <button to="/payment" className="action-btn payment-btn">
                    Proceed to Payment &rarr;
                </button>
            </div>
        </div>
    );
}

export default CartPage;