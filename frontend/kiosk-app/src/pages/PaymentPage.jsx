import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { fetchPaynowQr } from '../api';
import './CartPage.css';

function PaymentPage({ clearCart }) {
    const { orderId } = useParams();
    const [qr, setQr] = useState(null);
    const [error, setError] = useState(null);

    // the order is placed, so the cart is done with
    useEffect(() => { clearCart(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

    useEffect(() => {
        fetchPaynowQr(orderId).then(setQr).catch((err) => setError(err.message));
    }, [orderId]);

    return (
        <div className="cart-page-container payment-page">
            <h1>Scan to pay with PayNow</h1>
            {error && <p className="error-banner">{error}</p>}
            {qr && (
                <>
                    <img className="paynow-qr" src={qr.qr_code} alt="PayNow QR code" />
                    <h3>Amount: ${qr.amount}</h3>
                    <p>Reference: {qr.reference}</p>
                    {/* unpaid orders are cancelled after this and the drinks go back on sale */}
                    <p>Please pay by {new Date(qr.expires_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>
                </>
            )}
            <div className="cart-actions">
                <Link to="/" className="action-btn back-btn">Start a new order</Link>
            </div>
        </div>
    );
}

export default PaymentPage;
