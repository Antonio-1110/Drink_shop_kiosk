import React, { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { cancelOrder, fetchOrderStatus, fetchPaynowQr } from '../api';
import './CartPage.css';

const POLL_MS = 3000;

function formatRemaining(ms) {
    const seconds = Math.max(0, Math.round(ms / 1000));
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

function PaymentPage({ clearCart }) {
    const { orderId } = useParams();
    const orderToken = useLocation().state?.orderToken;
    const navigate = useNavigate();
    const [qr, setQr] = useState(null);
    const [orderStatus, setOrderStatus] = useState('PENDING');
    const [error, setError] = useState(null);
    const [now, setNow] = useState(() => Date.now());

    // the order is placed, so the cart is done with
    useEffect(() => { clearCart(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

    useEffect(() => {
        fetchPaynowQr(orderId).then(setQr).catch((err) => setError(err.message));
    }, [orderId]);

    // the backend decides when the order is paid or has run out of time; ask it every few seconds
    useEffect(() => {
        if (orderStatus !== 'PENDING') return undefined;
        const timer = setInterval(() => {
            fetchOrderStatus(orderId).then((data) => setOrderStatus(data.status)).catch(() => {});
        }, POLL_MS);
        return () => clearInterval(timer);
    }, [orderId, orderStatus]);

    // a one-second tick for the countdown
    useEffect(() => {
        const tick = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(tick);
    }, []);

    const cancel = async () => {
        try {
            await cancelOrder(orderId, orderToken);
        } catch {
            // already paid or already cancelled; the status poll shows which
        }
        navigate('/');
    };

    if (orderStatus === 'CANCELLED') {
        return (
            <div className="cart-page-container payment-page">
                <h1>Order cancelled</h1>
                <p>The payment time ran out, so nothing was charged.</p>
                <div className="cart-actions">
                    <Link to="/" className="action-btn back-btn">Start a new order</Link>
                </div>
            </div>
        );
    }

    if (orderStatus !== 'PENDING') {
        return (
            <div className="cart-page-container payment-page">
                <h1>Payment received</h1>
                <p>Thank you! Your drink is being made. Order number {orderId}.</p>
                <div className="cart-actions">
                    <Link to="/" className="action-btn back-btn">Start a new order</Link>
                </div>
            </div>
        );
    }

    const remaining = qr ? new Date(qr.expires_at).getTime() - now : null;

    return (
        <div className="cart-page-container payment-page">
            <h1>Scan to pay with PayNow</h1>
            {error && <p className="error-banner">{error}</p>}
            {qr && (
                <>
                    <img className="paynow-qr" src={qr.qr_code} alt="PayNow QR code" />
                    <h3>Amount: ${qr.amount}</h3>
                    <p>Reference: {qr.reference}</p>
                    <p>Time left to pay: {formatRemaining(remaining)}</p>
                </>
            )}
            <div className="cart-actions">
                {orderToken
                    ? <button className="action-btn back-btn" onClick={cancel}>Cancel order</button>
                    : <Link to="/" className="action-btn back-btn">Start a new order</Link>}
            </div>
        </div>
    );
}

export default PaymentPage;
